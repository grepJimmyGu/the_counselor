"""
Admin endpoints — internal maintenance operations.
Protected by INTERNAL_API_KEY header (same as community routes).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _require_internal_key(x_internal_key: str = Header(default="")) -> None:
    key = get_settings().internal_api_key
    if key and x_internal_key != key:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Prewarm health scores ─────────────────────────────────────────────────────

@router.post("/prewarm-health-scores")
async def trigger_prewarm_health_scores(
    max_symbols: int = 500,
    _: None = Depends(_require_internal_key),
) -> dict:
    """
    Trigger the S&P 500 health score pre-warm in background.
    Safe to call multiple times — only computes missing / stale scores.
    """
    from app.scripts.prewarm_health_scores import run_prewarm
    asyncio.create_task(run_prewarm(max_symbols=max_symbols))
    return {"status": "prewarm started", "max_symbols": max_symbols}


@router.get("/health-scores/status")
def health_scores_status(db: Session = Depends(get_db)) -> dict:
    """How many symbols have been scored and what sectors are covered."""
    try:
        total = db.execute(text("SELECT COUNT(*) FROM symbol_health_scores")).scalar() or 0
        sectors = db.execute(
            text("SELECT sector, COUNT(*) as n FROM symbol_health_scores WHERE sector IS NOT NULL GROUP BY sector ORDER BY n DESC LIMIT 10")
        ).fetchall()
        return {
            "total_symbols": total,
            "sectors": [{"sector": r[0], "count": r[1]} for r in sectors],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Supply chain / BI cache management ───────────────────────────────────────

@router.post("/refresh-bi/{symbol}")
async def refresh_business_intelligence(
    symbol: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
) -> dict:
    """
    Invalidate the 10-K business intelligence cache for a symbol.
    Next request to /api/company/{symbol}/overview will re-extract from SEC EDGAR.
    """
    sym = symbol.upper()
    try:
        result = db.execute(
            text("DELETE FROM company_business_intelligence WHERE symbol = :sym"),
            {"sym": sym},
        )
        db.commit()
        deleted = result.rowcount
        return {"symbol": sym, "deleted_rows": deleted, "status": "cache cleared — re-extraction will happen on next page load"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Commodity ETF price warmup ────────────────────────────────────────────────

_COMMODITY_ETFS = {
    "GOLD":   "GLD",
    "WTI":    "USO",
    "COPPER": "COPX",
    "WHEAT":  "WEAT",
    "SILVER": "SLV",
    "NATGAS": "UNG",
}

@router.post("/warmup-commodity-etfs")
async def warmup_commodity_etfs(
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
) -> dict:
    """
    Ensure price bars are loaded for commodity ETF proxies.
    GLD=Gold, USO=WTI, COPX=Copper, WEAT=Wheat.
    """
    from datetime import date, timedelta
    from app.services.alpha_vantage import AlphaVantageClient
    from app.services.price_cache_service import PriceCacheService

    client = AlphaVantageClient()
    svc = PriceCacheService(client)
    required_from = date.today() - timedelta(days=365 * 11)  # 11yr for 10yr pct computation

    results = {}
    for commodity, etf in _COMMODITY_ETFS.items():
        try:
            await svc.ensure_history(db, etf, required_from, force=False)
            from sqlalchemy import select, func
            from app.models.price_bar import PriceBar
            count = db.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.symbol == etf)) or 0
            results[commodity] = {"etf": etf, "bar_count": count, "status": "ok"}
        except Exception as exc:
            results[commodity] = {"etf": etf, "status": "error", "error": str(exc)[:100]}

    return {"results": results}


# ── Universe price-bars backfill (server-side, throttled, monitorable) ────────

@router.post("/backfill/universe")
async def trigger_universe_backfill(
    universe_id: str = "russell3000",
    rate_per_min: int = 50,      # AV paid tier is 75/min; default leaves headroom
    lookback_years: int = 3,
    _: None = Depends(_require_internal_key),
) -> dict:
    """Kick off a one-shot price-bars backfill for a standing universe on a
    background worker thread, then return immediately.

    Idempotent (skips symbols that already have fresh bars) and throttled to
    `rate_per_min` so it can't starve the live app's shared Alpha Vantage
    budget. Runs on its own thread (trap #21) so it never blocks /health.

    Poll `GET /api/admin/backfill/status` for live progress.
    """
    from app.services import universe_backfill as ub

    try:
        universe = ub.resolve_universe(universe_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rate = max(1, min(int(rate_per_min), ub.MAX_RATE_PER_MIN))
    started = ub.start_backfill_thread(
        universe, universe_id, rate, max(1, int(lookback_years))
    )
    if not started:
        raise HTTPException(
            status_code=409,
            detail="a backfill is already running — see GET /api/admin/backfill/status",
        )
    return {
        "status": "started",
        "universe": universe_id,
        "symbols": len(universe),
        "rate_per_min": rate,
        "lookback_years": lookback_years,
    }


@router.get("/backfill/status")
def universe_backfill_status(_: None = Depends(_require_internal_key)) -> dict:
    """Live progress of the most recent universe backfill (in-memory)."""
    from app.services import universe_backfill as ub

    return ub.get_status()


@router.post("/backfill/sectors")
def backfill_russell3000_sectors(
    dry_run: bool = False,
    _: None = Depends(_require_internal_key),
    db: Session = Depends(get_db),
) -> dict:
    """One-time (idempotent): overwrite SymbolCache.sector for every Russell
    3000 name with its canonical GICS label (app/data/russell3000_sectors).

    Fixes the mixed-taxonomy + null sector data that silently broke ~6/11
    sectors in the Sector screen (the picker sent FMP labels like "Technology"
    while the DB held GICS "Information Technology"). Fast — one SELECT + one
    commit, no external calls. Re-running just re-asserts the labels."""
    from sqlalchemy import select

    from app.data.russell3000_sectors import RUSSELL3000_SECTORS
    from app.models.symbol import SymbolCache

    if dry_run:
        return {"status": "dry-run", "would_set": len(RUSSELL3000_SECTORS)}

    symbols = list(RUSSELL3000_SECTORS)
    rows = (
        db.execute(select(SymbolCache).where(SymbolCache.symbol.in_(symbols)))
        .scalars()
        .all()
    )
    updated = 0
    unchanged = 0
    for row in rows:
        target = RUSSELL3000_SECTORS[row.symbol]
        if row.sector != target:
            row.sector = target
            updated += 1
        else:
            unchanged += 1
    db.commit()
    return {
        "status": "ok",
        "total": len(symbols),
        "updated": updated,
        "unchanged": unchanged,
        "missing_symbol_row": len(symbols) - len(rows),
    }


@router.post("/snapshot/warm")
async def trigger_snapshot_warm(_: None = Depends(_require_internal_key)) -> dict:
    """Warm the standing-universe signal_snapshot NOW — the same work the daily
    23:00-UTC cron does (warm_universe over sp500 + russell3000 from cached
    price_bars), runnable on demand so a freshly-registered universe is
    scannable immediately. Runs on a worker thread (trap #21) and returns at
    once. Poll GET /api/admin/snapshot/warm/status."""
    from app.services import snapshot_warm_trigger as sw

    if not sw.start_warm():
        raise HTTPException(
            status_code=409,
            detail="a warm is already running — see GET /api/admin/snapshot/warm/status",
        )
    return {"status": "started"}


@router.get("/snapshot/warm/status")
def snapshot_warm_status(_: None = Depends(_require_internal_key)) -> dict:
    """Status of the most recent on-demand snapshot warm (in-memory)."""
    from app.services import snapshot_warm_trigger as sw

    return sw.get_status()
