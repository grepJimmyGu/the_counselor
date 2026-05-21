from __future__ import annotations

import json
import logging
import random
import re
import string
from datetime import date, datetime

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.entitlement_errors import upgrade_error
from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.models.user import User
from app.schemas.strategy_storage import (
    LivePerformanceResponse,
    PublicStrategyItem,
    SavedStrategyResponse,
    StrategySaveRequest,
    StrategySaveResponse,
    VisibilityUpdateRequest,
)
from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
)
from app.services.live_performance_service import get_cached_performance, get_live_performance

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def _make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base}-{suffix}"


@router.post("/save", response_model=StrategySaveResponse)
def save_strategy(
    req: StrategySaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategySaveResponse:
    """Save a backtest result as a slugged, optionally-public strategy.

    Auth + tier enforcement (added 2026-05-20 after a QA audit found this
    endpoint was completely unauthenticated):
      • Bearer token required (anonymous saves are not supported here; the
        anonymous one-shot flow lives in /api/anonymous/backtest/run, which
        leaves user_id=NULL on the BacktestRecord and is later attached by
        merge_anonymous_into_user on signup).
      • Tier cap: `ent.saved_strategies_max` counted across the user's own
        slugged records. Scout cap is 10; Strategist 25; Quant 10,000.
      • Scout override: `ent.saved_strategies_always_public=True` forces
        is_public=True regardless of what the request body sent. This is
        intentional — Scout = public-only is the explicit Stage 1a design.
    """
    weekly = get_or_create_current_weekly_usage(db, user.id)
    ent = get_entitlements(user, weekly)

    # Cap check (count this user's existing slugged records, not all saves)
    count = db.query(BacktestRecord).filter(
        BacktestRecord.user_id == user.id,
        BacktestRecord.slug.is_not(None),
    ).count()
    if count >= ent.saved_strategies_max:
        raise upgrade_error(
            "saved_strategies_quota_reached",
            current_tier=ent.tier,
            current_value=str(count),
            limit_value=str(ent.saved_strategies_max),
        )

    # Scout-tier override: force is_public=True.
    is_public = True if ent.saved_strategies_always_public else req.is_public

    record = db.scalar(select(BacktestRecord).where(BacktestRecord.id == req.backtest_id))

    if not record:
        # Record not in DB — this happens when the strategy was run locally or against a
        # different database (dev SQLite vs prod PostgreSQL). If the frontend sent the full
        # result payload, create a new record so the strategy can still be published.
        if not req.result_payload:
            raise HTTPException(
                status_code=404,
                detail="Backtest not found. Re-run the strategy to publish it.",
            )
        record = BacktestRecord(
            id=req.backtest_id,
            strategy_type=req.strategy_type,
            strategy_name=req.name,
            result_payload=req.result_payload,
            user_id=user.id,
        )
        db.add(record)
    else:
        # Existing record — verify the caller owns it (or claim it if legacy).
        # Legacy anonymous-era rows have user_id=None; first authed save claims them.
        if record.user_id and record.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not your backtest.")
        if record.user_id is None:
            record.user_id = user.id

    if record.slug:
        raise HTTPException(status_code=400, detail="Strategy already saved.")

    slug = _make_slug(req.name)
    record.slug = slug
    record.name = req.name
    record.is_public = is_public
    record.saved_at = datetime.utcnow()
    db.commit()

    return StrategySaveResponse(slug=slug, url=f"/strategies/{slug}", is_public=is_public)


@router.patch("/{slug}/visibility", response_model=StrategySaveResponse)
def update_visibility(
    slug: str,
    req: VisibilityUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategySaveResponse:
    """Toggle public/private visibility of a saved strategy.

    Owner check (added 2026-05-20): only the user who saved the strategy can
    flip its visibility. Legacy anonymous-era records (user_id=None) remain
    editable by anyone — pragmatic compatibility shim; tighten in a follow-up
    once those rows have been backfilled or migrated.

    Scout users have `saved_strategies_always_public=True` and the save flow
    forces is_public=True. They can still call this endpoint, but the request
    body's is_public is honored as-is — a Scout flipping their own strategy
    private is not the spec, but we don't block it explicitly here either,
    leaving the future Stage 5 tightening to revisit.
    """
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.slug == slug))
    if not record:
        raise HTTPException(status_code=404, detail="Strategy not found.")
    if record.user_id and record.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your strategy.")
    record.is_public = req.is_public
    db.commit()
    return StrategySaveResponse(
        slug=record.slug,  # type: ignore[arg-type]
        url=f"/strategies/{record.slug}",
        is_public=req.is_public,
    )


@router.get("/public", response_model=list[PublicStrategyItem])
def list_public_strategies(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[PublicStrategyItem]:
    """
    Public saved strategies. Live performance is returned only if already cached —
    it is never computed here (that would time out). Computation is triggered
    lazily via GET /api/strategies/{slug}/live-performance when a strategy is visited.
    Sorted by a lightweight trust score, not raw return alone.
    """
    rows = db.execute(
        text(
            "SELECT b.slug, b.name, b.saved_at,"
            " b.result_payload,"
            " COALESCE(u.upvotes, 0) AS upvote_count"
            " FROM backtests b"
            " LEFT JOIN ("
            "   SELECT strategy_slug, COUNT(*) AS upvotes"
            "   FROM strategy_upvotes GROUP BY strategy_slug"
            " ) u ON u.strategy_slug = b.slug"
            " WHERE b.slug IS NOT NULL AND b.is_public = TRUE"
            " ORDER BY b.saved_at DESC"
            " LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit, "offset": offset},
    ).fetchall()

    items: list[PublicStrategyItem] = []
    for r in rows:
        rm = r._mapping
        slug = rm["slug"]
        saved_at = rm["saved_at"]

        # Only use cached live performance — never trigger a fresh computation here
        live_perf = None
        try:
            cached = get_cached_performance(slug, db)
            if cached:
                ret_pct = round(cached.total_return * 100, 2) if cached.total_return is not None else None
                live_perf = LivePerformanceResponse(
                    slug=slug,
                    published_at=cached.published_at,
                    total_return=cached.total_return,
                    total_return_pct=ret_pct,
                    days_tracked=cached.days_tracked,
                    current_signal=cached.current_signal,
                    last_price_date=cached.last_price_date,
                    equity_curve=[],  # omit from listing for speed
                    error=cached.error,
                    computed_at=cached.computed_at,
                )
        except Exception as exc:
            logger.warning("Cached perf lookup failed for %s: %s", slug, exc)

        payload = rm["result_payload"] or {}
        trust_score = _strategy_trust_score(live_perf, rm["upvote_count"] or 0, payload)
        verification_status = _strategy_verification_status(live_perf)
        items.append(PublicStrategyItem(
            slug=slug,
            name=rm["name"],
            saved_at=saved_at,
            upvote_count=rm["upvote_count"] or 0,
            trust_score=trust_score,
            verification_status=verification_status,
            follower_count=0,
            live=live_perf,
        ))

    # Sort: verified/trusted strategies first, then by community support.
    def sort_key(item: PublicStrategyItem) -> tuple:
        return (item.trust_score, item.upvote_count, item.saved_at)

    items.sort(key=sort_key, reverse=True)
    return items


def _strategy_trust_score(
    live_perf: LivePerformanceResponse | None,
    upvote_count: int,
    payload: dict,
) -> int:
    score = 45.0
    metrics = payload.get("metrics", {}) if isinstance(payload, dict) else {}
    max_drawdown = metrics.get("max_drawdown")
    if max_drawdown is not None:
        try:
            score -= min(18.0, abs(float(max_drawdown)) * 45.0)
        except (TypeError, ValueError):
            pass

    score += min(16.0, upvote_count * 2.0)

    if live_perf:
        if live_perf.days_tracked:
            score += min(18.0, live_perf.days_tracked * 1.5)
        if live_perf.total_return is not None:
            score += max(-12.0, min(12.0, live_perf.total_return * 100.0))
        if live_perf.error:
            score -= 4.0
    else:
        score += 6.0  # saved public strategies are at least backtested artifacts

    return int(max(0, min(100, round(score))))


def _strategy_verification_status(live_perf: LivePerformanceResponse | None) -> str:
    if live_perf and live_perf.days_tracked > 0 and not live_perf.error:
        return "Live paper tracking"
    if live_perf and live_perf.error and "Published today" in live_perf.error:
        return "Tracking starts next session"
    return "Backtested"


@router.get("/{slug}/live-performance", response_model=LivePerformanceResponse)
async def get_strategy_live_performance(
    slug: str,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> LivePerformanceResponse:
    """Full live performance for a single strategy — includes complete equity curve."""
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.slug == slug))
    if not record:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    saved_at = record.saved_at
    published_at = saved_at.date() if hasattr(saved_at, "date") else datetime.utcnow().date()
    payload = record.result_payload or {}
    strategy_json = payload.get("strategy_json", {})

    if not strategy_json:
        raise HTTPException(status_code=422, detail="Strategy JSON not available.")

    lp = await get_live_performance(slug, published_at, strategy_json, db, force_refresh=refresh)
    ret_pct = round(lp.total_return * 100, 2) if lp.total_return is not None else None
    return LivePerformanceResponse(
        slug=slug,
        published_at=published_at,
        total_return=lp.total_return,
        total_return_pct=ret_pct,
        days_tracked=lp.days_tracked,
        current_signal=lp.current_signal,
        last_price_date=lp.last_price_date,
        equity_curve=lp.equity_curve,
        error=lp.error,
        computed_at=lp.computed_at,
    )


@router.get("/{slug}", response_model=SavedStrategyResponse)
def get_saved_strategy(slug: str, db: Session = Depends(get_db)) -> SavedStrategyResponse:
    record = db.scalar(
        select(BacktestRecord).where(BacktestRecord.slug == slug)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    p = record.result_payload
    return SavedStrategyResponse(
        slug=record.slug,  # type: ignore[arg-type]
        name=record.name,  # type: ignore[arg-type]
        saved_at=record.saved_at,  # type: ignore[arg-type]
        is_public=bool(record.is_public),
        strategy_json=p.get("strategy_json", {}),
        metrics=p.get("metrics", {}),
        equity_curve=p.get("equity_curve", []),
        benchmark_curve=p.get("benchmark_curve", []),
        drawdown_curve=p.get("drawdown_curve", []),
        trade_log=p.get("trade_log", []),
        warnings=p.get("warnings", []),
    )
