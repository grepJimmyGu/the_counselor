"""MarkAsExecutedEvent — user-attested signal action log (PRD-19).

Append-only. One row per user-click on the "Mark as executed" button —
the retention metric loop. Latency from the linked SignalEvent's
`created_at` to this row's `executed_at` is the load-bearing number
Sprint A is trying to measure (see HANDOFF §7).

**Why a new table** (vs reusing SignalEvent): SignalEvent is system-
emitted (cron writes when a signal flips). MarkAsExecutedEvent is
user-emitted (user clicks a button). Mixing them muddles the
schema and prevents simple "did the user act on THIS specific event"
queries. The FK link from `signal_event_id` keeps the join cheap.

**Compliance note**: this is a user attestation, NOT a Livermore claim
of trade placement. The PRD compliance §"Mark-as-Executed event is
user-attested only" is enforced by naming + UX, not by schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MarkAsExecutedEvent(Base):
    __tablename__ = "mark_as_executed_events"

    # PK — String(36) per trap #2 (Uuid(as_uuid=False) stores hex without
    # hyphens, breaks raw SQL lookups).
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # NO FK to users.id — trap #1. App-layer enforces user identity by
    # cross-referencing against the request's authenticated user.
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # FK to signal_events.id is safe — both String(36).
    signal_event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("signal_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalized for fast "what strategy is this about?" lookups without
    # always joining through signal_events. Matches the parent
    # signal_events.saved_strategy_id.
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When the user clicked "Mark as executed". Retention metric source:
    # `executed_at - signal_event.created_at` is the latency we're measuring.
    executed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Optional free-text note ("filled at 4:05 via Schwab"). Bounded to
    # 560 chars per PRD §4 to keep email-embed previews sane.
    user_note: Mapped[Optional[str]] = mapped_column(String(560), nullable=True)
