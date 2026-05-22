"""Signal-alert email subscription (Stage 8 v0).

One row per (user, saved_strategy). Row exists iff the user has opted in;
unsubscribe deletes the row.

NOTE: `user_id` intentionally has no ForeignKey("users.id"). Diverges from
build_specs/research_execution_v0_signals_and_alerts.md §4.3 — backend
trap #1 (apps/api/CLAUDE.md): production users.id may be UUID while the
model declares String(36); Postgres rejects the FK at startup. App-layer
enforces ownership in routes/signals.py. Same pattern as SavedStrategy,
WeeklyUsage, AnonymousSession.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SignalAlertSubscription(Base):
    __tablename__ = "signal_alert_subscriptions"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    # User-clicked "I acted on this signal". Timestamp only, no broker integration.
    last_acted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
