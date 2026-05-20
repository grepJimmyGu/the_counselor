"""Saved strategy (Stage 1a, Path A).

Replaces the PRD-02 mechanism of storing saved strategies as `backtests` rows
with `slug != null`. A SavedStrategy is the canonical user-owned strategy
definition; `backtest_record_id` points at the most recent run (the existing
`backtests` table continues to store run results).

Scout-tier saves are forced public by the service layer (see saved_strategy_service.py).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SavedStrategy(Base):
    __tablename__ = "saved_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Optional FK to the most recent backtest run for this strategy.
    # String(64) matches BacktestRecord.id.
    backtest_record_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("backtests.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
