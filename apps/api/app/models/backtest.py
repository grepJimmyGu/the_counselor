from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BacktestRecord(Base):
    __tablename__ = "backtests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_type: Mapped[str] = mapped_column(String(64), index=True)
    strategy_name: Mapped[str] = mapped_column(String(255))
    result_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Owner — added at the DB level by startup migrations during Stage 1.
    # Nullable because anonymous one-shot runs (Stage 1a) create rows before
    # any user exists; merge_anonymous_into_user sets this on signup.
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # Strategy storage (PRD-02) — superseded by SavedStrategy model in Stage 1a.
    # Kept on the row for legacy reads; new saves write to saved_strategies.
    slug: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_backtests_slug_unique", "slug", unique=True, postgresql_where=~(slug.is_(None))),  # type: ignore[arg-type]
    )
