"""Creator revshare calculation (Stage 5a).

Sums 10% of first-year MRR from every paid user referred by a creator.
First-year = 365 days from each referred user's converted_to_paid_at.

Excludes refunded invoices. Excludes self-attribution (AttributionVisit
already enforces this on the write side via convert_on_signup, but we
filter again here as belt + suspenders).

Returns Decimal in dollars (not cents) for human-readable accounting.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attribution_visit import AttributionVisit
from app.models.creator import CreatorPayout
from app.models.stripe_invoice import StripeInvoice


# 10% revshare on first-year MRR per the GTM proposal.
REVSHARE_RATE = Decimal("0.10")
FIRST_YEAR_DAYS = 365


def compute_creator_revshare(
    db: Session,
    creator_user_id: str,
    *,
    as_of: Optional[datetime] = None,
) -> Decimal:
    """Total revshare *earned* (lifetime gross) for this creator. Does NOT
    subtract previously paid-out amounts — caller computes balance separately.

    Logic:
      1. Find all attribution rows for this creator with converted_to_paid_at set.
      2. For each referral, sum paid (non-refunded) invoices for that customer
         where invoice.paid_at is within 365 days of converted_to_paid_at.
      3. Multiply total by REVSHARE_RATE.
    """
    as_of_dt = as_of or datetime.utcnow()

    referrals = list(db.scalars(
        select(AttributionVisit).where(
            AttributionVisit.referrer_user_id == creator_user_id,
            AttributionVisit.converted_to_paid_at.is_not(None),
            # Self-attribution belt-and-suspenders.
            AttributionVisit.converted_to_user_id != creator_user_id,
        )
    ))

    total_cents = 0
    for r in referrals:
        if r.converted_to_user_id is None or r.converted_to_paid_at is None:
            continue
        # First-year window from the day they paid for the first time.
        # Strip tzinfo for cross-dialect comparison (SQLAlchemy returns aware
        # datetimes on Postgres, naive on SQLite).
        start = r.converted_to_paid_at.replace(tzinfo=None)
        window_end = min(start + timedelta(days=FIRST_YEAR_DAYS), as_of_dt)

        invoices = db.scalars(
            select(StripeInvoice).where(
                StripeInvoice.customer_user_id == r.converted_to_user_id,
                StripeInvoice.status == "paid",
            )
        ).all()

        for inv in invoices:
            paid_at = inv.paid_at.replace(tzinfo=None) if inv.paid_at else None
            if paid_at is None:
                continue
            if start <= paid_at <= window_end:
                total_cents += inv.amount_paid_cents

    return (Decimal(total_cents) / Decimal(100)) * REVSHARE_RATE


def compute_creator_balance(
    db: Session,
    creator_user_id: str,
) -> Decimal:
    """Earned − already-paid-out. The number the monthly payout CSV uses."""
    earned = compute_creator_revshare(db, creator_user_id)
    paid_out_cents = sum(
        p.amount_cents for p in db.scalars(
            select(CreatorPayout).where(CreatorPayout.user_id == creator_user_id)
        )
    )
    paid_out = Decimal(paid_out_cents) / Decimal(100)
    return earned - paid_out
