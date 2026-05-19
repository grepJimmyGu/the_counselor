"""Tests for the Stripe webhook handler and billing state machine."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.user import Plan
from app.services import billing_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_subscription(
    sub_id: str = "sub_test",
    user_id: str = "user-1",
    status: str = "active",
    price_id: str = "price_strat_mo",
    current_period_end: int = 9999999999,
) -> dict:
    return {
        "id": sub_id,
        "status": status,
        "current_period_end": current_period_end,
        "metadata": {"user_id": user_id},
        "items": {
            "data": [{
                "price": {
                    "id": price_id,
                    "recurring": {"interval": "month"},
                }
            }]
        },
    }


_PRICE_MAP_PATCH = {"price_strat_mo": ("strategist", "monthly"), "price_quant_yr": ("quant", "annual")}


# ── State machine unit tests ──────────────────────────────────────────────────

def test_webhook_subscription_created_sets_active(make_user, db: Session) -> None:
    user = make_user(email="wh1@test.com", password="pw")
    sub = _make_subscription(sub_id="sub_a", user_id=user.id, status="active")

    with patch("app.services.billing_state.price_id_to_tier", side_effect=lambda pid: _PRICE_MAP_PATCH.get(pid)):
        billing_state.apply_subscription_created(db, sub)

    db.refresh(user)
    assert user.plan.stripe_subscription_id == "sub_a"
    assert user.plan.status == "active"
    assert user.plan.tier == "strategist"
    assert user.plan.billing_cycle == "monthly"


def test_webhook_subscription_updated_changes_tier(make_user, db: Session) -> None:
    user = make_user(email="wh2@test.com", password="pw")
    user.plan.stripe_subscription_id = "sub_b"
    db.commit()

    # Update to quant annual
    sub = _make_subscription(sub_id="sub_b", user_id=user.id, status="active", price_id="price_quant_yr")
    sub["items"]["data"][0]["price"]["recurring"]["interval"] = "year"

    with patch("app.services.billing_state.price_id_to_tier", side_effect=lambda pid: _PRICE_MAP_PATCH.get(pid)):
        billing_state.apply_subscription_updated(db, sub)

    db.refresh(user)
    assert user.plan.tier == "quant"
    assert user.plan.billing_cycle == "annual"


def test_webhook_subscription_deleted_reverts_to_scout(make_user, db: Session) -> None:
    user = make_user(email="wh3@test.com", password="pw")
    user.plan.tier = "strategist"
    user.plan.status = "active"
    user.plan.stripe_subscription_id = "sub_c"
    db.commit()

    sub = _make_subscription(sub_id="sub_c", user_id=user.id, status="canceled")
    billing_state.apply_subscription_deleted(db, sub)

    db.refresh(user)
    assert user.plan.tier == "scout"
    assert user.plan.status == "canceled"
    assert user.plan.stripe_subscription_id is None


def test_webhook_invoice_payment_failed_sets_past_due(make_user, db: Session) -> None:
    user = make_user(email="wh4@test.com", password="pw")
    user.plan.stripe_subscription_id = "sub_d"
    user.plan.status = "active"
    db.commit()

    invoice = {"subscription": "sub_d"}
    billing_state.apply_invoice_payment_failed(db, invoice)

    db.refresh(user)
    assert user.plan.status == "past_due"


def test_webhook_invoice_payment_succeeded_restores_active(make_user, db: Session) -> None:
    user = make_user(email="wh5@test.com", password="pw")
    user.plan.stripe_subscription_id = "sub_e"
    user.plan.status = "past_due"
    db.commit()

    invoice = {"subscription": "sub_e"}
    billing_state.apply_invoice_payment_succeeded(db, invoice)

    db.refresh(user)
    assert user.plan.status == "active"


def test_webhook_duplicate_event_is_noop(make_user, db: Session) -> None:
    """Inserting the same Stripe event id twice should no-op (idempotency)."""
    from app.models.stripe_event import StripeEvent

    evt = StripeEvent(
        id="evt_test_123",
        type="customer.subscription.created",
        received_at=datetime.utcnow(),
        payload={"id": "evt_test_123", "type": "customer.subscription.created", "data": {"object": {}}},
    )
    db.add(evt)
    db.commit()

    # Second insert — should raise IntegrityError, which the handler catches
    from sqlalchemy.exc import IntegrityError
    evt2 = StripeEvent(
        id="evt_test_123",
        type="customer.subscription.created",
        received_at=datetime.utcnow(),
        payload={},
    )
    db.add(evt2)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_webhook_signature_invalid_returns_400() -> None:
    """Webhook endpoint rejects bad signatures."""
    import stripe
    from app.api.routes.stripe_webhook import stripe_webhook
    # Tested by checking that construct_event raises on bad sig — handled in route
    with patch("app.api.routes.stripe_webhook.stripe.Webhook.construct_event",
               side_effect=stripe.SignatureVerificationError("bad sig", "sig")):
        import asyncio
        from fastapi import HTTPException
        from unittest.mock import AsyncMock, MagicMock

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"id":"evt_bad"}')
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(stripe_webhook(request=mock_request, stripe_signature="bad", db=mock_db))
        assert exc.value.status_code == 400
