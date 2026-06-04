"""CN company overview route — Phase 3d (2026-06-04).

Serves GET /api/cn/company/{symbol}/overview and /trend for A-share stocks.
Delegates to cn_overview_service (overview) and CompanyTrendService (trend,
price-bars-only — no FMP dependency, works for any symbol with price data).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import CompanyOverviewResponse, TrendSection
from app.services.cn_overview_service import get_cn_company_overview
from app.services.company_trend_service import CompanyTrendService

router = APIRouter(prefix="/api/cn", tags=["cn-company"])


@router.get("/company/{symbol}/overview", response_model=CompanyOverviewResponse)
async def cn_company_overview(
    symbol: str,
    db: Session = Depends(get_db),
) -> CompanyOverviewResponse:
    """CN company overview — FMP profile + peers + AKShare financials/news.
    Degrades gracefully when AKShare is unavailable."""
    try:
        return await get_cn_company_overview(symbol.upper())
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"CN company overview unavailable for {symbol}: {exc}",
        ) from exc

_trend_svc = CompanyTrendService()


@router.get("/company/{symbol}/trend", response_model=TrendSection)
def cn_company_trend(
    symbol: str,
    db: Session = Depends(get_db),
) -> TrendSection:
    """CN stock trend — computed entirely from price_bars (no API call).
    Same service the US endpoint uses."""
    try:
        sym = symbol.upper()
        td = _trend_svc.get_trend(sym, db)
        td = _trend_svc.get_relative_strength(td, db)
        return td
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"CN trend unavailable for {symbol}: {exc}",
        ) from exc
