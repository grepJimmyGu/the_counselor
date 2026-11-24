"""In-app notification banner row — PRD-19 (Phase B re-shape).

One row per pending notification displayed on the Home + Strategy Builders
banner. Acknowledged entries are soft-deleted (acknowledged_at is set).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class NotificationBannerEntry(Base):
    __tablename__ = "notification_banner_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(280), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    # The SavedStrategy.id of the strategy or screen that sent it (the name
    # predates screens; it has always held the id). None on intraday exit
    # rows written before 2026-08-18.
    strategy_slug: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # What sent it and how much it matters (2026-11-23). Null on rows written
    # before then; `notice_inbox.classify` works them out on read.
    #   source_kind: strategy | screen | stock_alert | position
    #   level:       act | changed | fyi
    source_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    level: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
