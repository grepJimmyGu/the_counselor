"""The portfolio agent's per-user settings and what it has found.

`user_id` is deliberately not a foreign key to users.id (apps/api/CLAUDE.md,
trap 1).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentProfile(Base):
    """How one user wants their agent to work."""

    __tablename__ = "agent_profiles"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Off until the user turns it on: watching someone's holdings around the
    # clock is something they ask for, not something they discover.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The symbols to watch. The app keeps its watchlist on the device, so it
    # sends the list here; without that nothing could be watched while the
    # app is closed.
    watchlist: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # A day's move, in percent, big enough to be told about.
    move_alert_pct: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    # The most one holding may be of the portfolio, in percent.
    max_position_pct: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)
    # Email what a scheduled check finds. The app cannot be reached while it
    # is closed, so without this the user learns nothing until they open it.
    email_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # The user's own words about how they invest. Given to the agent in chat.
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AgentInsight(Base):
    """One thing the agent found and told the user about."""

    __tablename__ = "agent_insights"
    # One row per finding. The same fact found again on the next scan is the
    # same row, so a dismissed insight stays dismissed.
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_agent_insight_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # The numbers the title and body were written from.
    facts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # What the app should open if the user wants to act, or null.
    action: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
