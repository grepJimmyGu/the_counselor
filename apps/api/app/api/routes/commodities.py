"""
Commodity trend data via ETF price proxies.
Reuses the existing CompanyTrendService (reads from price_bars).

ETF proxies:
  GOLD   → GLD   (SPDR Gold Shares)
  WTI    → USO   (United States Oil Fund)
  COPPER → COPX  (Global X Copper Miners ETF)
  WHEAT  → WEAT  (Teucrium Wheat Fund)
  SILVER → SLV
  NATGAS → UNG
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import TrendSection
from app.services.company_trend_service import CompanyTrendService

router = APIRouter(prefix="/api/commodities", tags=["commodities"])
_trend_svc = CompanyTrendService()

_ETF_MAP: dict[str, str] = {
    "GOLD":   "GLD",
    "WTI":    "USO",
    "CRUDE":  "USO",
    "OIL":    "USO",
    "COPPER": "COPX",
    "WHEAT":  "WEAT",
    "SILVER": "SLV",
    "NATGAS": "UNG",
    "CORN":   "CORN",
    "SOYBEAN":"SOYB",
}


@router.get("/{commodity}/trend", response_model=TrendSection)
def get_commodity_trend(
    commodity: str,
    db: Session = Depends(get_db),
) -> TrendSection:
    """
    Price trend metrics for a commodity, sourced from its ETF proxy price bars.

    Computed fields:
      - Latest price + date (from ETF adjusted close)
      - 1M / 3M / 6M / 12M performance
      - 50-day and 200-day moving averages
      - Price vs MA50 / MA200
      - Volume trend (20d vs 65d)
      - Relative performance vs SPY (3M and 12M)
      - 90-day price sparkline

    Requires price bars to be loaded via startup warmup or /api/admin/warmup-commodity-etfs.
    """
    sym = commodity.upper()
    etf = _ETF_MAP.get(sym)
    if not etf:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown commodity: {sym}. Supported: {list(_ETF_MAP.keys())}",
        )

    td = _trend_svc.get_trend(etf, db)

    if td.bar_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No price history for {sym} (ETF proxy: {etf}). "
                   "Warmup via POST /api/admin/warmup-commodity-etfs.",
        )

    td = _trend_svc.get_relative_strength(td, db)

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
        data_source="alpha_vantage_etf_proxy",
    )
