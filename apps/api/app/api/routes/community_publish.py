"""Published-strategy routes (Stage 4a).

Distinct from the existing community.py (which handles per-ticker community
signals from PRD-12/13/14). All routes here live under
/api/community/strategies/*.

  POST   /api/community/strategies          — publish (auth required)
  GET    /api/community/strategies          — public feed (no auth needed)
  GET    /api/community/strategies/{slug}   — public detail (no auth needed)
  PATCH  /api/community/strategies/{id}     — edit (owner only)
  DELETE /api/community/strategies/{id}     — soft delete (owner only)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.published_strategy import PublishedStrategy
from app.models.user import User
from app.services import community_publish_service as svc
from app.services.attribution_service import track_visit
from app.services.community_publish_service import PublishStrategyRequest

router = APIRouter(prefix="/api/community/strategies", tags=["community_publish"])

# Stage 4a: a separate attribution-tracking router lives at
# /api/community/attribution/* so it's discoverable next to the publish routes.
attribution_router = APIRouter(prefix="/api/community/attribution", tags=["attribution"])


# ── Response schemas ─────────────────────────────────────────────────────────


class AuthorPublic(BaseModel):
    id: str
    handle: Optional[str]
    display_name: Optional[str]
    badge: Optional[str] = None  # "verified" | "creator" | None

    model_config = {"from_attributes": True}


class PublishedStrategySummary(BaseModel):
    id: str
    slug: str
    title: str
    description: Optional[str]
    strategy_type: str
    universe: list[str]
    benchmark: str
    metrics: dict
    follow_count: int
    like_count: int
    comment_count: int
    view_count: int
    created_at: datetime
    author: AuthorPublic


class PublishedStrategyDetail(PublishedStrategySummary):
    strategy_json: dict
    equity_curve: list[dict]


class FeedResponse(BaseModel):
    items: list[PublishedStrategySummary]
    page: int
    page_size: int


class UpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _badge_for(user: User) -> Optional[str]:
    """Quant tier → 'verified' badge. Creator (Stage 5) → 'creator'."""
    if not user or not user.plan:
        return None
    if user.plan.tier == "quant":
        # Stage 5 may upgrade this to 'creator' for users in the program.
        return "verified"
    return None


def _author_for(db: Session, user_id: str) -> AuthorPublic:
    user = db.get(User, user_id)
    if user is None:
        return AuthorPublic(id=user_id, handle=None, display_name=None, badge=None)
    return AuthorPublic(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        badge=_badge_for(user),
    )


def _summary(row: PublishedStrategy, db: Session) -> PublishedStrategySummary:
    return PublishedStrategySummary(
        id=row.id,
        slug=row.slug,
        title=row.title,
        description=row.description,
        strategy_type=row.strategy_type,
        universe=list(row.universe_snapshot or []),
        benchmark=row.benchmark_snapshot,
        metrics=row.metrics_snapshot or {},
        follow_count=row.follow_count,
        like_count=row.like_count,
        comment_count=row.comment_count,
        view_count=row.view_count,
        created_at=row.created_at,
        author=_author_for(db, row.user_id),
    )


def _detail(row: PublishedStrategy, db: Session) -> PublishedStrategyDetail:
    summary = _summary(row, db)
    return PublishedStrategyDetail(
        **summary.model_dump(),
        strategy_json=row.strategy_json or {},
        equity_curve=list(row.equity_curve_snapshot or []),
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("", response_model=PublishedStrategyDetail, status_code=201)
def create_published(
    payload: PublishStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishedStrategyDetail:
    row = svc.publish_strategy(db, current_user, payload)
    return _detail(row, db)


@router.get("", response_model=FeedResponse)
def list_published(
    sort: str = Query(default="trending", pattern="^(trending|newest|top_returns|top_sharpe)$"),
    strategy_type: Optional[str] = Query(default=None, max_length=64),
    ticker: Optional[str] = Query(default=None, max_length=20),
    handle: Optional[str] = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> FeedResponse:
    rows = svc.list_feed(
        db,
        sort=sort,
        strategy_type=strategy_type,
        ticker=ticker,
        handle=handle,
        page=page,
        page_size=page_size,
    )
    return FeedResponse(
        items=[_summary(r, db) for r in rows],
        page=page,
        page_size=page_size,
    )


@router.get("/{slug}", response_model=PublishedStrategyDetail)
def get_published(
    slug: str,
    db: Session = Depends(get_db),
) -> PublishedStrategyDetail:
    row = svc.get_by_slug(db, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    svc.increment_view(db, slug)
    # increment_view commits; re-fetch the row for accurate view_count
    row = svc.get_by_slug(db, slug) or row
    return _detail(row, db)


@router.patch("/{strategy_id}", response_model=PublishedStrategyDetail)
def update_published(
    strategy_id: str,
    payload: UpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishedStrategyDetail:
    row = svc.update_strategy(
        db, current_user.id, strategy_id,
        title=payload.title, description=payload.description,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return _detail(row, db)


@router.delete("/{strategy_id}", status_code=204, response_class=Response)
def delete_published(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    ok = svc.soft_delete(db, current_user.id, strategy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    return Response(status_code=204)


# ── Attribution ───────────────────────────────────────────────────────────────


class TrackVisitRequest(BaseModel):
    url: str = Field(..., max_length=500)
    via: str = Field(..., min_length=1, max_length=32)


class TrackVisitResponse(BaseModel):
    tracked: bool


@attribution_router.post("/track", response_model=TrackVisitResponse)
def track_attribution_visit(
    payload: TrackVisitRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TrackVisitResponse:
    """Called from /s/[slug] page mount when ?via=<handle> is in the URL.
    Resolves the handle to a user, sets livermore_vsid cookie if missing,
    records the visit. Returns silently if the handle is unknown."""
    visit = track_visit(
        db, request, response,
        via_handle=payload.via,
        landed_url=payload.url,
    )
    return TrackVisitResponse(tracked=visit is not None)
