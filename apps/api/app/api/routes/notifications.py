"""Notification routes — PRD-19 (Phase B re-shape).

In-app banner endpoints + notification preferences. Email/webhook
preferences are handled by existing signal subscription routes
(apps/api/app/api/routes/signals.py).

GET    /api/me/notifications/pending   — pending banner entries (the website's banner)
POST   /api/me/notifications/{id}/ack  — dismiss a banner entry

The notice inbox (2026-11-23, `app/services/notice_inbox.py`):

GET    /api/me/notices                       — unread notices grouped by source, and what is muted
GET    /api/me/notices/sources/{source_id}   — one strategy or screen's notices, read or not
POST   /api/me/notices/read                  — mark notices read, by id or by source
PUT    /api/me/notices/mutes/{source_id}     — silence a strategy or screen (notices and emails)
DELETE /api/me/notices/mutes/{source_id}     — undo it
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification_banner import NotificationBannerEntry
from app.models.user import User
from app.services import notice_inbox

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


# ── the notice inbox ─────────────────────────────────────────────────────────


class NoticeView(BaseModel):
    id: int
    title: str
    body: str
    symbol: Optional[str] = None
    source_kind: str          # strategy | screen | stock_alert | position
    level: str                # act | changed | fyi
    created_at: datetime
    read: bool


class NoticeGroupView(BaseModel):
    source_id: Optional[str] = None   # None: notices with no strategy behind them
    source_kind: str                  # strategy | screen | other
    title: str
    level: str                        # the most important unread notice
    unread_count: int
    latest_at: datetime
    muted: bool
    notices: List[NoticeView]


class MutedSourceView(BaseModel):
    source_id: str
    source_kind: str
    title: str


class NoticeInboxView(BaseModel):
    groups: List[NoticeGroupView]
    muted: List[MutedSourceView]


class NoticeSourceView(BaseModel):
    source_id: str
    source_kind: str
    title: str
    muted: bool
    notices: List[NoticeView]


class MarkReadRequest(BaseModel):
    ids: Optional[List[int]] = None
    source_id: Optional[str] = None


class MarkReadResponse(BaseModel):
    marked: int


def _notice_view(n: notice_inbox.Notice) -> NoticeView:
    return NoticeView(**vars(n))


@router.get("/notices", response_model=NoticeInboxView)
def notice_inbox_view(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoticeInboxView:
    """Unread notices, one group per strategy or screen, most important first.

    Exits on held positions are not here: they are listed as decisions on
    their own. Nothing here changes a position or sends an order."""
    groups, muted = notice_inbox.inbox(db, current_user.id)
    return NoticeInboxView(
        groups=[
            NoticeGroupView(
                **{k: v for k, v in vars(g).items() if k != "notices"},
                notices=[_notice_view(n) for n in g.notices],
            )
            for g in groups
        ],
        muted=[MutedSourceView(**vars(m)) for m in muted],
    )


@router.get("/notices/sources/{source_id}", response_model=NoticeSourceView)
def notice_source_view(
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoticeSourceView:
    """What one strategy or screen has sent, read or not, newest first."""
    try:
        h = notice_inbox.history(db, current_user.id, source_id)
    except notice_inbox.UnknownSource:
        raise HTTPException(status_code=404, detail="That strategy or screen isn't yours.")
    return NoticeSourceView(
        source_id=h.source_id, source_kind=h.source_kind, title=h.title,
        muted=h.muted, notices=[_notice_view(n) for n in h.notices],
    )


@router.post("/notices/read", response_model=MarkReadResponse)
def mark_notices_read(
    payload: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarkReadResponse:
    """Mark notices read: the ones named, or every unread one from a source."""
    try:
        marked = notice_inbox.mark_read(
            db, current_user.id, ids=payload.ids, source_id=payload.source_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MarkReadResponse(marked=marked)


@router.put("/notices/mutes/{source_id}", status_code=204, response_class=Response)
def mute_notice_source(
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Silence a strategy or screen: no new notices in the inbox and no
    signal-change emails from it. Its unread notices are marked read. Exits
    on held positions still come through."""
    try:
        notice_inbox.mute(db, current_user.id, source_id)
    except notice_inbox.UnknownSource:
        raise HTTPException(status_code=404, detail="That strategy or screen isn't yours.")
    return Response(status_code=204)


@router.delete("/notices/mutes/{source_id}", status_code=204, response_class=Response)
def unmute_notice_source(
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    notice_inbox.unmute(db, current_user.id, source_id)
    return Response(status_code=204)
