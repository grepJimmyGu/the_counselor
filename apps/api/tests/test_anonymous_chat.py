"""Integration tests for the anonymous chat endpoint (Stage 7 / ticket #6).

Same call-handler-directly pattern as test_chat_endpoint.py. Mocks the LLM
gateway with canned event streams + uses the existing in-memory SQLite fixture.

Coverage:
  * 5-turn cap returns 402 with is_anonymous=true and cta_action='signup'
  * Tool whitelist: 5 allowed tools, 2 excluded (stock_lookup, backtest_explain)
  * Excluded tool requested by hallucinating LLM → caught at dispatcher
  * Conversation cross-session isolation (anon A can't see anon B's conv)
  * Signup merge re-attributes the conv to the new user_id
  * 8K-char input cap rejects long inputs as 400
  * chat_turns_used counter increments
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncIterator, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.routes.chat import (
    ANON_TOKEN_CAP,
    ANON_TOOL_WHITELIST,
    ANON_TURN_CAP,
    ChatMessageRequest,
    post_anonymous_message,
)
from app.models.anonymous_session import AnonymousSession
from app.models.chat import ChatConversation, ChatMessage
from app.services.anonymous_service import merge_anonymous_into_user
from app.services.llm_adapter import ChatDone, ChatToken, ChatToolCall


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_anon_session(db: Session, turns_used: int = 0) -> AnonymousSession:
    """Persist an AnonymousSession ready for chat. Tests bypass the cookie
    creation by inserting directly."""
    session = AnonymousSession(
        id=f"anon-{turns_used}-{datetime.utcnow().timestamp()}",
        ip_first_seen="127.0.0.1",
        ip_last_seen="127.0.0.1",
        user_agent="pytest",
        locale="en",
        chat_turns_used=turns_used,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _fake_request_with_session(session_id: str) -> Request:
    """Build a minimal Request whose cookie matches our AnonymousSession id —
    enough for get_or_create_anonymous_session to find it without creating one.

    Cookie name MUST match the COOKIE_NAME constant in anonymous_service.py
    (currently `livermore_anon_id`). A mismatch makes the lookup fail and
    the service creates a fresh session instead — easy to miss in test output."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/anonymous/chat/conversations/x/messages",
        "headers": [
            (b"cookie", f"livermore_anon_id={session_id}".encode()),
            (b"user-agent", b"pytest"),
            (b"accept-language", b"en"),
        ],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def _fake_response() -> Response:
    return Response()


def _fake_gateway(events_per_iteration: List[List]) -> MagicMock:
    """Reuses the same pattern as test_chat_endpoint.py — different file
    deliberately to keep test fixtures co-located with their consumers."""
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
    gateway._spy_calls = _kwargs_recorder = []  # type: ignore[attr-defined]
    return gateway


async def _collect_frames(response) -> List[dict]:
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


# ── Quota ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anon_5th_turn_succeeds_6th_raises_402(db: Session):
    """Anonymous gets exactly ANON_TURN_CAP turns. The cap-th attempt fires 402.
    Per spec §2: 5 turns. After that, signup CTA."""
    session = _make_anon_session(db, turns_used=ANON_TURN_CAP)

    with pytest.raises(HTTPException) as exc:
        await post_anonymous_message(
            conversation_id="conv-cap",
            body=ChatMessageRequest(content="6th attempt"),
            request=_fake_request_with_session(session.id),
            response=_fake_response(),
            db=db,
        )

    assert exc.value.status_code == 402
    detail = exc.value.detail
    assert detail["entitlement"]["code"] == "chat_quota_exhausted"
    assert detail["entitlement"]["is_anonymous"] is True
    assert detail["entitlement"]["cta_action"] == "signup"
    assert detail["entitlement"]["limit_value"] == str(ANON_TURN_CAP)


@pytest.mark.asyncio
async def test_anon_turn_counter_increments_on_each_turn(db: Session):
    """Each successful turn bumps `chat_turns_used` by 1."""
    session = _make_anon_session(db, turns_used=0)

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        await _collect_frames(
            await post_anonymous_message(
                conversation_id="conv-counter",
                body=ChatMessageRequest(content="hi"),
                request=_fake_request_with_session(session.id),
                response=_fake_response(),
                db=db,
            )
        )

    db.refresh(session)
    assert session.chat_turns_used == 1


# ── Tool whitelist ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anon_tool_whitelist_filters_excluded_tools(db: Session):
    """The gateway should be passed ONLY whitelisted tools. Capture and verify."""
    session = _make_anon_session(db)

    captured_kwargs = {}

    async def _capture(**kwargs):
        captured_kwargs.update(kwargs)
        async def _gen():
            yield ChatToken(text="ok")
            yield ChatDone(finish_reason="stop")
        async for e in _gen():
            yield e

    gateway = MagicMock()
    gateway.chat_completion_with_tools = _capture

    with patch("app.api.routes.chat.get_llm_gateway", return_value=gateway):
        await _collect_frames(
            await post_anonymous_message(
                conversation_id="conv-whitelist",
                body=ChatMessageRequest(content="what tools do I have"),
                request=_fake_request_with_session(session.id),
                response=_fake_response(),
                db=db,
            )
        )

    tool_names = {s["function"]["name"] for s in captured_kwargs["tools"]}
    assert tool_names == ANON_TOOL_WHITELIST
    # Specifically the two excluded ones are gone:
    assert "stock_lookup" not in tool_names
    assert "backtest_explain" not in tool_names


@pytest.mark.asyncio
async def test_anon_hallucinated_excluded_tool_caught_by_dispatcher(db: Session):
    """If the LLM hallucinates an excluded tool (e.g., stock_lookup), the
    dispatcher must refuse it even though the tool is registered globally."""
    session = _make_anon_session(db)

    fake = _fake_gateway([
        [
            ChatToolCall(call_id="c0", name="stock_lookup", arguments={"ticker": "AAPL"}),
            ChatDone(finish_reason="tool_calls"),
        ],
        [
            ChatToken(text="I can't do that anonymously."),
            ChatDone(finish_reason="stop"),
        ],
    ])

    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        response = await post_anonymous_message(
            conversation_id="conv-ghosttool",
            body=ChatMessageRequest(content="look up AAPL"),
            request=_fake_request_with_session(session.id),
            response=_fake_response(),
            db=db,
        )
        frames = await _collect_frames(response)

    # Tool message should carry the whitelist-rejection error
    tool_msgs = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == "conv-ghosttool",
        ChatMessage.role == "tool",
    ).all()
    assert len(tool_msgs) == 1
    assert "not available" in tool_msgs[0].tool_results["content"]
    # The conversation continued — done event came through
    assert frames[-1]["type"] == "done"


# ── Cross-session isolation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anon_cannot_access_other_session_conversation(db: Session):
    """Anon A creates conv. Anon B (different cookie) tries to post to the
    same conv id — returns 403."""
    session_a = _make_anon_session(db)
    session_b = _make_anon_session(db)

    # Seed a conversation owned by A
    conv = ChatConversation(
        id="conv-anon-a",
        user_id=None,
        anon_session_id=session_a.id,
        title="Anon A",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await post_anonymous_message(
            conversation_id="conv-anon-a",
            body=ChatMessageRequest(content="i'm not anon a"),
            request=_fake_request_with_session(session_b.id),
            response=_fake_response(),
            db=db,
        )

    assert exc.value.status_code == 403


# ── Token cap ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anon_oversize_input_rejected(db: Session):
    """Input over ANON_TOKEN_CAP chars is rejected before any LLM call."""
    session = _make_anon_session(db)

    huge_input = "x" * (ANON_TOKEN_CAP + 1)

    with pytest.raises(HTTPException) as exc:
        await post_anonymous_message(
            conversation_id="conv-huge",
            body=ChatMessageRequest(content=huge_input),
            request=_fake_request_with_session(session.id),
            response=_fake_response(),
            db=db,
        )

    assert exc.value.status_code == 400
    assert "too long" in exc.value.detail.lower()

    # Quota counter unchanged — the rejection happens BEFORE any persistence
    db.refresh(session)
    assert session.chat_turns_used == 0


# ── Signup merge ──────────────────────────────────────────────────────────────


def test_merge_anonymous_into_user_reattributes_chat_conversations(db: Session, make_user):
    """After signup, anonymous conversations should belong to the new user.
    Verify directly against the merge function."""
    user = make_user(email="merge-anon@example.com", password="pw")

    session = _make_anon_session(db)
    # Create 2 anon conversations
    for i in range(2):
        db.add(ChatConversation(
            id=f"conv-merged-{i}",
            user_id=None,
            anon_session_id=session.id,
            title=f"Anon {i}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
    db.commit()

    merge_anonymous_into_user(db, session, user.id)

    # Both conversations now belong to the user; anon_session_id retained for history
    for i in range(2):
        conv = db.get(ChatConversation, f"conv-merged-{i}")
        assert conv.user_id == user.id
        assert conv.anon_session_id == session.id  # kept for audit


def test_merge_is_idempotent_on_chat(db: Session, make_user):
    """Re-running merge is a no-op (existing convs already attributed)."""
    user = make_user(email="merge-idem@example.com", password="pw")
    session = _make_anon_session(db)
    db.add(ChatConversation(
        id="conv-idem",
        user_id=None,
        anon_session_id=session.id,
        title="x",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    db.commit()

    merge_anonymous_into_user(db, session, user.id)
    merge_anonymous_into_user(db, session, user.id)  # second call: no-op

    conv = db.get(ChatConversation, "conv-idem")
    assert conv.user_id == user.id


# ── started frame carries remaining count ────────────────────────────────────


@pytest.mark.asyncio
async def test_started_frame_shows_anon_turns_remaining(db: Session):
    """Frontend wants to render '3 of 5 free turns left' — the started frame
    must include the remaining count AFTER the current turn is counted."""
    session = _make_anon_session(db, turns_used=2)

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        frames = await _collect_frames(
            await post_anonymous_message(
                conversation_id="conv-started",
                body=ChatMessageRequest(content="hi"),
                request=_fake_request_with_session(session.id),
                response=_fake_response(),
                db=db,
            )
        )

    started = next(f for f in frames if f["type"] == "started")
    # Was 2, now 3 used → 5 - 3 = 2 remaining
    assert started["anon_turns_remaining"] == 2


# ── Cookie propagation regression (2026-05-23) ────────────────────────────────


@pytest.mark.asyncio
async def test_anon_session_cookie_set_on_streaming_response(db: Session):
    """Regression: FastAPI discards the injected `Response` when the route
    returns a `StreamingResponse`. Any `Set-Cookie` set on the injected
    Response by `get_or_create_anonymous_session` is silently dropped,
    every subsequent POST mints a fresh AnonymousSession, conversation
    ownership check returns 403 "Conversation not found."

    Fix: `_propagate_cookies` copies raw Set-Cookie headers from the
    injected Response onto the StreamingResponse before returning.

    Regression mechanic: send a FRESH request (no cookie). The injected
    Response should get its Set-Cookie populated, and after our fix, the
    StreamingResponse we return must carry that cookie too."""
    # No existing session — force creation
    fresh_request_scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/anonymous/chat/conversations/conv-fresh/messages",
        "headers": [
            (b"user-agent", b"pytest"),
            (b"accept-language", b"en"),
        ],
        "client": ("127.0.0.1", 12345),
    }
    fresh_request = Request(fresh_request_scope)
    fresh_response = Response()

    fake = _fake_gateway([[ChatToken(text="ok"), ChatDone(finish_reason="stop")]])
    with patch("app.api.routes.chat.get_llm_gateway", return_value=fake):
        streaming = await post_anonymous_message(
            conversation_id="conv-fresh-cookie",
            body=ChatMessageRequest(content="hi"),
            request=fresh_request,
            response=fresh_response,
            db=db,
        )

    # The injected `fresh_response` should have a Set-Cookie for the new
    # anon session (proves get_or_create_anonymous_session ran).
    injected_cookies = [
        v for k, v in fresh_response.raw_headers if k.lower() == b"set-cookie"
    ]
    assert len(injected_cookies) >= 1, "anon session helper didn't set a cookie"
    assert b"livermore_anon_id=" in injected_cookies[0]

    # CRITICAL: that Set-Cookie must also be on the StreamingResponse the
    # browser actually receives. Without _propagate_cookies this list is empty.
    streaming_cookies = [
        v for k, v in streaming.raw_headers if k.lower() == b"set-cookie"
    ]
    assert len(streaming_cookies) >= 1, (
        "StreamingResponse missing Set-Cookie — cookie propagation regressed. "
        "Browser will mint fresh anon session each turn → 403 on turn 2."
    )
    assert b"livermore_anon_id=" in streaming_cookies[0]
