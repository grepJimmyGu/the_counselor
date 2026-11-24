"""An option plan a user built and saved.

`user_id` is deliberately not a foreign key to users.id (apps/api/CLAUDE.md,
trap 1).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OptionPlan(Base):
    __tablename__ = "option_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    # The legs as the user saw them, prices included: the app works out cost,
    # the most that can be lost or made, and the breakevens from these.
    legs: Mapped[list] = mapped_column(JSON, nullable=False)
    underlying_price: Mapped[float] = mapped_column(Float, nullable=False)
    # The trading day the plan's prices are from.
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
