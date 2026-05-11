from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.screener import ScreenerFilters, ScreenerFiltersResponse, ScreenerResponse
from app.services.screener_service import ScreenerService

router = APIRouter(prefix="/api/screener", tags=["screener"])
_service = ScreenerService()


@router.get("/filters", response_model=ScreenerFiltersResponse)
def get_screener_filters(db: Session = Depends(get_db)) -> ScreenerFiltersResponse:
    """Return all unique filter options (sectors, industries, countries, exchanges)."""
    return _service.get_filters(db)


@router.get("/results", response_model=ScreenerResponse)
def get_screener_results(
    sector: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    exchange: Optional[str] = Query(default=None),
    market_cap_category: Optional[str] = Query(default=None),
    min_market_cap: Optional[float] = Query(default=None),
    max_market_cap: Optional[float] = Query(default=None),
    min_pe: Optional[float] = Query(default=None),
    max_pe: Optional[float] = Query(default=None),
    min_dividend_yield: Optional[float] = Query(default=None),
    sort_by: str = Query(default="market_cap"),
    sort_order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ScreenerResponse:
    """Screen stocks by fundamental filters. Results come from the seeded symbols table."""
    filters = ScreenerFilters(
        sector=sector, industry=industry, country=country, exchange=exchange,
        market_cap_category=market_cap_category, min_market_cap=min_market_cap,
        max_market_cap=max_market_cap, min_pe=min_pe, max_pe=max_pe,
        min_dividend_yield=min_dividend_yield, sort_by=sort_by,
        sort_order=sort_order, limit=limit, offset=offset,
    )
    return _service.screen(db, filters)
