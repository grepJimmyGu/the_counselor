"""Per-ticker signal alert subscription (PRD-28).

Alerts before this were basket-scoped: `monitor_saved_screens` (PRD-23c)
notifies when ANY new name enters a saved screen. That's the wrong shape for a
user who cares about ONE name — they get 40 notifications about other stocks
and, critically, **nothing when their name drops out** (the screen cron records
exits but deliberately doesn't notify them).

This table is "tell me when THIS symbol changes state under THIS screen's
reading" — and it notifies in **both** directions.

Scoped to a saved screen (Mr Gu's call, 2026-07-30) rather than the "default
template" the PRD assumed: no default-template object exists in the codebase,
whereas saved screens, their rules, and their maintained basket membership all
ship. It also means `saved_screen_id` is a real `saved_strategies.id` — screens
are stored as SavedStrategy rows with `kind="screen"` — so the existing
`SignalEvent` (non-null FK to saved_strategies) can be reused verbatim.

`user_id` intentionally carries NO ForeignKey — production `users.id` may be
UUID-typed and Postgres rejects mismatched FK types (backend CLAUDE.md trap #1).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TickerSignalSubscription(Base):
    __tablename__ = "ticker_signal_subscriptions"

    # Composite PK: one subscription per (user, symbol, screen). Subscribing
    # twice is a no-op rather than a duplicate notification.
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    # FK is safe here — both sides have always been VARCHAR(36).
    saved_screen_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        primary_key=True,
    )

    email_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    # Last state the monitor observed, so it can emit on TRANSITION only.
    # None = never evaluated; the first pass records state without notifying
    # (otherwise every new subscription would fire immediately).
    last_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    last_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
