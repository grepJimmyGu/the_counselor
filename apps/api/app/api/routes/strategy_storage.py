from __future__ import annotations

import random
import re
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.strategy_storage import (
    PublicStrategyItem,
    SavedStrategyResponse,
    StrategySaveRequest,
    StrategySaveResponse,
    VisibilityUpdateRequest,
)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def _make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base}-{suffix}"


@router.post("/save", response_model=StrategySaveResponse)
def save_strategy(req: StrategySaveRequest, db: Session = Depends(get_db)) -> StrategySaveResponse:
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.id == req.backtest_id))
    if not record:
        raise HTTPException(status_code=404, detail="Backtest not found.")
    if record.slug:
        raise HTTPException(status_code=400, detail="Strategy already saved.")

    slug = _make_slug(req.name)
    record.slug = slug
    record.name = req.name
    record.is_public = req.is_public
    record.saved_at = datetime.utcnow()
    db.commit()

    return StrategySaveResponse(slug=slug, url=f"/strategies/{slug}", is_public=req.is_public)


@router.patch("/{slug}/visibility", response_model=StrategySaveResponse)
def update_visibility(
    slug: str, req: VisibilityUpdateRequest, db: Session = Depends(get_db)
) -> StrategySaveResponse:
    """Toggle public/private visibility of a saved strategy."""
    record = db.scalar(select(BacktestRecord).where(BacktestRecord.slug == slug))
    if not record:
        raise HTTPException(status_code=404, detail="Strategy not found.")
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
    """All public saved strategies, newest first, with upvote counts."""
    rows = db.execute(
        text(
            "SELECT b.slug, b.name, b.saved_at,"
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

    return [
        PublicStrategyItem(
            slug=r._mapping["slug"],
            name=r._mapping["name"],
            saved_at=r._mapping["saved_at"],
            upvote_count=r._mapping["upvote_count"] or 0,
        )
        for r in rows
    ]


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
