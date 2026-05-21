"""Chat conversation and message tables (Stage 7 — Phase 1, Ticket #1).

A `ChatConversation` belongs to **either** an authenticated user (`user_id`)
or an anonymous browser session (`anon_session_id`) — never both, never
neither. The XOR invariant is enforced at the application layer (in the
chat endpoint handler from Ticket #5 / Ticket #6), not at the DB level —
mirrors the simplicity-first stance taken on other Stage 1a tables.

`ChatMessage` rows are append-only and ordered by `created_at` per
conversation. The cascade delete on `conversation_id` exists because
orphaned messages have no meaning. (FK between non-user tables is fine
per `apps/api/CLAUDE.md` rule #1 — same-type both sides.)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChatConversation(Base):
    """Note: user_id and anon_session_id are intentionally NOT FOREIGN KEYS.
    Same reason as every other Stage 1a / community table — production users.id
    type drift made FK constraints fragile (see KNOWN_ISSUES 2026-05-21).
    App-layer enforces both identity AND the XOR invariant (exactly one of
    user_id / anon_session_id is non-null)."""

    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Exactly one of these is set; app-layer enforces.
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    anon_session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    title: Mapped[str] = mapped_column(
        String(120), default="New chat", server_default="New chat", nullable=False
    )

    # Page context the chat was opened in. Values like "workspace",
    # "stock:AAPL", "backtest:abc123", "saved:xyz", "general".
    context_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Free-form payload describing the page state at open time
    # (e.g. the draft strategy JSON for a workspace context).
    context_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ChatMessage(Base):
    """Append-only message log per conversation. role ∈ {'user','assistant','tool'}.
    Assistant rows with tool_calls have null content; tool rows have null content
    + populated tool_results. The (conversation_id, created_at) composite index
    serves the canonical 'load history in order' query."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tool_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    tokens_in: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_chat_messages_conv_created", "conversation_id", "created_at"),
    )
