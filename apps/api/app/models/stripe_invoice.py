"""Stripe invoice ledger (Stage 5a).

One row per `invoice.payment_succeeded` (or refund) event. Stage 5a's
revshare calculation queries this table to sum first-year MRR for users
referred by a creator.

Idempotency: id = Stripe invoice id (the natural primary key). The
webhook handler must INSERT…ON CONFLICT DO NOTHING (or catch IntegrityError)
because Stripe retries deliveries.

Note: customer_user_id is intentionally NOT a FK to users.id (Stage 1a rule).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StripeInvoice(Base):
    __tablename__ = "stripe_invoices"

    # Stripe invoice id (in_xxx).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # The customer (denormalized from Stripe customer → users.plans.stripe_customer_id).
    customer_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False)

    amount_paid_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD", nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # paid | refunded

    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Full webhook object for replay / debug.
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
