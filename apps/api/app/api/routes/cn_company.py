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
        # td.latest_date is a datetime.date; TrendSection.latest_date is
        # Optional[str]. Returning td directly hit FastAPI's Pydantic v2
        # response validation (`string_type` error) and 500'd every CN
        # request — this mirrors the US handler's explicit isoformat in
        # company_overview.py:69.
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
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"CN trend unavailable for {symbol}: {exc}",
        ) from exc
