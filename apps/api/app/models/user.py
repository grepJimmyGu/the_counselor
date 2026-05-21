from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import String, DateTime, Date, Integer, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    handle: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    # Password auth — null for OAuth-only accounts
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # OAuth — null for password-only accounts
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    oauth_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["Plan"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    usage: Mapped[List["MonthlyUsage"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("oauth_provider", "oauth_subject", name="uq_users_oauth"),
    )


class Plan(Base):
    """One row per user. tier ∈ {'scout', 'strategist', 'quant'}.
    Stage 2 populates stripe_* fields."""
    __tablename__ = "plans"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tier: Mapped[str] = mapped_column(String(16), default="scout", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    billing_cycle: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    # Stage 5a — Creator Program: comped=True means we don't charge for this
    # tier (they're an active Creator getting Strategist comped, or other promo).
    comped: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )

    # Stripe — filled by Stage 2
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="plan")


class MonthlyUsage(Base):
    """One row per (user_id, period_start). New month → new row on first metered action."""
    __tablename__ = "monthly_usage"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)
    backtest_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    robustness_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chat_prompts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saved_strategies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="usage")

    __table_args__ = (
        Index("ix_monthly_usage_period", "period_start"),
    )
