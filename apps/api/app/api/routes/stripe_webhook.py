from __future__ import annotations

import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.stripe_event import StripeEvent
from app.services import billing_state
from app.services.anonymous_service import get_anonymous_session_by_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["stripe"])

_HANDLED_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "checkout.session.completed",
}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature", default=""),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    payload = await request.body()

    # Verify signature
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except (stripe.SignatureVerificationError, ValueError) as exc:
        logger.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_id: str = event["id"]
    event_type: str = event["type"]

    # Idempotency — insert event record first
    record = StripeEvent(
        id=event_id,
        type=event_type,
        received_at=datetime.utcnow(),
        payload=dict(event),
    )
    try:
        db.add(record)
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("Duplicate Stripe event %s — skipping", event_id)
        return {"status": "duplicate"}

    # Dispatch
    try:
        _dispatch(db, event_type, event["data"]["object"])
        record.processed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        logger.exception("Failed to process Stripe event %s: %s", event_id, exc)
        record.error = str(exc)
        db.commit()
        # Still return 200 — Stripe must not retry a processing error
    return {"status": "ok"}


def _dispatch(db: Session, event_type: str, obj: dict) -> None:
    if event_type == "customer.subscription.created":
        billing_state.apply_subscription_created(db, obj)
        _log_attribution_on_conversion(db, obj)
        _mark_attribution_paid(db, obj)
    elif event_type == "customer.subscription.updated":
        billing_state.apply_subscription_updated(db, obj)
    elif event_type == "customer.subscription.deleted":
        billing_state.apply_subscription_deleted(db, obj)
    elif event_type == "invoice.payment_succeeded":
        billing_state.apply_invoice_payment_succeeded(db, obj)
        _record_stripe_invoice(db, obj)
    elif event_type == "invoice.payment_failed":
        billing_state.apply_invoice_payment_failed(db, obj)
    elif event_type == "checkout.session.completed":
        billing_state.apply_checkout_session_completed(db, obj)
    elif event_type not in _HANDLED_EVENTS:
        logger.debug("Unhandled Stripe event type: %s", event_type)


def _log_attribution_on_conversion(db: Session, subscription_obj: dict) -> None:
    """Stage 1a: when an anonymous-attributed signup converts to paid, emit a
    structured log line so Stage 5 (Creator Program) can replay attributions
    without needing the attribution_visits table to exist today.

    The data is fully preserved in anonymous_sessions.via_handle +
    converted_to_user_id; this log is the trigger event."""
    metadata = subscription_obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return
    session = get_anonymous_session_by_user_id(db, user_id)
    if session is None or not session.via_handle:
        return
    logger.info(
        "attribution.signup_converted_to_paid user_id=%s via_handle=%s "
        "anon_session_id=%s subscription_id=%s",
        user_id,
        session.via_handle,
        session.id,
        subscription_obj.get("id"),
    )


def _record_stripe_invoice(db: Session, invoice_obj: dict) -> None:
    """Stage 5a: persist paid invoice rows for revshare calc.

    Resolves the Stripe customer → plans.stripe_customer_id → user_id.
    Idempotent (PK = Stripe invoice id; INSERT errors are silently
    rolled back). Silent on failure — webhook must still ack."""
    from datetime import datetime as _dt
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models.stripe_invoice import StripeInvoice
    from app.models.user import Plan

    try:
        invoice_id = invoice_obj.get("id")
        if not invoice_id:
            return

        # Already recorded → skip (webhook replay).
        if db.get(StripeInvoice, invoice_id) is not None:
            return

        # Resolve customer → user_id via plans.stripe_customer_id.
        customer_id = invoice_obj.get("customer")
        if not customer_id:
            return
        plan = db.scalar(select(Plan).where(Plan.stripe_customer_id == customer_id))
        if plan is None:
            logger.warning(
                "stripe_invoice: no plan for stripe_customer_id=%s (invoice=%s)",
                customer_id, invoice_id,
            )
            return

        # Lines for period_start/end (Stripe gives this per invoice line; use first).
        lines = invoice_obj.get("lines", {}).get("data") or []
        first_line = lines[0] if lines else {}
        period = first_line.get("period") or {}

        invoice = StripeInvoice(
            id=invoice_id,
            customer_user_id=plan.user_id,
            subscription_id=invoice_obj.get("subscription") or "",
            amount_paid_cents=int(invoice_obj.get("amount_paid", 0)),
            currency=(invoice_obj.get("currency") or "USD").upper(),
            status=invoice_obj.get("status") or "paid",  # "paid" usually
            paid_at=_dt.utcfromtimestamp(invoice_obj.get("status_transitions", {}).get("paid_at")
                                         or invoice_obj.get("created", 0)),
            period_start=_dt.utcfromtimestamp(period.get("start") or invoice_obj.get("period_start") or 0),
            period_end=_dt.utcfromtimestamp(period.get("end") or invoice_obj.get("period_end") or 0),
            raw=dict(invoice_obj),
        )
        db.add(invoice)
        db.commit()
    except IntegrityError:
        db.rollback()  # race: another webhook delivered the same invoice
    except Exception as exc:
        logger.warning("record_stripe_invoice failed: %s", exc)
        db.rollback()


def _mark_attribution_paid(db: Session, subscription_obj: dict) -> None:
    """Stage 4a: on customer.subscription.created, mark the user's attribution
    row as converted-to-paid. Stage 5's Creator Program queries this column
    for payout calculations. Silent on failure."""
    metadata = subscription_obj.get("metadata") or {}
    user_id = metadata.get("user_id")
    if not user_id:
        return
    try:
        from app.services.attribution_service import mark_paid_conversion
        mark_paid_conversion(db, user_id, subscription_id=subscription_obj.get("id"))
    except Exception as exc:
        logger.warning("mark_attribution_paid failed for user_id=%s: %s", user_id, exc)
