"""Creator Program data models (Stage 5a).

Three tables:
  - CreatorApplication: pending/approved/rejected applications.
  - Creator: active program members. Created on application approval.
  - CreatorPayout: ledger of payouts made (manual via Stripe Connect / Wise
    for Year 1).

Note: user_id columns are NOT FKs to users.id (Stage 1a rule).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CreatorApplication(Base):
    __tablename__ = "creator_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    handle_link: Mapped[str] = mapped_column(String(200), nullable=False)
    follower_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # tiktok | youtube | substack | twitter | other
    content_format: Mapped[str] = mapped_column(String(32), nullable=False)
    sample_url: Mapped[str] = mapped_column(String(500), nullable=False)
    pitch: Mapped[str] = mapped_column(Text, nullable=False)

    # pending | approved | rejected
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", nullable=False,
    )

    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False,
    )


class Creator(Base):
    __tablename__ = "creators"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # active | suspended | terminated
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False,
    )
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    payout_email: Mapped[str] = mapped_column(String(320), nullable=False)
    payout_country: Mapped[str] = mapped_column(
        String(2), default="US", server_default="US", nullable=False,
    )
    stripe_connect_account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CreatorPayout(Base):
    """Ledger of manual payouts. Admin uploads a CSV monthly that populates this."""

    __tablename__ = "creator_payouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD", nullable=False,
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # stripe_connect | wise | other
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
