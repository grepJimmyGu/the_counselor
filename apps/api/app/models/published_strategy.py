"""Published strategy (Stage 4).

A frozen, public copy of a saved strategy. Decoupled from `saved_strategies` so
users can edit their saved version without subsequent edits leaking out to the
published snapshot.

Scout-tier saves auto-publish to this table (Stage 1a's
`saved_strategies_always_public=True` extended to also create a published row).
Strategist+ may save without publishing.

Note: user_id is intentionally NOT a FOREIGN KEY to users.id (lesson from
Stage 1a — production users.id may be UUID and would crash Base.metadata.create_all
on type mismatch). App-layer enforces user identity.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PublishedStrategy(Base):
    __tablename__ = "published_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Strategy payload (frozen at publish time)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Optional link to the backtest run that produced these results.
    backtest_record_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Snapshot fields so feed/detail don't need to re-run backtests.
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    universe_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    benchmark_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Optional snapshot of equity_curve points for /s/[slug] chart rendering.
    # JSON array of {date: str, equity: float, benchmark: float}; capped at
    # ~150 monthly points so the snapshot stays small.
    equity_curve_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # State
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    locale: Mapped[str] = mapped_column(
        String(8), default="en", server_default="en", nullable=False,
    )

    # Counts (denormalized for feed performance)
    follow_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    like_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    comment_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    view_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        onupdate=datetime.utcnow, nullable=False,
    )
