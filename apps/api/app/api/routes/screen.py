"""Market Screener — scan/count endpoints (PRD-23a §3.5-3.6).

`POST /api/screen/scan`  — a composed reading + a universe -> matched basket
                           + per-symbol satisfied readings.
`POST /api/screen/count` — the same filter, count only (the live funnel).

Both are pure reads over the pre-warmed `signal_snapshot` — no backtest (the
rank step is PRD-23a slice 5). `allow_anonymous=True` so the mode is
explorable pre-sign-in (trap #18); the expensive rank-by-backtest is the
sign-in-gated step.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.data.sp500_tickers import SP500_TICKERS
from app.db.session import get_db
from app.models.symbol import SymbolCache
from app.schemas.screener_scan import (
    ScreenCountResponse,
    ScreenScanRequest,
    ScreenScanResponse,
)
from app.services.screener.scan_service import scan

logger = logging.getLogger("livermore.screener.api")

router = APIRouter(prefix="/api/screen", tags=["screener"])


def _db_sector_membership(db: Session):
    """sector_<key> membership from SymbolCache.sector, intersected with the
    S&P 500 standard (expand-only + snapshot coverage). v1 matches the sector
    string the client sends; sector-label normalization is a follow-up."""

    def lookup(key: str) -> List[str]:
        rows = (
            db.execute(
                select(SymbolCache.symbol).where(
                    func.lower(SymbolCache.sector) == key.lower()
                )
            )
            .scalars()
            .all()
        )
        return [s for s in rows if s in SP500_TICKERS]

    return lookup


@router.post("/scan", response_model=ScreenScanResponse)
async def screen_scan(
    payload: ScreenScanRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=True, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenScanResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    return ScreenScanResponse(
        matched=result.matched,
        readings=result.readings,
        as_of_date=result.as_of_date,
        universe_size=result.universe_size,
        matched_count=result.matched_count,
        unsupported_primitives=result.unsupported_primitives,
    )


@router.post("/count", response_model=ScreenCountResponse)
async def screen_count(
    payload: ScreenScanRequest,
    auth: tuple = Depends(
        require_entitlement(needs_run_quota=False, allow_anonymous=True, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenCountResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    return ScreenCountResponse(
        matched_count=result.matched_count,
        universe_size=result.universe_size,
        as_of_date=result.as_of_date,
        unsupported_primitives=result.unsupported_primitives,
    )
