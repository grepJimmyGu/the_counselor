"""Weekly usage counter (Stage 1a).

Stage 1 created `monthly_usage` for slow-cumulative counters (saved strategies,
lifetime totals). This table tracks the Scout 5-runs-per-week meter — a faster
reset cadence that gives Scouts ~4× more compute than the original 5/month cap.

`monthly_usage.backtest_runs` is now legacy (kept populated for backwards
compatibility with Stage 2 reports) but is NOT consulted by entitlement gating.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import String, Date, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WeeklyUsage(Base):
    """One row per (user_id, week_start). week_start = Monday UTC."""

    __tablename__ = "weekly_usage"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)

    # Total runs (custom + template) — useful for reporting; not gated on.
    backtest_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Only this counter is gated on. Templates are unlimited regardless of tier.
    custom_backtest_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Reported separately so analytics can split template vs custom adoption.
    template_backtest_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_weekly_usage_week", "week_start"),
    )
