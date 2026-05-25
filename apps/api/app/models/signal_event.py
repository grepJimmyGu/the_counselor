"""Signal-change event log (Stage 8 v0).

Append-only. One row per signal *change* — the cron writes here when the
recomputed signal differs from the cached state. Drives the signal-history
drawer (Phase C) and the alert-email dispatch (Phase B).

See build_specs/research_execution_v0_signals_and_alerts.md §4.2.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, DateTime, Date, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SignalEvent(Base):
    __tablename__ = "signal_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # FK to saved_strategies.id is safe (both String(36)).
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_signal: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    previous_signal_display: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    new_signal: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_signal_display: Mapped[str] = mapped_column(String(280), nullable=False)
    # "flip_to_cash" | "flip_to_long" | "rotation" | "rebalance"
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    # {"NVDA": 145.23, "SPY": 412.10} — close prices on the signal date.
    reference_price_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    # Phase B fills these when the email send fires.
    email_dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_dispatch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
