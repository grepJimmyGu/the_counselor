"""Screen basket membership (PRD-23c).

Tracks, per saved *screen* (a `SavedStrategy` whose `strategy_json.kind ==
"screen"`), which symbols are currently in its matched basket plus the full
entrant/exit history. Append-only lifecycle rows:

  - A symbol entering the basket inserts a row with `entered_date` set and
    `exited_date == NULL` (currently a member).
  - A symbol leaving sets `exited_date` on its current row.
  - A re-entry after an exit inserts a NEW row (the prior one keeps its
    `exited_date`), so the history captures every distinct stint.

"Current basket" = rows for the screen with `exited_date IS NULL`. The
`monitor_saved_screens` cron diffs the latest scan against the current
members; each new entrant is notified once via the PRD-19 dispatcher.

`saved_strategy_id` FK → `saved_strategies.id` is safe: both are
`VARCHAR(36)` (same rule as `SavedStrategy.backtest_record_id` → backtests).
No FK to users (trap #1).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ScreenBasketMember(Base):
    __tablename__ = "screen_basket_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Both dates are anchored to the scan's `as_of_date` (the snapshot date),
    # not wall-clock "today", so membership is authoritative to the data.
    entered_date: Mapped[date] = mapped_column(Date, nullable=False)
    exited_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
