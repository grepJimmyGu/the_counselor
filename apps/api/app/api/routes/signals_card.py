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

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.signal_card import SignalCard
from app.services.signal_card_service import evaluate_cards

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalCardBatchRequest(BaseModel):
    saved_strategy_ids: List[str] = Field(default_factory=list)


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
