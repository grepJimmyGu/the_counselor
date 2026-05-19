from __future__ import annotations

"""Thin wrapper around the Stripe SDK.

All direct stripe.* calls live here so tests can mock a single module.
"""

import logging
from typing import Optional

import stripe

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Price catalogue: (tier, cycle) → Stripe price id
# Loaded lazily from settings on first call.
_PRICE_MAP: dict[tuple[str, str], str] | None = None
_PRICE_ID_TO_TIER: dict[str, tuple[str, str]] | None = None


def _init_stripe() -> None:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key


def get_price_map() -> dict[tuple[str, str], str]:
    global _PRICE_MAP, _PRICE_ID_TO_TIER
    if _PRICE_MAP is None:
        s = get_settings()
        _PRICE_MAP = {
            ("strategist", "monthly"): s.stripe_price_strategist_monthly,
            ("strategist", "annual"):  s.stripe_price_strategist_annual,
            ("quant",       "monthly"): s.stripe_price_quant_monthly,
            ("quant",       "annual"):  s.stripe_price_quant_annual,
        }
        _PRICE_ID_TO_TIER = {v: k for k, v in _PRICE_MAP.items() if v}
    return _PRICE_MAP


def price_id_to_tier(price_id: str) -> Optional[tuple[str, str]]:
    """Return (tier, billing_cycle) for a Stripe price id, or None if unknown."""
    get_price_map()
    return _PRICE_ID_TO_TIER.get(price_id)  # type: ignore[union-attr]


AMOUNTS: dict[tuple[str, str], int] = {
    ("strategist", "monthly"): 2400,
    ("strategist", "annual"):  22800,
    ("quant",       "monthly"): 7900,
    ("quant",       "annual"):  70800,
}

DISPLAY_PRICES: dict[tuple[str, str], str] = {
    ("strategist", "monthly"): "$24/mo",
    ("strategist", "annual"):  "$19/mo (billed $228/yr)",
    ("quant",       "monthly"): "$79/mo",
    ("quant",       "annual"):  "$59/mo (billed $708/yr)",
}


def create_customer(email: str, user_id: str) -> str:
    """Create a Stripe customer and return the customer id."""
    _init_stripe()
    customer = stripe.Customer.create(
        email=email,
        metadata={"user_id": user_id},
    )
    return customer.id  # type: ignore[return-value]


def update_customer_email(stripe_customer_id: str, new_email: str) -> None:
    _init_stripe()
    try:
        stripe.Customer.modify(stripe_customer_id, email=new_email)
    except stripe.StripeError as exc:
        logger.warning("Failed to sync email to Stripe customer %s: %s", stripe_customer_id, exc)


def create_checkout_session(
    *,
    stripe_customer_id: str,
    price_id: str,
    trial_period_days: Optional[int],
    success_url: str,
    cancel_url: str,
    user_id: str,
    tier: str,
    billing_cycle: str,
) -> str:
    """Create a Stripe Checkout session and return the hosted URL."""
    _init_stripe()
    params: dict = {
        "customer": stripe_customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"user_id": user_id, "tier": tier, "billing_cycle": billing_cycle},
        "subscription_data": {
            "metadata": {"user_id": user_id, "tier": tier},
        },
    }
    if trial_period_days and trial_period_days > 0:
        params["subscription_data"]["trial_period_days"] = trial_period_days

    session = stripe.checkout.Session.create(**params)
    return session.url  # type: ignore[return-value]


def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Create a Stripe Billing Portal session and return the URL."""
    _init_stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url  # type: ignore[return-value]


def cancel_subscription(stripe_subscription_id: str) -> None:
    _init_stripe()
    try:
        stripe.Subscription.cancel(stripe_subscription_id)
    except stripe.StripeError as exc:
        logger.warning("Failed to cancel Stripe subscription %s: %s", stripe_subscription_id, exc)


def construct_webhook_event(payload: bytes, sig_header: str, secret: str) -> stripe.Event:
    """Verify Stripe signature and return the event. Raises stripe.SignatureVerificationError."""
    return stripe.Webhook.construct_event(payload, sig_header, secret)
