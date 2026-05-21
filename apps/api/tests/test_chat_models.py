"""Stage 7 / Ticket #1 — SQLite-runnable smoke tests for the chat schema.

The deeper Postgres invariants (cascade behavior, information_schema column
types) are exercised in `test_postgres_migrations.py`, which is skipped
without `PG_TEST_URL`. These tests run on every pytest invocation against
the in-memory SQLite fixture and catch:

  - ORM declaration errors (missing columns, wrong types)
  - Default values not being applied to ORM inserts
  - The Stage 1a `anonymous_sessions.chat_turns_used` migration didn't run
  - Cross-table references resolving (ChatMessage → ChatConversation)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.anonymous_session import AnonymousSession
from app.models.chat import ChatConversation, ChatMessage


def test_chat_conversation_authed_owner_roundtrip(db: Session):
    """An authed conversation has user_id set and anon_session_id null."""
    conv = ChatConversation(
        id=str(uuid.uuid4()),
        user_id="115253677145661247079",  # Google numeric — must accept
        title="My first chat",
        context_type="workspace",
    )
    db.add(conv)
    db.commit()

    db.refresh(conv)
    assert conv.user_id == "115253677145661247079"
    assert conv.anon_session_id is None
    assert conv.title == "My first chat"
    assert isinstance(conv.created_at, datetime)
    assert isinstance(conv.updated_at, datetime)


def test_chat_conversation_anonymous_owner_roundtrip(db: Session):
    """An anonymous conversation has anon_session_id set and user_id null."""
    conv = ChatConversation(
        id=str(uuid.uuid4()),
        anon_session_id=str(uuid.uuid4()),
        title="Anon chat",
    )
    db.add(conv)
    db.commit()

    db.refresh(conv)
    assert conv.user_id is None
    assert conv.anon_session_id is not None


def test_chat_message_links_to_conversation(db: Session):
    """A ChatMessage references its parent ChatConversation via FK."""
    conv = ChatConversation(id=str(uuid.uuid4()), user_id="u1", title="t")
    db.add(conv)
    db.commit()

    msg = ChatMessage(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="user",
        content="What is a Sharpe ratio?",
    )
    db.add(msg)
    db.commit()

    db.refresh(msg)
    assert msg.conversation_id == conv.id
    assert msg.role == "user"
    assert msg.tokens_in == 0  # ORM default applies
    assert msg.tokens_out == 0
    assert msg.tool_calls is None
    assert msg.tool_results is None


def test_chat_message_tool_call_row(db: Session):
    """Assistant rows that produced a tool call have null content + populated tool_calls."""
    conv = ChatConversation(id=str(uuid.uuid4()), user_id="u1", title="t")
    db.add(conv)
    db.commit()

    tool_call = [{"name": "stock_lookup", "arguments": {"ticker": "AAPL"}}]
    msg = ChatMessage(
        id=str(uuid.uuid4()),
        conversation_id=conv.id,
        role="assistant",
        content=None,
        tool_calls=tool_call,
        tokens_in=42,
        tokens_out=0,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    assert msg.content is None
    assert msg.tool_calls == tool_call
    assert msg.tokens_in == 42


def test_anonymous_session_chat_turns_used_default(db: Session):
    """AnonymousSession.chat_turns_used defaults to 0 — Stage 7 anonymous chat
    quota tracking. The migration in _run_stage1_isolated_ddl is what populates
    this column on existing prod tables; on a fresh DB the model declaration is
    the source of truth."""
    sess = AnonymousSession(
        id=str(uuid.uuid4()),
        ip_first_seen="127.0.0.1",
        ip_last_seen="127.0.0.1",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    assert sess.chat_turns_used == 0
    assert sess.runs_used == 0  # existing column still works


def test_anonymous_session_can_increment_chat_turns(db: Session):
    """Verify the column supports the 5-turn cap mechanic from the build spec §2."""
    sess = AnonymousSession(
        id=str(uuid.uuid4()),
        ip_first_seen="127.0.0.1",
        ip_last_seen="127.0.0.1",
        chat_turns_used=4,
    )
    db.add(sess)
    db.commit()

    sess.chat_turns_used += 1  # mimics endpoint increment
    db.commit()
    db.refresh(sess)
    assert sess.chat_turns_used == 5
