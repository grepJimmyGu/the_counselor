"""PRD-16c-3 — PositionState ORM.

Per-symbol per-strategy live-trading state. Active-execution strategies
(those configured with `bar_resolution != 'daily'`) maintain one row per
open position. The intraday monitor cron mutates these as it walks the
multi-tier exit ladder; the live dashboard reads them to render
distance-to-stop / distance-to-TP1 / distance-to-TP2 cards.

Lifecycle:
  1. Strategy fires an entry rule → cron creates row with
     `is_open=True`, snapshots entry_price + shares_initial.
  2. Each subsequent tick: cron computes pct_change from entry; if a
     tier triggers, appends a `{event, timestamp, price, shares_sold}`
     dict to `trade_log` and either zeros `shares_remaining` (sell_all)
     or decrements it (sell_fraction).
  3. Final exit closes the row: `is_open=False`, `closed_at`,
     `final_pnl` snapshot.

The `trade_log` JSON column lets the dashboard render the chronological
event sequence without joining to a separate trade-events table. For
v1 the log is bounded by exit_ladder length + entry — typically ≤4
events per position — so JSON is the right shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PositionState(Base):
    """One row per open or recently-closed position."""

    __tablename__ = "position_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # FK is SAFE here — both columns are String(36). user_id intentionally
    # not stored on this table; it's reachable via SavedStrategy.user_id
    # (one extra join) and avoiding it dodges the FK-mismatch trap.
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    shares_initial: Mapped[float] = mapped_column(Float, nullable=False)
    shares_remaining: Mapped[float] = mapped_column(Float, nullable=False)
    # trade_log: list of {event, timestamp, price, shares_sold|shares} dicts.
    # Default = [] via lambda (mutable default avoidance — SQLAlchemy
    # evaluates `default` per-row).
    trade_log: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    is_open: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    final_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        # The monitor cron queries "give me all open positions for this
        # strategy" every 5 minutes. Compound index makes that O(log n).
        Index(
            "idx_position_open_per_strategy",
            "saved_strategy_id",
            "is_open",
        ),
    )
