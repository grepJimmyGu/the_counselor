"""A strategy or screen the user has silenced (2026-11-23).

One row per (user, source). While it exists, that source's notices arrive
already read and its signal-change emails are not sent. Exits on a held
position are never silenced: they are decisions about real money.

`user_id` carries no ForeignKey (backend CLAUDE.md trap #1). `source_id` is a
`saved_strategies.id`; deleting the strategy leaves a harmless orphan row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class NoticeMute(Base):
    __tablename__ = "notice_mutes"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
