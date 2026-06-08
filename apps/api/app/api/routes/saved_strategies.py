"""Saved strategies CRUD (Stage 1a).

POST   /api/strategies          — create (Scout cap + auto-public enforced)
GET    /api/strategies          — list current user's saves
GET    /api/strategies/{id}     — read (owner or public)
DELETE /api/strategies/{id}     — delete (owner only)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest

# NOTE: mounted at /api/saved-strategies (not /api/strategies) to avoid colliding
# with the legacy PRD-02 strategy_storage.py routes which still serve the slug-based
# Workspace flow. Stage 4 will reconcile the two surfaces.
router = APIRouter(prefix="/api/saved-strategies", tags=["saved_strategies"])


class SavedStrategyResponse(BaseModel):
    id: str
    user_id: str
    title: str
    strategy_json: dict
    is_public: bool
    backtest_record_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=SavedStrategyResponse, status_code=201)
def create_saved_strategy(
    payload: SaveStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    """Save a strategy. Scout: forced public + 10 cap; Strategist+: respects is_public + 25/unlimited cap."""
    strategy = saved_strategy_service.save_strategy(db, current_user, payload)
    return SavedStrategyResponse.model_validate(strategy)


@router.get("", response_model=list[SavedStrategyResponse])
def list_saved_strategies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedStrategyResponse]:
    rows = saved_strategy_service.list_user_strategies(db, current_user.id)
    return [SavedStrategyResponse.model_validate(r) for r in rows]


@router.get("/{strategy_id}", response_model=SavedStrategyResponse)
def get_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedStrategyResponse:
    row = saved_strategy_service.get_strategy(db, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    # Public strategies are readable by anyone authenticated; private only by owner.
    if not row.is_public and row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return SavedStrategyResponse.model_validate(row)


@router.delete("/{strategy_id}", status_code=204, response_class=Response)
def delete_saved_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    deleted = saved_strategy_service.delete_strategy(db, current_user.id, strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return Response(status_code=204)


# ── PRD-19: Mark-as-Executed retention metric loop ──────────────────────────


class MarkAsExecutedRequest(BaseModel):
    """User-attested action log. Optional free-text note bounded to 560
    chars per PRD §4 (matches the email-embed preview limit)."""
    user_note: Optional[str] = None


class MarkAsExecutedResponse(BaseModel):
    ok: bool
    latency_seconds: int  # signal_event.created_at → executed_at
    signal_event_id: str
    executed_at: datetime
    # True if a row already existed for (user, signal_event) — idempotent.
    # The endpoint never errors on repeat clicks; it just returns the
    # existing row. Lets the frontend optimistic-UI button stay idempotent
    # without race-condition worry.
    idempotent: bool


@router.post(
    "/{strategy_id}/mark-executed",
    response_model=MarkAsExecutedResponse,
)
def mark_strategy_executed(
    strategy_id: str,
    payload: MarkAsExecutedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarkAsExecutedResponse:
    """Log that the current user acted on the latest signal for this
    strategy. Idempotent — second click on the same notification returns
    the existing row.

    The retention metric Sprint A is trying to measure
    (HANDOFF §7): time from `signal_event.created_at` to `executed_at`.
    PostHog captures it as `notification_executed` with `latency_seconds`.

    Compliance note: this is a user attestation, not a Livermore claim
    of trade placement (PRD §"Compliance" — Mark-as-Executed event is
    user-attested only).

    Failures:
      - 404 if the strategy doesn't exist OR isn't owned by the caller
        (the message is intentionally the same to avoid leaking strategy
        existence to non-owners)
      - 404 if no SignalEvent exists for this strategy yet (nothing to
        mark — the user hasn't received a notification at all)
    """
    from uuid import uuid4
    from sqlalchemy import select, desc
    from app.models.mark_as_executed_event import MarkAsExecutedEvent
    from app.models.saved_strategy import SavedStrategy
    from app.models.signal_event import SignalEvent

    # Snapshot scalars (trap #17 — DB-bound ORM instances expire across
    # commits; reading user_id / current_user.id again after the
    # MarkAsExecutedEvent commit below could trigger DetachedInstanceError
    # in some configurations).
    user_id: str = current_user.id

    # 1. Resolve strategy + verify ownership. Public strategies don't count;
    # you can only mark-executed on something you saved.
    strategy = db.get(SavedStrategy, strategy_id)
    if strategy is None or strategy.user_id != user_id:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    # 2. Find the latest SignalEvent for this strategy. If none, there's
    # nothing to act on — return 404 so the frontend can degrade gracefully.
    latest_event = db.execute(
        select(SignalEvent)
        .where(SignalEvent.saved_strategy_id == strategy_id)
        .order_by(desc(SignalEvent.created_at))
        .limit(1)
    ).scalar_one_or_none()
    if latest_event is None:
        raise HTTPException(
            status_code=404,
            detail="No signal event to mark as executed for this strategy.",
        )

    # 3. Idempotency check — has the user already marked THIS specific
    # signal event as executed? The UNIQUE index on
    # (user_id, signal_event_id) backs this query.
    existing = db.execute(
        select(MarkAsExecutedEvent).where(
            MarkAsExecutedEvent.user_id == user_id,
            MarkAsExecutedEvent.signal_event_id == latest_event.id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Idempotent — return the existing row's data. No write, no
        # PostHog re-capture (avoids inflating the retention metric with
        # duplicate clicks).
        latency = int((existing.executed_at - latest_event.created_at).total_seconds())
        return MarkAsExecutedResponse(
            ok=True,
            latency_seconds=max(0, latency),
            signal_event_id=latest_event.id,
            executed_at=existing.executed_at,
            idempotent=True,
        )

    # 4. Write the new attestation. `datetime.utcnow()` to match the
    # model default's TZ semantics (naive UTC).
    now = datetime.utcnow()
    event = MarkAsExecutedEvent(
        id=str(uuid4()),
        user_id=user_id,
        signal_event_id=latest_event.id,
        saved_strategy_id=strategy_id,
        executed_at=now,
        user_note=(payload.user_note.strip() if payload.user_note else None),
    )
    db.add(event)
    db.commit()

    latency = int((now - latest_event.created_at).total_seconds())

    # 5. PostHog event for the retention metric. PRD-19 §7 names this
    # `notification_executed` with `latency_seconds`. Best-effort — never
    # blocks the response, never raises.
    try:
        from app.services.posthog_service import ph_capture  # type: ignore[attr-defined]
        ph_capture(
            user_id=user_id,
            event="notification_executed",
            properties={
                "latency_seconds": max(0, latency),
                "saved_strategy_id": strategy_id,
                "signal_event_id": latest_event.id,
                "has_user_note": bool(payload.user_note),
            },
        )
    except Exception:
        # PostHog being down / misconfigured / module absent must never
        # break the user action. The DB row is the source of truth for
        # the metric; PostHog is convenience for the dashboard view.
        pass

    return MarkAsExecutedResponse(
        ok=True,
        latency_seconds=max(0, latency),
        signal_event_id=latest_event.id,
        executed_at=now,
        idempotent=False,
    )
