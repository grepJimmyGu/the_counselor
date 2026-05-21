from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import Plan, User
from app.schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalResponse,
    PricingPage,
    TierOption,
    TrialStartRequest,
    TrialStartResponse,
)
from app.services import stripe_service

router = APIRouter(prefix="/api/billing", tags=["billing"])

_TRIAL_DAYS = 14


# ── Pricing ───────────────────────────────────────────────────────────────────

@router.get("/pricing", response_model=PricingPage)
def get_pricing() -> PricingPage:
    """Public endpoint — returns the four purchasable tier options."""
    price_map = stripe_service.get_price_map()
    options: list[TierOption] = []
    for (tier, cycle), price_id in sorted(price_map.items()):
        options.append(
            TierOption(
                tier=tier,  # type: ignore[arg-type]
                billing_cycle=cycle,  # type: ignore[arg-type]
                price_id=price_id,
                amount_cents=stripe_service.AMOUNTS[(tier, cycle)],
                display_price=stripe_service.DISPLAY_PRICES[(tier, cycle)],
            )
        )
    return PricingPage(options=options, trial_days=_TRIAL_DAYS)


# ── Trial ─────────────────────────────────────────────────────────────────────

@router.post("/trial/start", response_model=TrialStartResponse)
def start_trial(
    body: TrialStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrialStartResponse:
    plan = db.get(Plan, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # One trial per user lifetime — enforced by checking if trial_end was ever set
    if plan.trial_end is not None:
        raise HTTPException(
            status_code=409,
            detail="You have already used your free trial.",
        )
    if plan.status in ("trialing", "active") and plan.stripe_subscription_id:
        raise HTTPException(
            status_code=409,
            detail="You already have an active subscription.",
        )

    trial_end = datetime.utcnow() + timedelta(days=_TRIAL_DAYS)
    plan.tier = body.tier
    plan.status = "trialing"
    plan.trial_end = trial_end
    plan.billing_cycle = None
    db.commit()

    # Stage 6a: trial_started event
    try:
        from app.services.posthog_service import capture
        capture(current_user.id, "trial_started", {
            "tier": body.tier,
            "days": _TRIAL_DAYS,
        })
    except Exception:
        pass

    return TrialStartResponse(trial_end=trial_end, tier=body.tier)


# ── Checkout ──────────────────────────────────────────────────────────────────

@router.post("/checkout/session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    body: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse:
    price_map = stripe_service.get_price_map()
    price_id = price_map.get((body.tier, body.billing_cycle))
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for {body.tier}/{body.billing_cycle}.",
        )

    plan = db.get(Plan, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # Create Stripe customer if none yet
    if not plan.stripe_customer_id:
        customer_id = stripe_service.create_customer(
            email=current_user.email, user_id=current_user.id
        )
        plan.stripe_customer_id = customer_id
        db.commit()

    # Remaining trial days (so user doesn't get a fresh 14 days on checkout)
    trial_period_days: Optional[int] = None
    if plan.status == "trialing" and plan.trial_end:
        remaining = (plan.trial_end - datetime.utcnow()).days
        trial_period_days = max(0, remaining)

    success_url = f"{body.return_url}?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{body.return_url}?canceled=true"

    url = stripe_service.create_checkout_session(
        stripe_customer_id=plan.stripe_customer_id,
        price_id=price_id,
        trial_period_days=trial_period_days,
        success_url=success_url,
        cancel_url=cancel_url,
        user_id=current_user.id,
        tier=body.tier,
        billing_cycle=body.billing_cycle,
    )
    return CheckoutSessionResponse(url=url)


# ── Customer Portal ───────────────────────────────────────────────────────────

@router.post("/portal", response_model=CustomerPortalResponse)
def customer_portal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerPortalResponse:
    plan = db.get(Plan, current_user.id)
    if plan is None or not plan.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No billing account found. Start a subscription first.",
        )

    settings = get_settings()
    return_url = f"{settings.frontend_url}/account"
    url = stripe_service.create_portal_session(plan.stripe_customer_id, return_url)
    return CustomerPortalResponse(url=url)
