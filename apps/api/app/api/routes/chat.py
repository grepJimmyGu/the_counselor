"""Chat endpoint — authenticated conversations with SSE streaming and
tool-calling dispatch (Stage 7 / ticket #5).

POST /api/chat/conversations/{conversation_id}/messages
  - Auth required (Stage 1 get_current_user dep).
  - Daily turn cap enforced before any LLM call.
  - Streams Server-Sent Events: token / tool_call / tool_result / done / error.
  - Persists user message + assistant message + tool messages into
    chat_conversations / chat_messages (Stage 7 / ticket #1 tables).
  - Tool dispatch loop: when the LLM emits ChatToolCall events, executes
    them via dispatch_tool_call, appends results, re-invokes the LLM with
    enriched context. Loops until ChatDone with finish_reason != "tool_calls".

The client picks a UUID for the conversation on first POST; the server
creates the conversation row if not found, scoped to the authenticated user.
A second user posting to the same UUID gets 403 (ownership check).

Anonymous chat lives in ticket #6 (separate route + tool whitelist + 5/turn
cap per AnonymousSession). This route is signed-in users only.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.entitlement_errors import upgrade_error
from app.db.session import get_db
from app.models.anonymous_session import AnonymousSession
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User
from app.services.anonymous_service import get_or_create_anonymous_session
from app.services.chat_guardrails import (
    append_redaction_warning,
    attempt_citation_reprompt,
    classify_refusal,
    detect_uncited_numerics,
    log_refusal_event,
    log_uncited_event,
)
from app.services.chat_tools import (
    UnknownToolError,
    dispatch_tool_call,
    get_openai_tool_specs,
)
from app.services.llm_adapter import (
    ChatDone,
    ChatToken,
    ChatToolCall,
    LLMAdapterError,
    get_llm_gateway,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])
anonymous_router = APIRouter(prefix="/api/anonymous/chat", tags=["chat", "anonymous"])
_log = logging.getLogger("livermore.chat")


# Anonymous-tier chat constants per build_specs/07_chat_v2_research_partner.md §2:
ANON_TURN_CAP = 5  # turns per AnonymousSession (lifetime, not daily)
ANON_TOKEN_CAP = 8_000  # rough char approximation; the spec quotes 8K tokens
ANON_TOOL_WHITELIST: set[str] = {
    "strategy_builder_iterate",
    "concept_explainer",
    "template_search",
    "onboarding_tutor",
    "backtest_execute",
}
# Excluded for anonymous (would otherwise be tempting):
#   stock_lookup     — Stage 3 already gates by S&P 500 scope, but the
#                      tool itself touches per-user state we'd rather not.
#   backtest_explain — requires backtest_id ownership; anon can't own one.


# ── Schemas ───────────────────────────────────────────────────────────────────


class ChatMessageRequest(BaseModel):
    """Body of POST /api/chat/conversations/{id}/messages."""

    content: str
    context_type: Optional[str] = None
    context_payload: Optional[dict] = None


# ── Tier caps ─────────────────────────────────────────────────────────────────

# Per build_specs/07_chat_v2_research_partner.md §4 tier matrix:
#   Scout 20/day, 100/week. Strategist 100/day, 500/week. Quant unlimited.
# Phase 1 ships the daily cap; weekly is observed-only (no enforcement).
# The `onboarding_tutor` first-3-turns exemption from spec §7 is a DEFERRED
# refinement — for now ALL Scout messages count against the cap. Track in
# project backlog if the activation funnel suffers.
_DAILY_CAP_BY_TIER: Dict[str, Optional[int]] = {
    "scout": 20,
    "strategist": 100,
    "quant": None,  # unlimited (soft monitoring only)
}


def _system_prompt() -> str:
    """The system message prepended to every chat request.

    Locked refusals per spec §3 / §4.5. Citation enforcement (spec §3.7) is
    DEFERRED to ticket #9 — the runtime reprompt loop adds it without
    requiring this prompt to change.
    """
    return (
        "You are Livermore's research partner. You help users research "
        "investment strategies and stocks using the tools at your disposal. "
        "You DO NOT execute trades, give personalized financial advice, or "
        "make forward predictions about prices. You refuse those requests "
        "and redirect to a research-oriented alternative (backtest, "
        "scorecard lookup, concept explanation). "
        "Use tools whenever they are available — never invent numeric "
        "claims when a tool can produce them. When you cite a metric, "
        "say where it came from (e.g., 'based on the AAPL scorecard'). "
        "Outputs are paper strategies and historical backtests, not "
        "financial advice."
    )


# ── Rate limit ────────────────────────────────────────────────────────────────


def _check_chat_quota(db: Session, user_id: str, tier: str) -> None:
    """Raise 402 if the user is over their daily turn cap. Counts user-role
    messages in chat_messages joined to chat_conversations owned by them.

    The query is per-user (not per-conversation) so opening a new conversation
    doesn't reset the counter — that would be a trivial bypass.
    """
    cap = _DAILY_CAP_BY_TIER.get(tier)
    if cap is None:
        return

    cutoff = datetime.utcnow() - timedelta(hours=24)
    count = (
        db.query(ChatMessage)
        .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
        .filter(
            ChatConversation.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= cutoff,
        )
        .count()
    )
    if count < cap:
        return

    _log.info(
        "chat_quota_exhausted user_id=%s tier=%s used=%s cap=%s",
        user_id, tier, count, cap,
    )
    raise upgrade_error(
        "chat_quota_exhausted",
        current_tier=tier,
        current_value=str(count),
        limit_value=str(cap),
        cta_action_override="trial" if tier == "scout" else "upgrade",
    )


# ── Conversation persistence ──────────────────────────────────────────────────


def _get_or_create_conversation(
    db: Session,
    conversation_id: str,
    user_id: str,
    context_type: Optional[str],
    context_payload: Optional[dict],
) -> ChatConversation:
    """Find the conversation by id or create it owned by `user_id`. If the
    id exists but belongs to a different user, raise 403 — we don't want
    cross-user leakage from a guessed UUID."""
    existing = db.get(ChatConversation, conversation_id)
    if existing is not None:
        if existing.user_id != user_id:
            raise HTTPException(status_code=403, detail="Conversation not found.")
        return existing

    conv = ChatConversation(
        id=conversation_id,
        user_id=user_id,
        anon_session_id=None,
        title="New chat",
        context_type=context_type,
        context_payload=context_payload,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _persist_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: Optional[str],
    tool_calls: Optional[list] = None,
    tool_results: Optional[dict] = None,
) -> ChatMessage:
    """Insert one chat_messages row. Returns the persisted ORM row."""
    msg = ChatMessage(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_results=tool_results,
        tokens_in=0,
        tokens_out=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _load_history(db: Session, conversation_id: str, limit: int = 20) -> List[dict]:
    """Load the last `limit` messages from the conversation as OpenAI-shaped
    message dicts (`{"role": ..., "content": ..., "tool_calls": ..., "tool_call_id": ...}`)."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    out: List[dict] = []
    for r in rows:
        msg: dict = {"role": r.role}
        if r.content is not None:
            msg["content"] = r.content
        if r.tool_calls:
            msg["tool_calls"] = r.tool_calls
        if r.role == "tool" and r.tool_results:
            # OpenAI's tool message shape: {"role": "tool", "tool_call_id": "...", "content": "..."}
            msg["tool_call_id"] = r.tool_results.get("call_id", "")
            msg["content"] = r.tool_results.get("content", "")
        out.append(msg)
    return out


# ── SSE helpers ───────────────────────────────────────────────────────────────


def _sse(event_type: str, payload: dict) -> str:
    """Format one SSE frame. Each frame is `data: <json>\\n\\n`. The frontend
    parses the JSON and dispatches on its `type` field."""
    data = json.dumps({"type": event_type, **payload}, default=str)
    return f"data: {data}\n\n"


# ── Tool-dispatch loop ────────────────────────────────────────────────────────


async def _run_tool_loop(
    db: Session,  # legacy positional — see lifecycle note below
    conversation_id: str,
    messages: List[dict],
    max_iterations: int = 5,
    tool_whitelist: Optional[set] = None,
    # Ticket #9 guardrail context. All optional so existing callers
    # remain valid; passing them enables structured event logging.
    user_id: Optional[str] = None,
    anon_session_id: Optional[str] = None,
    tier: str = "unknown",
    user_message: str = "",
) -> AsyncIterator[str]:
    """Core orchestration: call LLM, dispatch tool calls, re-invoke until done.

    **Session lifecycle (post-mortem 2026-05-22 / KNOWN_ISSUES.md):**
    The `db` passed by the route is FastAPI-request-scoped — closed when
    the route handler returns. StreamingResponse runs this generator AFTER
    the handler returns, so `db` is already closed; any ORM op against it
    raises DetachedInstanceError silently inside the ASGI exception handler
    and the SSE body comes out empty (production symptom). We therefore
    open a fresh SessionLocal here and ignore the passed-in `db`. The
    parameter is kept for backwards compat with the existing call sites
    and tests; the local `stream_db` is what actually executes.

    `tool_whitelist`: if provided, only tools whose names are in this set
    are exposed to the LLM AND honored by the dispatcher. The anonymous
    chat passes a restricted set per spec §2.2. Authed chat passes None
    (all tools allowed).

    Guardrail context (ticket #9): user_id / anon_session_id / tier /
    user_message are surfaced in the structured chat_refusal /
    numeric_uncited log lines emitted from `_apply_guardrails`. The
    weekly digest job aggregates from those lines.
    """
    from sqlalchemy.orm import sessionmaker  # local — keeps top-level imports clean

    # Bind the new session to the SAME engine as the caller's `db`. Using
    # `db.get_bind()` rather than the global SessionLocal means tests can
    # drive this loop against their in-memory SQLite engine without any
    # monkey-patching — they pass a Session from the test engine, and we
    # spawn a sibling on the same engine.
    StreamMaker = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, future=True)
    stream_db = StreamMaker()
    try:
        async for frame in _run_tool_loop_inner(
            stream_db, conversation_id, messages,
            max_iterations=max_iterations,
            tool_whitelist=tool_whitelist,
            user_id=user_id, anon_session_id=anon_session_id,
            tier=tier, user_message=user_message,
        ):
            yield frame
    finally:
        stream_db.close()


async def _run_tool_loop_inner(
    db: Session,
    conversation_id: str,
    messages: List[dict],
    *,
    max_iterations: int,
    tool_whitelist: Optional[set],
    user_id: Optional[str],
    anon_session_id: Optional[str],
    tier: str,
    user_message: str,
) -> AsyncIterator[str]:
    """The original loop body. Wrapped in _run_tool_loop above so the
    fresh-session bracket is enforced even when callers forget."""
    gateway = get_llm_gateway()
    all_specs = get_openai_tool_specs()
    if tool_whitelist is None:
        tools = all_specs
    else:
        tools = [s for s in all_specs if s["function"]["name"] in tool_whitelist]

    for iteration in range(max_iterations):
        try:
            events_iter = gateway.chat_completion_with_tools(
                messages=messages,
                tools=tools,
            )
        except LLMAdapterError as exc:
            yield _sse("error", {"message": str(exc), "fatal": True})
            return

        accumulated_text = ""
        tool_calls: List[ChatToolCall] = []
        finish_reason: Optional[str] = None

        try:
            async for event in events_iter:
                if isinstance(event, ChatToken):
                    accumulated_text += event.text
                    yield _sse("token", {"text": event.text})
                elif isinstance(event, ChatToolCall):
                    tool_calls.append(event)
                    yield _sse("tool_call_start", {
                        "call_id": event.call_id,
                        "name": event.name,
                        "arguments": event.arguments,
                    })
                elif isinstance(event, ChatDone):
                    finish_reason = event.finish_reason
        except LLMAdapterError as exc:
            yield _sse("error", {"message": str(exc), "fatal": True})
            return

        # Persist the assistant's contribution this iteration.
        assistant_tool_calls_payload = [
            {
                "id": tc.call_id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in tool_calls
        ] or None
        _persist_message(
            db,
            conversation_id,
            role="assistant",
            content=accumulated_text or None,
            tool_calls=assistant_tool_calls_payload,
        )

        if finish_reason != "tool_calls" or not tool_calls:
            # LLM finished without (or beyond) needing more tools. Run
            # guardrails on the final assistant text before signaling done.
            tool_names = _gather_tool_names_used(messages)
            async for frame in _apply_guardrails(
                db=db,
                conversation_id=conversation_id,
                messages=messages,
                response_text=accumulated_text,
                tool_names_used=tool_names,
                user_id=user_id,
                anon_session_id=anon_session_id,
                tier=tier,
                user_message=user_message,
            ):
                yield frame
            yield _sse("done", {"finish_reason": finish_reason or "stop"})
            return

        # The assistant decided to call tools. Execute each, persist the
        # result as a tool message, append to messages for the next loop iter.
        messages.append({
            "role": "assistant",
            "content": accumulated_text or None,
            "tool_calls": assistant_tool_calls_payload,
        })

        for tc in tool_calls:
            try:
                # Whitelist check: enforce even if the LLM picked a tool we
                # didn't advertise (defense against hallucinated tool names).
                if tool_whitelist is not None and tc.name not in tool_whitelist:
                    raise UnknownToolError(
                        f"Tool '{tc.name}' not available in this context. "
                        f"Allowed: {sorted(tool_whitelist)}"
                    )
                result = await dispatch_tool_call(tc.name, tc.arguments)
                result_text = _serialize_tool_result(result)
            except UnknownToolError as exc:
                result_text = json.dumps({"error": str(exc)})
            except Exception as exc:  # pragma: no cover — defensive
                result_text = json.dumps({"error": f"Tool {tc.name} failed: {exc!r}"})

            _persist_message(
                db,
                conversation_id,
                role="tool",
                content=None,
                tool_results={"call_id": tc.call_id, "content": result_text, "name": tc.name},
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.call_id,
                "content": result_text,
            })
            yield _sse("tool_result", {"call_id": tc.call_id, "name": tc.name})

        # Loop back — LLM will synthesize tool results into a final response.

    # Hit max_iterations without a clean finish. Emit a soft error so the
    # frontend can show a "this is taking a while" message rather than hang.
    yield _sse("error", {
        "message": f"Tool loop exceeded {max_iterations} iterations; check for infinite tool-call recursion.",
        "fatal": True,
    })


def _serialize_tool_result(result: Any) -> str:
    """Convert a tool's return value (Pydantic model, dict, primitive) to a
    JSON string the LLM can consume as the `content` of a tool message."""
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(), default=str)
    return json.dumps(result, default=str)


# ── Guardrails (ticket #9) ────────────────────────────────────────────────────


def _gather_tool_names_used(messages: List[dict]) -> List[str]:
    """Walk the messages list and extract names of tools the assistant called.

    Used as input to the refusal log so we know whether the assistant tried
    a tool path before refusing (vs. blanket-refusing the user)."""
    names: List[str] = []
    for m in messages:
        for tc in m.get("tool_calls") or []:
            name = tc.get("name") or tc.get("function", {}).get("name")
            if name:
                names.append(name)
    return names


async def _apply_guardrails(
    *,
    db: Session,
    conversation_id: str,
    messages: List[dict],
    response_text: str,
    tool_names_used: List[str],
    user_id: Optional[str],
    anon_session_id: Optional[str],
    tier: str,
    user_message: str,
) -> AsyncIterator[str]:
    """Two checks on the final assistant text:

      (a) Refusal classification — if the text matches a known refusal
          shape, emit a structured chat_refusal event. Frontend may use
          the SSE `guardrail` frame to render the refusal styled
          differently.

      (b) Citation enforcement — if the text contains uncited numeric
          claims AND any tools were used this turn, try ONE reprompt
          asking the LLM to add citation chips. If that fails too,
          append a redaction warning to the persisted text and log
          a numeric_uncited event with reprompt_succeeded=False.

    Yields SSE frames for any user-visible guardrail action; the chat
    endpoint streams them inline with the regular `token`/`done` flow.
    """
    # (a) Refusal classification
    refusal_category = classify_refusal(response_text)
    if refusal_category is not None:
        log_refusal_event(
            category=refusal_category,
            user_message=user_message,
            assistant_response=response_text,
            tool_calls_attempted=tool_names_used,
            user_id=user_id,
            anon_session_id=anon_session_id,
            tier=tier,
            conversation_id=conversation_id,
        )
        yield _sse("guardrail", {"action": "refusal_logged", "category": refusal_category})

    # (b) Citation enforcement
    if not tool_names_used:
        # No tools were used this turn → the response is general
        # knowledge / refusal copy, nothing to cite. Skip.
        return

    uncited = detect_uncited_numerics(response_text)
    if not uncited:
        return

    # Try one reprompt.
    rewritten = await attempt_citation_reprompt(
        messages=messages,
        response_text=response_text,
        uncited=uncited,
    )
    if rewritten is not None:
        # Success — replace the persisted assistant message text. The
        # original streamed text is already in the user's terminal/UI;
        # the frontend can refetch on done or re-render from DB.
        last_assistant = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.role == "assistant",
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if last_assistant is not None:
            last_assistant.content = rewritten
            db.commit()
        log_uncited_event(
            uncited=uncited,
            conversation_id=conversation_id,
            reprompt_succeeded=True,
            user_id=user_id,
            anon_session_id=anon_session_id,
            tier=tier,
        )
        yield _sse("guardrail", {
            "action": "citation_reprompt_succeeded",
            "uncited_count": len(uncited),
            "rewritten_text": rewritten,
        })
        return

    # Reprompt failed. Append warning + log event with
    # reprompt_succeeded=False.
    warned = append_redaction_warning(response_text, uncited)
    last_assistant = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == "assistant",
        )
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if last_assistant is not None:
        last_assistant.content = warned
        db.commit()
    log_uncited_event(
        uncited=uncited,
        conversation_id=conversation_id,
        reprompt_succeeded=False,
        user_id=user_id,
        anon_session_id=anon_session_id,
        tier=tier,
    )
    yield _sse("guardrail", {
        "action": "citation_warning_appended",
        "uncited_count": len(uncited),
    })


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: str,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream an assistant response to the user's message via SSE.

    Order of operations:
      1. Daily turn-cap check (raises 402 before any LLM cost).
      2. Conversation create-or-load (ownership check raises 403).
      3. Persist user message FIRST (so it counts toward quota even if the
         LLM errors).
      4. Load history + compose messages with system prompt.
      5. Stream tokens + run tool-dispatch loop.

    The SSE stream emits these event types:
      `token`            — assistant prose chunk
      `tool_call_start`  — assistant decided to call a tool
      `tool_result`      — tool returned, ready for next LLM iteration
      `done`             — terminal event with finish_reason
      `error`            — fatal stream error; client should disable retry
    """
    # 1. Rate limit. Heal orphan-plan users per apps/api/CLAUDE.md rule #9.
    if user.plan is None:  # pragma: no cover — heal path tested in auth
        raise HTTPException(status_code=500, detail="User plan missing — please retry.")
    _check_chat_quota(db, user.id, user.plan.tier)

    # 2. Conversation create-or-load.
    conv = _get_or_create_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
        context_type=body.context_type,
        context_payload=body.context_payload,
    )

    # 3. Persist the user message FIRST so the next quota check sees it.
    _persist_message(db, conv.id, role="user", content=body.content)

    # 4. Build the messages array. System prompt + history (which now
    #    includes the user's new message since we just persisted it).
    history = _load_history(db, conv.id, limit=20)
    messages: List[dict] = [{"role": "system", "content": _system_prompt()}] + history

    # 5. Stream.
    #
    # CRITICAL: snapshot ORM attribute values into plain locals BEFORE the
    # generator yields. The FastAPI-injected `db` session closes when this
    # route handler returns; the streaming generator runs AFTER that, so
    # accessing `conv.id` / `user.id` / `user.plan.tier` inside the generator
    # raises DetachedInstanceError. See KNOWN_ISSUES.md 2026-05-22.
    conv_id_snap = conv.id
    user_id_snap = user.id
    tier_snap = user.plan.tier if user.plan else "unknown"
    user_message_snap = body.content

    async def event_stream() -> AsyncIterator[str]:
        # `started` lets the frontend differentiate "request received" from
        # "first token" (which can be 2-3s on cold cache).
        yield _sse("started", {"conversation_id": conv_id_snap})
        async for frame in _run_tool_loop(
            db, conv_id_snap, messages,
            user_id=user_id_snap,
            tier=tier_snap,
            user_message=user_message_snap,
        ):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )


# ── Anonymous chat (ticket #6) ────────────────────────────────────────────────


def _check_anonymous_chat_quota(session: AnonymousSession) -> None:
    """5-turn cap per AnonymousSession (lifetime, not daily). Raises 402
    with `is_anonymous=true` so the frontend renders the signup CTA inline."""
    if session.chat_turns_used >= ANON_TURN_CAP:
        _log.info(
            "chat_quota_exhausted anonymous session_id=%s used=%s cap=%s",
            session.id, session.chat_turns_used, ANON_TURN_CAP,
        )
        raise upgrade_error(
            "chat_quota_exhausted",
            current_tier=None,
            current_value=str(session.chat_turns_used),
            limit_value=str(ANON_TURN_CAP),
            is_anonymous=True,
            cta_action_override="signup",
        )


def _get_or_create_anon_conversation(
    db: Session,
    conversation_id: str,
    anon_session_id: str,
    context_type: Optional[str],
    context_payload: Optional[dict],
) -> ChatConversation:
    """Anonymous variant of conversation create-or-load. Ownership is keyed
    on `anon_session_id`, not `user_id`. A cookie-rotated visitor effectively
    starts fresh — that's intentional; anon convs are throwaway by design."""
    existing = db.get(ChatConversation, conversation_id)
    if existing is not None:
        if existing.anon_session_id != anon_session_id:
            raise HTTPException(status_code=403, detail="Conversation not found.")
        return existing

    conv = ChatConversation(
        id=conversation_id,
        user_id=None,
        anon_session_id=anon_session_id,
        title="New chat",
        context_type=context_type,
        context_payload=context_payload,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@anonymous_router.post("/conversations/{conversation_id}/messages")
async def post_anonymous_message(
    conversation_id: str,
    body: ChatMessageRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Anonymous chat endpoint. Same SSE protocol as the authed route, but:
      - Cookie-tracked AnonymousSession instead of User+Plan
      - 5-turn lifetime cap (vs daily caps for authed tiers)
      - Tool whitelist: 5 of 7 tools (stock_lookup + backtest_explain excluded)
      - 8K-char input cap (defense-in-depth; the spec quotes 8K tokens but
        char-counting is a cheap and conservative approximation)
      - 402 envelope flags `is_anonymous=true`; cta_action='signup'

    No authentication is required. The anonymous session cookie is created
    on first visit (existing `get_or_create_anonymous_session` flow) and
    persists across pages — so a guest who chatted on Market Pulse and then
    visits a stock page is still the same session.
    """
    # Defense-in-depth: cap input length before any LLM call. Tokens are
    # ~4 chars on average; 8K tokens ≈ 32K chars. We use a hard 8K-char
    # cap as a conservative bound that obviously hits well before token
    # cap (rather than estimating tokens — which depends on the tokenizer).
    if len(body.content) > ANON_TOKEN_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"Anonymous chat input too long ({len(body.content)} chars; cap {ANON_TOKEN_CAP}).",
        )

    session = get_or_create_anonymous_session(request, response, db)

    # 1. Quota.
    _check_anonymous_chat_quota(session)

    # 2. Conversation create-or-load.
    conv = _get_or_create_anon_conversation(
        db,
        conversation_id=conversation_id,
        anon_session_id=session.id,
        context_type=body.context_type,
        context_payload=body.context_payload,
    )

    # 3. Persist user message + bump turn counter BEFORE any LLM call.
    #    Same anti-bypass rationale as the authed route.
    _persist_message(db, conv.id, role="user", content=body.content)
    session.chat_turns_used += 1
    db.commit()

    # 4. Build messages.
    history = _load_history(db, conv.id, limit=20)
    messages: List[dict] = [{"role": "system", "content": _system_prompt()}] + history

    # 5. Stream — same as authed, but with the anon tool whitelist.
    #
    # CRITICAL: snapshot ORM values BEFORE the generator (see authed-route
    # equivalent above + KNOWN_ISSUES.md 2026-05-22 — the request-scoped
    # `db` is closed by the time event_stream() executes, so any ORM
    # attribute read on `session` / `conv` raises DetachedInstanceError
    # and the SSE body comes out empty).
    conv_id_snap = conv.id
    anon_turns_remaining_snap = ANON_TURN_CAP - session.chat_turns_used
    anon_session_id_snap = session.id
    user_message_snap = body.content

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("started", {
            "conversation_id": conv_id_snap,
            "anon_turns_remaining": anon_turns_remaining_snap,
        })
        async for frame in _run_tool_loop(
            db, conv_id_snap, messages,
            tool_whitelist=ANON_TOOL_WHITELIST,
            anon_session_id=anon_session_id_snap,
            tier="anonymous",
            user_message=user_message_snap,
        ):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
