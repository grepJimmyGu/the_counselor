"""Unified signal card endpoints (PRD-25 — Minimal).

Read-only re-presentation of the existing per-strategy signal state as a
uniform card:

    GET  /api/signals/card?saved_strategy_id=...   → one SignalCard
    POST /api/signals/card/batch  {saved_strategy_ids: [...]}  → list

Mounted **unconditionally** (unlike the gated `/api/saved-strategies/.../signal`
alert routes): the card is the cross-surface brick the redesign renders on
every ticker surface, so it must exist regardless of `signal_alerts_enabled`.
When the signal cron hasn't populated a strategy's state, its card is
`pending`. Cards are user-scoped — a caller only ever sees their own
strategies.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.entitlement_errors import upgrade_error
from app.core.config import get_settings
from app.db.session import get_db
from app.models.saved_strategy import SavedStrategy
from app.models.ticker_signal_subscription import TickerSignalSubscription
from app.models.user import User
from app.schemas.signal_card import SignalCard
from app.services.screener.saved_screen_service import is_screen
from app.services.signal_card_service import evaluate_cards

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalCardBatchRequest(BaseModel):
    saved_strategy_ids: List[str] = Field(default_factory=list)


class TickerSubscribeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    # The saved screen whose reading the ticker is judged against. PRD-28
    # scopes per-ticker alerts to a real saved screen (the "default template"
    # the PRD assumed does not exist in this codebase).
    saved_screen_id: str = Field(..., min_length=1, max_length=36)
    email_enabled: bool = True


class TickerSubscriptionOut(BaseModel):
    symbol: str
    saved_screen_id: str
    screen_title: Optional[str] = None
    email_enabled: bool
    last_state: Optional[str] = None
    last_as_of: Optional[str] = None


@router.get("/card", response_model=SignalCard)
def get_signal_card(
    saved_strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SignalCard:
    """One card for a strategy the caller owns (404 otherwise)."""
    cards = evaluate_cards(db, [saved_strategy_id], current_user.id)
    if not cards:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return cards[0]


@router.post("/card/batch", response_model=List[SignalCard])
def get_signal_cards_batch(
    payload: SignalCardBatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[SignalCard]:
    """Cards for a list of the caller's strategies — one cached call for a
    whole list surface. Non-owned ids are silently dropped."""
    return evaluate_cards(db, payload.saved_strategy_ids, current_user.id)


# ── PRD-28: per-ticker alert subscriptions ──────────────────────────────────
#
# "Tell me when THIS symbol changes state under THIS screen's reading" — in
# BOTH directions. `monitor_saved_screens` already covers "any new entrant to
# my screen", which is basket-scoped and entrant-only.


def _owned_screen(db: Session, screen_id: str, user_id: str) -> SavedStrategy:
    """The screen, or 404. Not-owned reads as not-found so we never leak the
    existence of another user's screen."""
    row = db.get(SavedStrategy, screen_id)
    if row is None or row.user_id != user_id or not is_screen(row):
        raise HTTPException(status_code=404, detail="Screen not found.")
    return row


@router.post("/card/subscribe", response_model=TickerSubscriptionOut)
def subscribe_ticker(
    payload: TickerSubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TickerSubscriptionOut:
    """Watch one symbol under one saved screen. Idempotent — re-subscribing
    updates `email_enabled` instead of creating a duplicate."""
    # Snapshot before any commit expires the instance (trap #17).
    user_id: str = current_user.id
    tier: str = current_user.plan.tier if current_user.plan else "scout"
    symbol = payload.symbol.strip().upper()

    # Strategist+, mirroring screen tracking. Honours shadow mode: with
    # GATING_ENABLED=false the check is observe-only so the feature stays
    # testable on any tier.
    if get_settings().gating_enabled and tier not in ("strategist", "quant"):
        raise upgrade_error(
            "screen_tracking_locked",
            current_tier=tier,
            current_value=tier,
            limit_value="strategist",
        )

    screen = _owned_screen(db, payload.saved_screen_id, user_id)
    screen_title = screen.title

    sub = db.get(
        TickerSignalSubscription, (user_id, symbol, payload.saved_screen_id)
    )
    if sub is None:
        sub = TickerSignalSubscription(
            user_id=user_id,
            symbol=symbol,
            saved_screen_id=payload.saved_screen_id,
            email_enabled=payload.email_enabled,
        )
        db.add(sub)
    else:
        sub.email_enabled = payload.email_enabled
    db.commit()

    return TickerSubscriptionOut(
        symbol=symbol,
        saved_screen_id=payload.saved_screen_id,
        screen_title=screen_title,
        email_enabled=payload.email_enabled,
        last_state=sub.last_state,
        last_as_of=sub.last_as_of.isoformat() if sub.last_as_of else None,
    )


@router.delete("/card/subscribe", status_code=204, response_class=Response)
def unsubscribe_ticker(
    symbol: str,
    saved_screen_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Idempotent opt-out — deletes the row if present, no-op otherwise.
    (204 must not serialize a body — backend trap #7.)"""
    sub = db.get(
        TickerSignalSubscription,
        (current_user.id, symbol.strip().upper(), saved_screen_id),
    )
    if sub is not None:
        db.delete(sub)
        db.commit()
    return Response(status_code=204)


@router.get("/card/subscriptions", response_model=List[TickerSubscriptionOut])
def list_ticker_subscriptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[TickerSubscriptionOut]:
    """The caller's per-ticker alerts, for Account → Notifications."""
    rows = db.execute(
        select(TickerSignalSubscription)
        .filter(TickerSignalSubscription.user_id == current_user.id)
        .order_by(
            TickerSignalSubscription.symbol,
            TickerSignalSubscription.saved_screen_id,
        )
    ).scalars().all()

    titles = {}
    for r in rows:
        if r.saved_screen_id not in titles:
            screen = db.get(SavedStrategy, r.saved_screen_id)
            titles[r.saved_screen_id] = screen.title if screen else None

    return [
        TickerSubscriptionOut(
            symbol=r.symbol,
            saved_screen_id=r.saved_screen_id,
            screen_title=titles.get(r.saved_screen_id),
            email_enabled=r.email_enabled,
            last_state=r.last_state,
            last_as_of=r.last_as_of.isoformat() if r.last_as_of else None,
        )
        for r in rows
    ]
