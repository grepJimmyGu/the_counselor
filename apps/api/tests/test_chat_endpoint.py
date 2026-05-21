"""Integration tests for the chat endpoint (Stage 7 / ticket #5).

Pattern: call the route handler `post_message` directly with constructed args
and a mocked LLM gateway. Same pattern as `tests/test_strategy_storage_auth.py`.

Mocks `get_llm_gateway` to inject a fake whose `chat_completion_with_tools`
returns canned event sequences — that lets us cover the dispatch loop end-
to-end without spinning up the real LLM or any tool subprocess.

What we cover:
  * happy path: text-only stream → user + assistant messages persisted
  * tool dispatch loop: LLM emits ChatToolCall → dispatched → result fed
    back → second LLM iteration produces final text
  * daily-cap rate limit: 21st message of the day from a Scout returns 402
  * conversation ownership: posting to another user's conversation → 403
  * conversation create-on-first-post
  * SSE event ordering: started → token* → done

What we don't cover (deferred):
  * Real LLM + real tool execution — that's verified by ticket #2/#3/#4
    unit tests + manual smoke
  * Anonymous chat — ticket #6
  * Citation enforcement + refusal logging — ticket #9
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.chat import ChatMessageRequest, post_message
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User
from app.services.llm_adapter import ChatDone, ChatToken, ChatToolCall


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_gateway(events_per_iteration: List[List]) -> MagicMock:
    """Build a fake LLMGateway whose chat_completion_with_tools yields
    `events_per_iteration[N]` on the Nth call. Lets one test drive multiple
    LLM iterations (text → tool_call → text)."""
    call_count = {"n": 0}

    def _stream(**_kwargs) -> AsyncIterator:
        events = events_per_iteration[call_count["n"]]
        call_count["n"] += 1

        async def _it():
            for e in events:
                yield e

        return _it()

    gateway = MagicMock()
    gateway.chat_completion_with_tools = _stream
    return gateway


async def _collect_frames(response) -> List[dict]:
    """Iterate a StreamingResponse's body_iterator + parse SSE frames into dicts."""
    frames: List[dict] = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        for line in text.split("\n\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue
            try:
                frames.append(json.loads(line[len("data: "):]))
            except json.JSONDecodeError:
                pass
    return frames


# ── Happy path: text-only stream ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_only_stream_persists_and_emits_events(db: Session, make_user):
    """Single LLM iteration with no tool calls: user msg → assistant text → done.
    Both messages are persisted; SSE emits started, tokens, done in order."""
    user = make_user(email="happy@example.com", password="pw")

    fake = _fake_gateway([[
        ChatToken(text="Hello"),
        ChatToken(text=" world"),
        ChatDone(finish_reason="stop"),
    ]])

    body = ChatMessageRequest(content="Hi there")

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-happy",
            body=body,
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    # Event ordering
    types = [f["type"] for f in frames]
    assert types[0] == "started"
    assert "token" in types
    assert types[-1] == "done"
    # Token frames carry the text
    tokens = [f["text"] for f in frames if f["type"] == "token"]
    assert "".join(tokens) == "Hello world"

    # Persistence — one user msg + one assistant msg
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == "conv-happy")
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Hi there"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Hello world"


# ── Conversation creation + ownership ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversation_created_on_first_post(db: Session, make_user):
    """No existing conversation row → create one owned by the caller."""
    user = make_user(email="newconv@example.com", password="pw")

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-fresh",
            body=ChatMessageRequest(content="first turn"),
            user=user,
            db=db,
        )
        await _collect_frames(response)

    conv = db.get(ChatConversation, "conv-fresh")
    assert conv is not None
    assert conv.user_id == user.id
    assert conv.title == "New chat"


@pytest.mark.asyncio
async def test_conversation_ownership_other_user_rejected(db: Session, make_user):
    """User B cannot post to User A's conversation — returns 403."""
    user_a = make_user(email="alice@example.com", password="pw")
    user_b = make_user(email="bob@example.com", password="pw")

    # Seed a conversation owned by A
    a_conv = ChatConversation(
        id="conv-alice",
        user_id=user_a.id,
        title="Alice's chat",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(a_conv)
    db.commit()

    # B tries to post
    with patch("app.api.routes.chat.get_llm_gateway", return_value=MagicMock()):
        with pytest.raises(HTTPException) as exc:
            await post_message(
                conversation_id="conv-alice",
                body=ChatMessageRequest(content="i'm not alice"),
                user=user_b,
                db=db,
            )

    assert exc.value.status_code == 403


# ── Context passed through on conversation creation ───────────────────────────


@pytest.mark.asyncio
async def test_context_payload_stored_on_new_conversation(db: Session, make_user):
    """Frontend passes context_type/payload on first POST — must be stored."""
    user = make_user(email="ctx@example.com", password="pw")

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])

    body = ChatMessageRequest(
        content="from stock page",
        context_type="stock:AAPL",
        context_payload={"ticker": "AAPL", "as_of": "2026-05-21"},
    )

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        await _collect_frames(
            await post_message(
                conversation_id="conv-ctx",
                body=body,
                user=user,
                db=db,
            )
        )

    conv = db.get(ChatConversation, "conv-ctx")
    assert conv.context_type == "stock:AAPL"
    assert conv.context_payload == {"ticker": "AAPL", "as_of": "2026-05-21"}


# ── Rate limit ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scout_daily_cap_returns_402(db: Session, make_user):
    """A Scout who already sent 20 messages in the last 24h gets 402 on the 21st."""
    user = make_user(email="cap@example.com", password="pw", tier="scout")

    # Seed 20 user-role messages on a conversation owned by `user` in the last hour
    conv = ChatConversation(
        id="conv-cap",
        user_id=user.id,
        title="Capped",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    base_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(20):
        msg = ChatMessage(
            id=f"msg-{i}",
            conversation_id="conv-cap",
            role="user",
            content=f"msg {i}",
            tokens_in=0,
            tokens_out=0,
            created_at=base_time + timedelta(seconds=i),
        )
        db.add(msg)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await post_message(
            conversation_id="conv-cap",
            body=ChatMessageRequest(content="msg 21"),
            user=user,
            db=db,
        )

    assert exc.value.status_code == 402
    detail = exc.value.detail
    assert detail["entitlement"]["code"] == "chat_quota_exhausted"
    assert detail["entitlement"]["cta_action"] == "trial"
    assert detail["entitlement"]["current_value"] == "20"
    assert detail["entitlement"]["limit_value"] == "20"


@pytest.mark.asyncio
async def test_quant_tier_is_unlimited(db: Session, make_user):
    """Quant users bypass the cap entirely — even at 200 historical messages."""
    user = make_user(email="quant@example.com", password="pw", tier="quant")

    # Seed enough messages to exceed Strategist's 100/day; Quant should still pass
    conv = ChatConversation(
        id="conv-quant",
        user_id=user.id,
        title="Quant",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    for i in range(150):
        db.add(ChatMessage(
            id=f"qmsg-{i}",
            conversation_id="conv-quant",
            role="user",
            content="x",
            tokens_in=0,
            tokens_out=0,
            created_at=datetime.now(timezone.utc),
        ))
    db.commit()

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-quant",
            body=ChatMessageRequest(content="more"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    # No 402 raised → quant goes through
    assert frames[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_old_messages_dont_count_toward_24h_cap(db: Session, make_user):
    """Messages from >24h ago shouldn't count — that's a rolling window."""
    user = make_user(email="rolling@example.com", password="pw", tier="scout")

    conv = ChatConversation(
        id="conv-rolling",
        user_id=user.id,
        title="Rolling",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    # 25 messages from 2 days ago — should NOT count
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    for i in range(25):
        db.add(ChatMessage(
            id=f"old-{i}", conversation_id="conv-rolling", role="user",
            content="x", tokens_in=0, tokens_out=0, created_at=old_time,
        ))
    db.commit()

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-rolling",
            body=ChatMessageRequest(content="fresh"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    # 25 old + 1 new = 26 total but only 1 in the last 24h → no cap
    assert frames[-1]["type"] == "done"


# ── Tool dispatch loop ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_call_dispatches_then_loops(db: Session, make_user):
    """LLM emits a tool_call → loop dispatches it → tool result fed back →
    LLM emits final text → done. End-to-end across 2 iterations."""
    user = make_user(email="tool@example.com", password="pw")

    # Iteration 0: LLM decides to call concept_explainer
    # Iteration 1: LLM has the tool result, emits final prose
    fake = _fake_gateway([
        [
            ChatToolCall(call_id="c0", name="concept_explainer", arguments={"concept": "Sharpe Ratio"}),
            ChatDone(finish_reason="tool_calls"),
        ],
        [
            ChatToken(text="Sharpe is "),
            ChatToken(text="risk-adjusted return."),
            ChatDone(finish_reason="stop"),
        ],
    ])

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-tool",
            body=ChatMessageRequest(content="what is sharpe ratio?"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    types = [f["type"] for f in frames]
    assert types[0] == "started"
    assert "tool_call_start" in types
    assert "tool_result" in types
    # Order matters: tool_call_start must come before tool_result
    assert types.index("tool_call_start") < types.index("tool_result")
    # Final text + done
    assert "token" in types
    assert types[-1] == "done"

    # Persistence: user msg + 2 assistant msgs (one per iteration) + 1 tool msg
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == "conv-tool")
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    roles = [m.role for m in msgs]
    assert roles[0] == "user"
    assert "tool" in roles  # tool_result was persisted
    assert roles.count("assistant") == 2  # one per LLM iteration


@pytest.mark.asyncio
async def test_unknown_tool_call_doesnt_crash(db: Session, make_user):
    """LLM hallucinates a tool name → dispatcher raises UnknownToolError →
    tool message gets an error payload → LLM gets the error in its next turn
    and finishes gracefully."""
    user = make_user(email="ghosttool@example.com", password="pw")

    fake = _fake_gateway([
        [
            ChatToolCall(call_id="c0", name="ghost_tool", arguments={}),
            ChatDone(finish_reason="tool_calls"),
        ],
        [
            ChatToken(text="Sorry — I tried a tool that doesn't exist."),
            ChatDone(finish_reason="stop"),
        ],
    ])

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-ghost",
            body=ChatMessageRequest(content="run the ghost tool"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    assert frames[-1]["type"] == "done"
    # Tool error message persisted
    tool_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == "conv-ghost", ChatMessage.role == "tool")
        .all()
    )
    assert len(tool_msgs) == 1
    payload = tool_msgs[0].tool_results
    assert "error" in payload["content"]


@pytest.mark.asyncio
async def test_tool_loop_max_iterations_safety(db: Session, make_user):
    """If the LLM keeps emitting tool_calls (e.g., infinite recursion bug),
    the loop bails out after max_iterations with an error frame rather than
    hanging the connection."""
    user = make_user(email="recursive@example.com", password="pw")

    # LLM perpetually wants to call the same tool — loop should bail at iter cap.
    looping_iteration = [
        ChatToolCall(call_id="c-x", name="concept_explainer", arguments={"concept": "Sharpe Ratio"}),
        ChatDone(finish_reason="tool_calls"),
    ]
    fake = _fake_gateway([looping_iteration] * 20)  # more than max_iterations=5

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_message(
            conversation_id="conv-loop",
            body=ChatMessageRequest(content="trigger loop"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    types = [f["type"] for f in frames]
    assert types[-1] == "error"
    assert "exceeded" in frames[-1]["message"]


# ── LLM error surfacing ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_adapter_error_emits_fatal_error_frame(db: Session, make_user):
    """If the LLM gateway raises LLMAdapterError (no provider, HTTP failure),
    the SSE stream emits a fatal error frame so the frontend disables retry."""
    from app.services.llm_adapter import LLMAdapterError

    user = make_user(email="noprovider@example.com", password="pw")

    def _raise(**_kwargs):
        raise LLMAdapterError("Provider not configured")

    gateway = MagicMock()
    gateway.chat_completion_with_tools = _raise

    with patch("app.api.routes.chat.get_llm_gateway", return_value=gateway):
        response = await post_message(
            conversation_id="conv-noprov",
            body=ChatMessageRequest(content="hi"),
            user=user,
            db=db,
        )
        frames = await _collect_frames(response)

    error_frames = [f for f in frames if f["type"] == "error"]
    assert len(error_frames) == 1
    assert error_frames[0]["fatal"] is True
    assert "Provider not configured" in error_frames[0]["message"]
