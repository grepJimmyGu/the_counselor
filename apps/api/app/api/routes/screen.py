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
    RankedSymbol,
    ScreenCountResponse,
    ScreenRankRequest,
    ScreenRankResponse,
    ScreenScanRequest,
    ScreenScanResponse,
)
from app.services.screener.rank_service import rank_service
from app.services.screener.scan_service import scan
from app.services.screener.signal_snapshot_service import SignalSnapshotService

logger = logging.getLogger("livermore.screener.api")

router = APIRouter(prefix="/api/screen", tags=["screener"])

# Snapshot columns used (in order of preference) as the cheap-proxy pre-order
# for the rank top-K cap, so a loose rule keeps the highest-momentum names
# rather than an alphabetical slice.
_PROXY_PRIMITIVES = ("time_series_momentum", "roc", "mom", "rank_return_6m")


def _momentum_proxy(db: Session, symbols: List[str]):
    """{symbol -> momentum score} from the snapshot's first available momentum
    column, for the rank top-K pre-order. None if the snapshot has no such
    column for these symbols (rank then falls back to scan order)."""
    if not symbols:
        return None
    frame = SignalSnapshotService().get_snapshot(db, symbols).frame
    for col in _PROXY_PRIMITIVES:
        if col in frame.columns:
            return {
                str(sym): float(val)
                for sym, val in frame[col].items()
                if val == val  # drop NaN
            }
    return None


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
        default_param_primitives=result.default_param_primitives,
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
        default_param_primitives=result.default_param_primitives,
    )


@router.post("/rank", response_model=ScreenRankResponse)
async def screen_rank(
    payload: ScreenRankRequest,
    auth: tuple = Depends(
        # The expensive step — backtests the matched subset. Sign-in-gated
        # (§3.6); the scan/count above stay anonymous-explorable.
        require_entitlement(needs_run_quota=False, allow_anonymous=False, template_id_field=None)
    ),
    db: Session = Depends(get_db),
) -> ScreenRankResponse:
    result = scan(
        db,
        payload.universe_id,
        payload.rules,
        symbols=payload.symbols,
        sector_membership=_db_sector_membership(db),
    )
    # NOTE (backlog — trap #13 / quota): rank backtests the matched subset
    # sequentially while holding this request `db`; on a cold-cache symbol each
    # run can await an AV fetch with the conn checked out. Bounded today by
    # sign-in gating + top_k<=200 + the warm-cache short-circuit, but a
    # fresh-SessionLocal-per-backtest + a per-tier run quota are tracked in
    # PROJECT_BACKLOG before this is heavily trafficked.
    rank_result = await rank_service.rank(
        db,
        result.matched,
        payload.strategy,
        as_of_date=result.as_of_date,
        top_k=payload.top_k,
        proxy_scores=_momentum_proxy(db, result.matched),
    )
    return ScreenRankResponse(
        ranked=[
            RankedSymbol(
                symbol=e.symbol,
                total_return=e.total_return,
                annualized_return=e.annualized_return,
                sharpe_ratio=e.sharpe_ratio,
                readings=result.readings.get(e.symbol, []),
            )
            for e in rank_result.ranked
        ],
        as_of_date=rank_result.as_of_date,
        matched_count=rank_result.matched_count,
        backtested_count=rank_result.backtested_count,
        dropped_count=rank_result.dropped_count,
        universe_size=result.universe_size,
        unsupported_primitives=result.unsupported_primitives,
        default_param_primitives=result.default_param_primitives,
    )
