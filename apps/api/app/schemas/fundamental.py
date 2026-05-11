from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class CompanyProfile(BaseModel):
    symbol: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    ceo: Optional[str] = None
    employees: Optional[int] = None
    website: Optional[str] = None
    # Market data
    price: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    # Flags
    is_etf: bool = False
    is_actively_trading: bool = True
    # Peers (from FMP /stock_peers)
    peers: list[str] = []
    # Data provenance
    data_source: str = "fmp"
    as_of_date: Optional[date] = None


class KeyMetrics(BaseModel):
    symbol: str
    as_of_date: Optional[date] = None
    # Valuation
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    peg_ratio: Optional[float] = None
    free_cash_flow_yield: Optional[float] = None
    dividend_yield: Optional[float] = None
    # Profitability
    roe: Optional[float] = None
    roa: Optional[float] = None
    # Cash flow
    free_cash_flow_per_share: Optional[float] = None
    operating_cash_flow_per_share: Optional[float] = None
    # Balance sheet
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    net_debt_to_ebitda: Optional[float] = None
    # Per share
    revenue_per_share: Optional[float] = None
    earnings_per_share: Optional[float] = None
    book_value_per_share: Optional[float] = None
    # Data provenance
    data_source: str = "fmp"


class FundamentalSummary(BaseModel):
    """Combined profile + key metrics for the /api/fundamental/overview endpoint."""
    profile: CompanyProfile
    metrics: KeyMetrics
    disclaimer: str = (
        "Financial data is sourced from Financial Modeling Prep and may be delayed "
        "or incomplete. This is for research purposes only, not financial advice."
    )
