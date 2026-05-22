"""Saved-strategy current signal cache (Stage 8 v0).

One row per saved strategy. Populated lazily — by the daily recompute cron
(Phase B) or by the GET signal endpoint on first read post-deploy. Holds the
strategy's *current* position derived from a re-run of the backtest engine
against today's cached price data.

`current_signal` shape is free-form JSON keyed off strategy_type — see
build_specs/research_execution_v0_signals_and_alerts.md §4.1 for examples.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, DateTime, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SavedStrategySignalState(Base):
    __tablename__ = "saved_strategy_signal_states"

    # FK to saved_strategies.id is safe — both columns are String(36).
    # The users.id FK trap (backend CLAUDE.md #1) only applies to user_id columns.
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    current_signal: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_signal_display: Mapped[str] = mapped_column(String(280), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
