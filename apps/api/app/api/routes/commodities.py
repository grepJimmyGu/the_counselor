"""
Commodity trend data.

Spot price (for display): sourced from Alpha Vantage commodity endpoints
  (WTI → $/bbl, GOLD derived from GLD → $/oz, COPPER → $/lb, WHEAT → ¢/bu).
  Stored in price_bars as WTI_SPOT, GOLD_SPOT, COPPER_SPOT, WHEAT_SPOT.

Technical signals (CMF, MA, volume): sourced from ETF proxy price bars
  GOLD   → GLD   (SPDR Gold Shares)
  WTI    → USO   (United States Oil Fund)
  COPPER → COPX  (Global X Copper Miners ETF)
  WHEAT  → WEAT  (Teucrium Wheat Fund)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company_overview import TrendSection
from app.services.company_trend_service import CompanyTrendService
from app.services.commodity_spot_service import CommoditySpotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commodities", tags=["commodities"])
_trend_svc = CompanyTrendService()
_spot_svc = CommoditySpotService()

# ETF used for CMF / technical analysis (volume-based signals)
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

# Canonical commodity names for the *_SPOT symbols (WTI, GOLD, COPPER, WHEAT)
_SPOT_SUPPORTED = frozenset({"WTI", "CRUDE", "OIL", "GOLD", "COPPER", "WHEAT"})
_SPOT_COMMODITY_KEY = {"CRUDE": "WTI", "OIL": "WTI"}  # aliases


@router.get("/{commodity}/trend", response_model=TrendSection)
def get_commodity_trend(
    commodity: str,
    db: Session = Depends(get_db),
) -> TrendSection:
    """
    Price trend metrics for a commodity.

    latest_price / latest_date: actual commodity spot price ($/bbl, $/oz, $/lb, ¢/bu)
      sourced from Alpha Vantage commodity API (stored as *_SPOT bars).
      Falls back to ETF proxy price when spot data is unavailable.

    perf_1m/3m/6m/12m: computed from spot price monthly series (or ETF if unavailable).
    ma_50 / ma_200 / vol_trend: from ETF proxy (uses real OHLCV).
    """
    sym = commodity.upper()
    etf = _ETF_MAP.get(sym)
    if not etf:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown commodity: {sym}. Supported: {list(_ETF_MAP.keys())}",
        )

    # Fetch ETF-based trend (CMF, MAs, volume, sparkline, RS vs SPY)
    td = _trend_svc.get_trend(etf, db)

    if td.bar_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No price history for {sym} (ETF proxy: {etf}). "
                   "Warmup via POST /api/admin/warmup-commodity-etfs.",
        )

    td = _trend_svc.get_relative_strength(td, db)

    # Overlay actual spot price when available (replaces ETF price for display)
    spot_key = _SPOT_COMMODITY_KEY.get(sym, sym)
    if spot_key in _SPOT_SUPPORTED:
        try:
            quote = _spot_svc.get_quote(spot_key, db)
            if quote:
                td.latest_price = quote.price
                td.latest_date = quote.date
                # Use spot-derived performance (month-over-month) if available
                if quote.perf_1m is not None:
                    td.perf_1m = quote.perf_1m
                if quote.perf_3m is not None:
                    td.perf_3m = quote.perf_3m
                if quote.perf_6m is not None:
                    td.perf_6m = quote.perf_6m
                if quote.perf_12m is not None:
                    td.perf_12m = quote.perf_12m
                logger.debug(
                    "Commodity spot overlay: %s = %.4f %s (date: %s)",
                    spot_key, quote.price, quote.display_unit, quote.date,
                )
        except Exception as exc:
            logger.warning(
                "Spot price overlay failed for %s, falling back to ETF: %s", sym, exc
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
        data_source="alpha_vantage_spot+etf_proxy",
    )
