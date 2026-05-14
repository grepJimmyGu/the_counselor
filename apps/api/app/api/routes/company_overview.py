from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import CompanyOverviewResponse, TrendSection
from app.services.company_overview_service import CompanyOverviewService
from app.services.company_trend_service import CompanyTrendService

router = APIRouter(prefix="/api/company", tags=["company-overview"])
_service = CompanyOverviewService()
_trend_svc = CompanyTrendService()


@router.get("/{symbol}/overview", response_model=CompanyOverviewResponse)
async def get_company_overview(
    symbol: str,
    db: Session = Depends(get_db),
) -> CompanyOverviewResponse:
    """Full company overview including health, valuation, business map, market position."""
    try:
        return await _service.get_overview(db, symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{symbol}/trend", response_model=TrendSection)
def get_company_trend(
    symbol: str,
    db: Session = Depends(get_db),
) -> TrendSection:
    """
    Price trend metrics computed from price_bars (Alpha Vantage data).
    Returns 1M/3M/6M/12M performance, 50/200-day MAs, volume trend,
    SPY-relative strength, and 90-day price sparkline.

    Synchronous — no external API call. Reads directly from DB.
    Requires price history to be loaded via /api/data/warmup first.
    """
    sym = symbol.upper()
    try:
        td = _trend_svc.get_trend(sym, db)
        td = _trend_svc.get_relative_strength(td, db)

        if td.bar_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No price history found for {sym}. "
                       "Load history via /api/data/warmup first.",
            )

        return TrendSection(
            latest_price=td.latest_price,
            latest_date=td.latest_date.isoformat() if td.latest_date else None,
            perf_1m=td.perf_1m,
            perf_3m=td.perf_3m,
            perf_6m=td.perf_6m,
            perf_12m=td.perf_12m,
            ma_50=td.ma_50,
            ma_200=td.ma_200,
            price_vs_ma50=td.price_vs_ma50,
            price_vs_ma200=td.price_vs_ma200,
            vol_trend=td.vol_trend,
            avg_vol_20d=td.avg_vol_20d,
            avg_vol_65d=td.avg_vol_65d,
            rs_vs_spy_3m=td.rs_vs_spy_3m,
            rs_vs_spy_12m=td.rs_vs_spy_12m,
            price_series_90d=td.price_series_90d,
            bar_count=td.bar_count,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
