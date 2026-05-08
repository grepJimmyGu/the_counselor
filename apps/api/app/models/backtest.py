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

    # Strategy storage (PRD-02)
    slug: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_backtests_slug_unique", "slug", unique=True, postgresql_where=~(slug.is_(None))),  # type: ignore[arg-type]
    )
