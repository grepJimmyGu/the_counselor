from __future__ import annotations

import random
import re
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRecord
from app.schemas.strategy_storage import SavedStrategyResponse, StrategySaveRequest, StrategySaveResponse

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
    record.is_public = True
    record.saved_at = datetime.utcnow()
    db.commit()

    return StrategySaveResponse(slug=slug, url=f"/strategies/{slug}")


@router.get("/{slug}", response_model=SavedStrategyResponse)
def get_saved_strategy(slug: str, db: Session = Depends(get_db)) -> SavedStrategyResponse:
    record = db.scalar(
        select(BacktestRecord).where(
            BacktestRecord.slug == slug,
            BacktestRecord.is_public.is_(True),
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="Strategy not found.")

    p = record.result_payload
    return SavedStrategyResponse(
        slug=record.slug,  # type: ignore[arg-type]
        name=record.name,  # type: ignore[arg-type]
        saved_at=record.saved_at,  # type: ignore[arg-type]
        strategy_json=p.get("strategy_json", {}),
        metrics=p.get("metrics", {}),
        equity_curve=p.get("equity_curve", []),
        benchmark_curve=p.get("benchmark_curve", []),
        drawdown_curve=p.get("drawdown_curve", []),
        trade_log=p.get("trade_log", []),
        warnings=p.get("warnings", []),
    )
