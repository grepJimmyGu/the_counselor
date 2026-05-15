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
