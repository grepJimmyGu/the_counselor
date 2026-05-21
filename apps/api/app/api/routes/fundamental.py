from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps_entitlement import require_entitlement
from app.db.session import get_db
from app.schemas.fundamental import CompanyProfile, FundamentalSummary, KeyMetrics
from app.services.fundamental_service import FundamentalService

router = APIRouter(prefix="/api/fundamental", tags=["fundamental"])
_service = FundamentalService()

# Stage 3: gated to S&P 500 for Scout + anonymous; Strategist+ unrestricted.
_market_pulse_gate = require_entitlement(
    market_pulse_ticker_field="symbol",
    allow_anonymous=True,
)


@router.get("/profile/{symbol}", response_model=CompanyProfile)
async def get_profile(
    symbol: str,
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> CompanyProfile:
    """Company profile: name, sector, industry, description, market cap, P/E, peers.

    Gated: Scout + anonymous → S&P 500 only.
    """
    try:
        return await _service.get_profile(db, symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/metrics/{symbol}", response_model=KeyMetrics)
async def get_key_metrics(
    symbol: str,
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> KeyMetrics:
    """Key financial metrics: P/E, P/B, ROE, FCF yield, debt/equity, current ratio, etc.

    Gated: Scout + anonymous → S&P 500 only.
    """
    try:
        return await _service.get_key_metrics(db, symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/overview/{symbol}", response_model=FundamentalSummary)
async def get_overview(
    symbol: str,
    _gate=Depends(_market_pulse_gate),
    db: Session = Depends(get_db),
) -> FundamentalSummary:
    """Full fundamental summary: profile + key metrics combined.

    Gated: Scout + anonymous → S&P 500 only.
    """
    try:
        return await _service.get_summary(db, symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
