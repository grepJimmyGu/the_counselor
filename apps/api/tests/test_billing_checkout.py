"""Tests for POST /api/billing/checkout/session."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.billing import create_checkout_session
from app.schemas.billing import CheckoutSessionRequest


_PRICE_MAP = {
    ("strategist", "monthly"): "price_strat_mo",
    ("strategist", "annual"):  "price_strat_yr",
    ("quant",       "monthly"): "price_quant_mo",
    ("quant",       "annual"):  "price_quant_yr",
}


def _mock_stripe(create_customer_id: str = "cus_new", checkout_url: str = "https://checkout.stripe.com/pay/test"):
    return {
        "app.api.routes.billing.stripe_service.get_price_map":   MagicMock(return_value=_PRICE_MAP),
        "app.api.routes.billing.stripe_service.create_customer": MagicMock(return_value=create_customer_id),
        "app.api.routes.billing.stripe_service.create_checkout_session": MagicMock(return_value=checkout_url),
    }


def test_checkout_creates_stripe_customer_first_time(make_user, db: Session) -> None:
    user = make_user(email="checkout1@test.com", password="pw")
    body = CheckoutSessionRequest(tier="strategist", billing_cycle="monthly", return_url="https://app.com/return")

    mocks = _mock_stripe(create_customer_id="cus_created_new")
    with patch("app.api.routes.billing.stripe_service.get_price_map", mocks["app.api.routes.billing.stripe_service.get_price_map"]), \
         patch("app.api.routes.billing.stripe_service.create_customer", mocks["app.api.routes.billing.stripe_service.create_customer"]), \
         patch("app.api.routes.billing.stripe_service.create_checkout_session", mocks["app.api.routes.billing.stripe_service.create_checkout_session"]):
        result = create_checkout_session(body=body, current_user=user, db=db)

    db.refresh(user)
    assert user.plan.stripe_customer_id == "cus_created_new"
    assert result.url == "https://checkout.stripe.com/pay/test"
    mocks["app.api.routes.billing.stripe_service.create_customer"].assert_called_once()


def test_checkout_reuses_existing_stripe_customer(make_user, db: Session) -> None:
    user = make_user(email="checkout2@test.com", password="pw")
    user.plan.stripe_customer_id = "cus_existing"
    db.commit()

    body = CheckoutSessionRequest(tier="strategist", billing_cycle="annual", return_url="https://app.com/return")
    mocks = _mock_stripe()
    with patch("app.api.routes.billing.stripe_service.get_price_map", mocks["app.api.routes.billing.stripe_service.get_price_map"]), \
         patch("app.api.routes.billing.stripe_service.create_customer", mocks["app.api.routes.billing.stripe_service.create_customer"]), \
         patch("app.api.routes.billing.stripe_service.create_checkout_session", mocks["app.api.routes.billing.stripe_service.create_checkout_session"]):
        create_checkout_session(body=body, current_user=user, db=db)

    # Should NOT have called create_customer since one already exists
    mocks["app.api.routes.billing.stripe_service.create_customer"].assert_not_called()


def test_checkout_passes_remaining_trial_days(make_user, db: Session) -> None:
    """If user is trialing, checkout should pass remaining trial days to Stripe."""
    user = make_user(email="checkout3@test.com", password="pw")
    user.plan.stripe_customer_id = "cus_trial"
    user.plan.status = "trialing"
    user.plan.trial_end = datetime.utcnow() + timedelta(days=7)
    db.commit()

    body = CheckoutSessionRequest(tier="strategist", billing_cycle="monthly", return_url="https://app.com/r")
    captured_kwargs: dict = {}

    def mock_checkout(**kwargs):
        captured_kwargs.update(kwargs)
        return "https://checkout.stripe.com/pay/trial"

    with patch("app.api.routes.billing.stripe_service.get_price_map", return_value=_PRICE_MAP), \
         patch("app.api.routes.billing.stripe_service.create_checkout_session", side_effect=mock_checkout):
        create_checkout_session(body=body, current_user=user, db=db)

    assert captured_kwargs.get("trial_period_days") in (6, 7)  # ≤1s timing tolerance
