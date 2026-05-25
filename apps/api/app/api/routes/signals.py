"""Saved-strategy signal alerts (Stage 8 v0 — Phase A).

Endpoints per build_specs/research_execution_v0_signals_and_alerts.md §5:
  GET    /api/saved-strategies/{id}/signal             — current state + subscription flag
  POST   /api/saved-strategies/{id}/signal/subscribe   — opt in
  DELETE /api/saved-strategies/{id}/signal/subscribe   — opt out (204)
  POST   /api/saved-strategies/{id}/signal/acknowledge — user marks "I acted on this"

The §5.4 email-token unsub endpoint lands in Phase B alongside the cron + email
template; signal state recomputation also lives there.

Router is mounted by main.py only when settings.signal_alerts_enabled is True
(§11 disclaimer requires lawyer review before public enablement).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.models.user import User

router = APIRouter(prefix="/api/saved-strategies", tags=["signals"])


# ── Response schemas ─────────────────────────────────────────────────────────


class SignalEventResponse(BaseModel):
    id: str
    previous_signal_display: Optional[str]
    new_signal_display: str
    change_type: str
    as_of_date: str
    reference_price_snapshot: Optional[dict]

    model_config = {"from_attributes": True}


class SignalStateResponse(BaseModel):
    saved_strategy_id: str
    # Null until the Phase B cron runs at least once for this strategy.
    current_signal: Optional[dict]
    current_signal_display: Optional[str]
    as_of_date: Optional[str]
    last_changed_at: Optional[datetime]
    subscription_active: bool
    recent_events: list[SignalEventResponse]


class SubscriptionStatusResponse(BaseModel):
    subscription_active: bool


class AcknowledgeResponse(BaseModel):
    last_acted_at: datetime


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_owned_strategy(
    db: Session, strategy_id: str, user_id: str
) -> SavedStrategy:
    """Return the strategy or raise 404. Treats not-owned as not-found to avoid
    leaking the existence of other users' strategies."""
    row = db.get(SavedStrategy, strategy_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return row


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/{strategy_id}/signal", response_model=SignalStateResponse)
def get_signal(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SignalStateResponse:
    """Return the cached signal state plus the user's subscription flag.

    State is null until the Phase B daily cron populates it; the frontend
    should render "Signal computing — first run pending" in that case.
    """
    _load_owned_strategy(db, strategy_id, current_user.id)

    state = db.get(SavedStrategySignalState, strategy_id)
    subscription = db.get(SignalAlertSubscription, (current_user.id, strategy_id))

    recent_events = (
        db.query(SignalEvent)
        .filter(SignalEvent.saved_strategy_id == strategy_id)
        .order_by(SignalEvent.created_at.desc())
        .limit(5)
        .all()
    )

    return SignalStateResponse(
        saved_strategy_id=strategy_id,
        current_signal=state.current_signal if state else None,
        current_signal_display=state.current_signal_display if state else None,
        as_of_date=state.as_of_date.isoformat() if state else None,
        last_changed_at=state.last_changed_at if state else None,
        subscription_active=subscription is not None and subscription.email_enabled,
        recent_events=[
            SignalEventResponse(
                id=e.id,
                previous_signal_display=e.previous_signal_display,
                new_signal_display=e.new_signal_display,
                change_type=e.change_type,
                as_of_date=e.as_of_date.isoformat(),
                reference_price_snapshot=e.reference_price_snapshot,
            )
            for e in recent_events
        ],
    )


@router.post(
    "/{strategy_id}/signal/subscribe",
    response_model=SubscriptionStatusResponse,
    status_code=200,
)
def subscribe_signal(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubscriptionStatusResponse:
    """Idempotent opt-in. Re-subscribing flips `email_enabled` back to True if
    the row exists but was disabled."""
    _load_owned_strategy(db, strategy_id, current_user.id)

    sub = db.get(SignalAlertSubscription, (current_user.id, strategy_id))
    if sub is None:
        sub = SignalAlertSubscription(
            user_id=current_user.id,
            saved_strategy_id=strategy_id,
            email_enabled=True,
        )
        db.add(sub)
    else:
        sub.email_enabled = True
    db.commit()

    return SubscriptionStatusResponse(subscription_active=True)


@router.delete(
    "/{strategy_id}/signal/subscribe",
    status_code=204,
    response_class=Response,
)
def unsubscribe_signal(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Idempotent opt-out — deletes the row if present, no-op otherwise."""
    _load_owned_strategy(db, strategy_id, current_user.id)

    sub = db.get(SignalAlertSubscription, (current_user.id, strategy_id))
    if sub is not None:
        db.delete(sub)
        db.commit()
    return Response(status_code=204)


@router.post(
    "/{strategy_id}/signal/acknowledge",
    response_model=AcknowledgeResponse,
)
def acknowledge_signal(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AcknowledgeResponse:
    """Record that the user acted on the current signal — timestamp only, no
    broker integration. Surfaces as "Last acted: 3d ago" in the UI."""
    _load_owned_strategy(db, strategy_id, current_user.id)

    sub = db.get(SignalAlertSubscription, (current_user.id, strategy_id))
    if sub is None:
        raise HTTPException(
            status_code=409,
            detail="Subscribe to signal alerts before marking acted.",
        )

    sub.last_acted_at = datetime.utcnow()
    db.commit()
    return AcknowledgeResponse(last_acted_at=sub.last_acted_at)
