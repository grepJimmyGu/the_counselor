"""Stage 5a — creator revshare calculation."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.attribution_visit import AttributionVisit
from app.models.creator import CreatorPayout
from app.models.stripe_invoice import StripeInvoice
from app.services.revshare_service import (
    REVSHARE_RATE,
    compute_creator_balance,
    compute_creator_revshare,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _attribution(
    db: Session,
    *,
    creator_user_id: str,
    referred_user_id: str,
    paid_at: datetime,
    handle: str = "creator",
) -> AttributionVisit:
    row = AttributionVisit(
        id=str(uuid4()),
        visitor_session_id=str(uuid4()),
        referrer_handle=handle,
        referrer_user_id=creator_user_id,
        landed_url="https://livermore.app/s/strat",
        landed_at=paid_at - timedelta(days=2),
        converted_to_user_id=referred_user_id,
        converted_at=paid_at - timedelta(days=1),
        converted_to_paid_at=paid_at,
    )
    db.add(row)
    db.commit()
    return row


def _invoice(
    db: Session,
    *,
    customer_user_id: str,
    amount_cents: int,
    paid_at: datetime,
    status: str = "paid",
) -> StripeInvoice:
    row = StripeInvoice(
        id=f"in_{uuid4().hex[:24]}",
        customer_user_id=customer_user_id,
        subscription_id="sub_test",
        amount_paid_cents=amount_cents,
        currency="USD",
        status=status,
        paid_at=paid_at,
        period_start=paid_at,
        period_end=paid_at + timedelta(days=30),
        raw={},
    )
    db.add(row)
    db.commit()
    return row


def _payout(
    db: Session,
    *,
    creator_user_id: str,
    amount_cents: int,
    paid_at: datetime,
) -> CreatorPayout:
    row = CreatorPayout(
        id=str(uuid4()),
        user_id=creator_user_id,
        amount_cents=amount_cents,
        currency="USD",
        period_start=paid_at.date() - timedelta(days=30),
        period_end=paid_at.date(),
        paid_at=paid_at,
        method="wise",
    )
    db.add(row)
    db.commit()
    return row


# ── Tests ────────────────────────────────────────────────────────────────────


def test_revshare_zero_for_no_referrals(make_user, db: Session):
    creator = make_user(email="lonely@test.com")
    assert compute_creator_revshare(db, creator.id) == Decimal(0)


def test_revshare_10_percent_of_paid_invoices(make_user, db: Session):
    creator = make_user(email="creator@test.com")
    customer = make_user(email="customer@test.com")
    now = datetime.utcnow() - timedelta(days=30)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer.id, paid_at=now)
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=now)  # $24
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=now + timedelta(days=30))

    earned = compute_creator_revshare(db, creator.id)
    # $48 total paid → 10% = $4.80
    assert earned == Decimal("4.80")
    # Sanity: REVSHARE_RATE is 10%.
    assert REVSHARE_RATE == Decimal("0.10")


def test_revshare_annual_payment(make_user, db: Session):
    """Annual prepay of $228 → 10% = $22.80, attributed at time of payment."""
    creator = make_user(email="annual-c@test.com")
    customer = make_user(email="annual-u@test.com")
    now = datetime.utcnow() - timedelta(days=5)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer.id, paid_at=now)
    _invoice(db, customer_user_id=customer.id, amount_cents=22_800, paid_at=now)

    earned = compute_creator_revshare(db, creator.id)
    assert earned == Decimal("22.80")


def test_revshare_excludes_refunded(make_user, db: Session):
    creator = make_user(email="refund-c@test.com")
    customer = make_user(email="refund-u@test.com")
    now = datetime.utcnow() - timedelta(days=10)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer.id, paid_at=now)
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=now, status="paid")
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=now, status="refunded")

    # Only the paid one counts → $24 * 10% = $2.40
    earned = compute_creator_revshare(db, creator.id)
    assert earned == Decimal("2.40")


def test_revshare_caps_at_12_months(make_user, db: Session):
    """Invoices beyond 365 days after first paid don't count toward revshare."""
    creator = make_user(email="cap-c@test.com")
    customer = make_user(email="cap-u@test.com")
    first_paid = datetime.utcnow() - timedelta(days=400)  # 13+ months ago
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer.id, paid_at=first_paid)
    # Month 0 — counts
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=first_paid)
    # Month 13 — outside window, excluded
    _invoice(db, customer_user_id=customer.id, amount_cents=2400, paid_at=first_paid + timedelta(days=400))

    earned = compute_creator_revshare(db, creator.id)
    assert earned == Decimal("2.40")  # only the first $24


def test_revshare_excludes_self_attribution(make_user, db: Session):
    """Even if a self-attribution row exists, revshare must exclude it."""
    creator = make_user(email="selfref-c@test.com")
    now = datetime.utcnow() - timedelta(days=5)
    # Self-referral: converted_to_user_id == referrer_user_id
    row = AttributionVisit(
        id=str(uuid4()),
        visitor_session_id=str(uuid4()),
        referrer_handle="selfref",
        referrer_user_id=creator.id,
        landed_url="https://x",
        landed_at=now - timedelta(days=2),
        converted_to_user_id=creator.id,  # SELF
        converted_at=now - timedelta(days=1),
        converted_to_paid_at=now,
    )
    db.add(row)
    _invoice(db, customer_user_id=creator.id, amount_cents=2400, paid_at=now)
    db.commit()

    earned = compute_creator_revshare(db, creator.id)
    assert earned == Decimal(0)


def test_revshare_aggregates_multiple_referrals(make_user, db: Session):
    creator = make_user(email="multi-c@test.com")
    customer_a = make_user(email="a@test.com")
    customer_b = make_user(email="b@test.com")
    now = datetime.utcnow() - timedelta(days=10)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer_a.id, paid_at=now)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer_b.id, paid_at=now, handle="dup")
    _invoice(db, customer_user_id=customer_a.id, amount_cents=2400, paid_at=now)
    _invoice(db, customer_user_id=customer_b.id, amount_cents=2400, paid_at=now)

    # 2 × $24 × 10% = $4.80
    assert compute_creator_revshare(db, creator.id) == Decimal("4.80")


def test_balance_subtracts_paid_out(make_user, db: Session):
    """compute_creator_balance = earned − sum of CreatorPayout."""
    creator = make_user(email="bal-c@test.com")
    customer = make_user(email="bal-u@test.com")
    now = datetime.utcnow() - timedelta(days=10)
    _attribution(db, creator_user_id=creator.id, referred_user_id=customer.id, paid_at=now)
    _invoice(db, customer_user_id=customer.id, amount_cents=10_000, paid_at=now)  # $100

    # Earned $10. Pay out $4 → balance = $6.
    _payout(db, creator_user_id=creator.id, amount_cents=400, paid_at=now + timedelta(days=15))

    assert compute_creator_revshare(db, creator.id) == Decimal("10.00")
    assert compute_creator_balance(db, creator.id) == Decimal("6.00")
