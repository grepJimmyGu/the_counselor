from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ScreenerFilters(BaseModel):
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    exchange: Optional[str] = None
    market_cap_category: Optional[str] = None  # micro/small/mid/large/mega
    min_market_cap: Optional[float] = None      # in USD
    max_market_cap: Optional[float] = None
    min_pe: Optional[float] = None
    max_pe: Optional[float] = None
    min_dividend_yield: Optional[float] = None  # as decimal (0.02 = 2%)
    sort_by: str = "market_cap"
    sort_order: str = "desc"                    # asc | desc
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ScreenerResult(BaseModel):
    symbol: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None
    market_cap: Optional[float] = None
    market_cap_category: Optional[str] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None


class ScreenerResponse(BaseModel):
    results: list[ScreenerResult]
    total: int
    offset: int
    limit: int
    filters_applied: dict


class ScreenerFiltersResponse(BaseModel):
    sectors: list[str]
    industries: list[str]
    countries: list[str]
    exchanges: list[str]
    market_cap_categories: list[str]
    total_symbols: int
