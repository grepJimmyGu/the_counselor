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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.entitlement_errors import upgrade_error
from app.db.session import get_db
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User
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
_log = logging.getLogger("livermore.chat")


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
    db: Session,
    conversation_id: str,
    messages: List[dict],
    max_iterations: int = 5,
) -> AsyncIterator[str]:
    """Core orchestration: call LLM, dispatch tool calls, re-invoke until done.

    Yields SSE-formatted strings. Persists each assistant + tool message to
    chat_messages as the loop progresses. Caps at `max_iterations` to prevent
    a runaway tool-call chain (LLM accidentally calls the same tool in a loop).
    """
    gateway = get_llm_gateway()
    tools = get_openai_tool_specs()

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
            # LLM finished without (or beyond) needing more tools.
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
    async def event_stream() -> AsyncIterator[str]:
        # `started` lets the frontend differentiate "request received" from
        # "first token" (which can be 2-3s on cold cache).
        yield _sse("started", {"conversation_id": conv.id})
        async for frame in _run_tool_loop(db, conv.id, messages):
            yield frame

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )
