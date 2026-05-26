"""Asset Behavior Fingerprint endpoint — Module 2 (2026-05-26).

Exposes:

  GET /api/assets/{symbol}/behavior

Returns the diagnostic payload defined in
`app/schemas/asset_behavior.py`. Computed by
`app/services/asset_behavior_service.py` on top of the existing
`PriceDataService` cache — so the same price rows that drive backtests
power this card too.

No auth gate (matches the existing /api/data/daily/{symbol} pattern). Pure
read endpoint with a small data footprint per request.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.asset_behavior import AssetBehaviorFingerprintResponse
from app.services.asset_behavior_service import compute_asset_behavior_fingerprint
from app.services.price_data_service import PriceDataService

router = APIRouter(prefix="/api/assets", tags=["asset-behavior"])

_price_data_service = PriceDataService()

# Pull ~6 years of daily bars so the 5y vol + drawdown + 200-day MA
# trending-pct all have full history. The PriceDataService cache
# transparently fetches from AlphaVantage on first request and serves from
# Postgres thereafter.
_LOOKBACK_YEARS = 6


@router.get("/{symbol}/behavior", response_model=AssetBehaviorFingerprintResponse)
async def get_asset_behavior(
    symbol: str,
    db: Session = Depends(get_db),
) -> AssetBehaviorFingerprintResponse:
    """Return the Asset Behavior Fingerprint for a single ticker."""
    symbol_clean = (symbol or "").upper().strip()
    if not symbol_clean:
        raise HTTPException(status_code=422, detail="symbol is required")

    today = date.today()
    start = today - timedelta(days=int(_LOOKBACK_YEARS * 365.25) + 10)
    frame = await _price_data_service.get_price_frame(
        db, symbol_clean, start_date=start, end_date=today,
    )

    if frame.empty or "adjusted_close" not in frame.columns:
        # Service handles the "insufficient" branch gracefully — fall through
        # rather than 404 so the frontend can surface a friendly warning card.
        fingerprint = compute_asset_behavior_fingerprint(symbol_clean, prices=None)  # type: ignore[arg-type]
        return AssetBehaviorFingerprintResponse(**fingerprint.to_dict())

    # Prefer adjusted_close (handles splits/dividends) since trending +
    # drawdown calcs care about total return, not split-only price action.
    prices = frame["adjusted_close"].astype(float)
    fingerprint = compute_asset_behavior_fingerprint(symbol_clean, prices=prices)
    return AssetBehaviorFingerprintResponse(**fingerprint.to_dict())
