"""Notification routes — PRD-19 (Phase B re-shape).

In-app banner endpoints + notification preferences. Email/webhook
preferences are handled by existing signal subscription routes
(apps/api/app/api/routes/signals.py).

GET    /api/me/notifications/pending   — pending banner entries
POST   /api/me/notifications/{id}/ack  — dismiss a banner entry
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification_banner import NotificationBannerEntry
from app.models.user import User

router = APIRouter(prefix="/api/me", tags=["notifications"])


class PendingBannerItem(BaseModel):
    id: int
    title: str
    body: str
    strategy_slug: Optional[str] = None
    created_at: datetime


@router.get("/notifications/pending", response_model=list[PendingBannerItem])
def list_pending_banners(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PendingBannerItem]:
    """Return unacknowledged banner entries for the current user."""
    rows = (
        db.query(NotificationBannerEntry)
        .filter(
            NotificationBannerEntry.user_id == current_user.id,
            NotificationBannerEntry.acknowledged_at.is_(None),
        )
        .order_by(NotificationBannerEntry.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        PendingBannerItem(
            id=r.id,
            title=r.title,
            body=r.body,
            strategy_slug=r.strategy_slug,
            created_at=r.created_at or datetime.utcnow(),
        )
        for r in rows
    ]


@router.post(
    "/notifications/{entry_id}/ack",
    status_code=204,
    response_class=Response,
)
def acknowledge_banner(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Mark a banner entry as acknowledged (soft-delete).

    Trap #7 (apps/api/CLAUDE.md): FastAPI 0.115+ asserts at import time
    that routes coded 204 can't serialize a body. The original `-> None`
    signature tripped the assertion, breaking app startup. Returning an
    explicit `Response(status_code=204)` with `response_class=Response`
    keeps the route valid.
    """
    row = db.get(NotificationBannerEntry, entry_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    row.acknowledged_at = datetime.utcnow()
    db.commit()
    return Response(status_code=204)
