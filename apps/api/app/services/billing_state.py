from __future__ import annotations

"""State machine helpers for plan transitions driven by Stripe webhooks and scheduled jobs."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import Plan
from app.services.stripe_service import price_id_to_tier

logger = logging.getLogger(__name__)


def _get_billing_cycle(subscription: dict) -> str | None:
    """Extract 'monthly' | 'annual' from a Stripe subscription object (dict form)."""
    items = subscription.get("items", {}).get("data", [])
    if not items:
        return None
    interval = items[0].get("price", {}).get("recurring", {}).get("interval")
    return "annual" if interval == "year" else "monthly" if interval == "month" else None


def _subscription_tier(subscription: dict) -> str | None:
    """Infer tier from price id on the subscription."""
    items = subscription.get("items", {}).get("data", [])
    if not items:
        return None
    price_id = items[0].get("price", {}).get("id")
    result = price_id_to_tier(price_id)
    if result is None:
        logger.error("Unknown price id in webhook: %s", price_id)
        return None
    return result[0]  # tier


def _ts(unix: int | None) -> datetime | None:
    if not unix:
        return None
    return datetime.utcfromtimestamp(unix)


def apply_subscription_created(db: Session, subscription: dict) -> None:
    user_id: str | None = (
        subscription.get("metadata", {}).get("user_id")
        or subscription.get("customer_metadata", {}).get("user_id")
    )
    if not user_id:
        logger.warning("subscription.created: no user_id in metadata — skipping")
        return

    plan = db.get(Plan, user_id)
    if plan is None:
        logger.error("subscription.created: no plan row for user_id=%s", user_id)
        return

    stripe_status = subscription.get("status", "")
    plan.stripe_subscription_id = subscription["id"]
    plan.status = "trialing" if stripe_status == "trialing" else "active"
    plan.current_period_end = _ts(subscription.get("current_period_end"))
    plan.billing_cycle = _get_billing_cycle(subscription)
    tier = _subscription_tier(subscription)
    if tier:
        plan.tier = tier
    db.commit()


def apply_subscription_updated(db: Session, subscription: dict) -> None:
    sub_id: str = subscription["id"]
    plan = db.query(Plan).filter(Plan.stripe_subscription_id == sub_id).first()
    if plan is None:
        # Could arrive before subscription.created in rare cases — try user metadata fallback
        user_id = subscription.get("metadata", {}).get("user_id")
        if user_id:
            plan = db.get(Plan, user_id)
    if plan is None:
        logger.warning("subscription.updated: no plan for sub_id=%s", sub_id)
        return

    stripe_status = subscription.get("status", "")
    status_map = {
        "trialing": "trialing",
        "active": "active",
        "past_due": "past_due",
        "canceled": "canceled",
        "unpaid": "past_due",
    }
    plan.status = status_map.get(stripe_status, plan.status)
    plan.current_period_end = _ts(subscription.get("current_period_end"))
    plan.billing_cycle = _get_billing_cycle(subscription)
    tier = _subscription_tier(subscription)
    if tier:
        plan.tier = tier
    # Guard: multiple items is unexpected
    items = subscription.get("items", {}).get("data", [])
    if len(items) > 1:
        logger.error("Unexpected multi-item subscription %s — data integrity risk", sub_id)
    db.commit()


def apply_subscription_deleted(db: Session, subscription: dict) -> None:
    sub_id: str = subscription["id"]
    plan = db.query(Plan).filter(Plan.stripe_subscription_id == sub_id).first()
    if plan is None:
        return
    plan.status = "canceled"
    plan.tier = "scout"
    plan.canceled_at = datetime.utcnow()
    plan.stripe_subscription_id = None
    db.commit()


def apply_invoice_payment_succeeded(db: Session, invoice: dict) -> None:
    sub_id: str | None = invoice.get("subscription")
    if not sub_id:
        return
    plan = db.query(Plan).filter(Plan.stripe_subscription_id == sub_id).first()
    if plan is None:
        return
    if plan.status in ("past_due", "trialing"):
        plan.status = "active"
        db.commit()


def apply_invoice_payment_failed(db: Session, invoice: dict) -> None:
    sub_id: str | None = invoice.get("subscription")
    if not sub_id:
        return
    plan = db.query(Plan).filter(Plan.stripe_subscription_id == sub_id).first()
    if plan is None:
        return
    plan.status = "past_due"
    db.commit()


def apply_checkout_session_completed(db: Session, session: dict) -> None:
    """Belt-and-suspenders: ensure subscription is created after checkout."""
    sub_id: str | None = session.get("subscription")
    user_id: str | None = session.get("metadata", {}).get("user_id")
    if not sub_id or not user_id:
        return
    plan = db.get(Plan, user_id)
    if plan and not plan.stripe_subscription_id:
        plan.stripe_subscription_id = sub_id
        db.commit()
