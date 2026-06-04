from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

DISCLAIMER = (
    "This tool provides research candidates, not financial advice. "
    "Market size estimates, competitive position, and financial data may be "
    "incomplete, delayed, or uncertain. Always verify with primary sources."
)


class TrendSection(BaseModel):
    """Price trend metrics computed from price_bars (Alpha Vantage)."""
    latest_price: Optional[float] = None
    latest_date: Optional[str] = None
    perf_1m: Optional[float] = None
    perf_3m: Optional[float] = None
    perf_6m: Optional[float] = None
    perf_12m: Optional[float] = None
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    price_vs_ma50: Optional[float] = None
    price_vs_ma200: Optional[float] = None
    vol_trend: Optional[str] = None
    avg_vol_20d: Optional[float] = None
    avg_vol_65d: Optional[float] = None
    rs_vs_spy_3m: Optional[float] = None
    rs_vs_spy_12m: Optional[float] = None
    price_series_90d: list[dict] = []
    bar_count: int = 0
    data_source: str = "alpha_vantage"


class SegmentYearSchema(BaseModel):
    year: int
    segments: dict[str, float] = {}


class RevenueSegmentSection(BaseModel):
    """PRD-08d: Revenue segment + geographic breakdown charts."""
    product_years: list[SegmentYearSchema] = []
    geo_years: list[SegmentYearSchema] = []
    segment_names: list[str] = []
    geo_names: list[str] = []
    segment_colors: list[str] = []
    geo_colors: list[str] = []
    fallback_note: Optional[str] = None


class SupplyChainEntry(BaseModel):
    name: str
    symbol: Optional[str] = None


class CompetitorRankingEntry(BaseModel):
    symbol: str
    name: str
    revenue: str
    revenue_raw: float
    share: float
    position: str
    trend_5yr: list[float] = []


class CompetitorSegmentSection(BaseModel):
    segment: str
    rankings: list[CompetitorRankingEntry] = []
    disclaimer: str = ""


class BusinessMapSection(BaseModel):
    one_line_summary: Optional[str] = None
    primary_value_chain_role: Optional[str] = None
    secondary_value_chain_roles: list[str] = []
    customer_types: list[str] = []
    revenue_model: Optional[str] = None
    margin_implication: Optional[str] = None
    cyclicality_implication: Optional[str] = None
    pricing_power_implication: Optional[str] = None
    visualization_type: str = "value_chain_map"
    confidence: str = "partial"
    source_notes: list[str] = []


class MarketPositionSection(BaseModel):
    market_category: Optional[str] = None
    market_size_estimate: str = "estimate unavailable"
    market_growth_label: Optional[str] = None
    competitive_position_label: Optional[str] = None
    market_share_notes: Optional[str] = None
    key_competitors: list[str] = []
    key_growth_drivers: list[str] = []
    key_risks: list[str] = []
    upstream_suppliers: list[SupplyChainEntry] = []
    downstream_customers: list[SupplyChainEntry] = []
    competitor_segments: list[CompetitorSegmentSection] = []
    visualization_type: str = "market_position_card"
    confidence: str = "partial"
    source_notes: list[str] = []


class FinancialCheckSection(BaseModel):
    financial_validation_label: str = "Mixed Financial Validation"
    financial_validation_score: int = 50
    valuation_risk_score: int = 50
    overall_score: int = 50
    growth_summary: Optional[str] = None
    profitability_summary: Optional[str] = None
    cash_flow_summary: Optional[str] = None
    balance_sheet_summary: Optional[str] = None
    valuation_summary: Optional[str] = None
    # Growth
    revenue_yoy: Optional[float] = None
    revenue_3y_cagr: Optional[float] = None
    eps_yoy: Optional[float] = None
    # Profitability
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    # Cash flow
    free_cash_flow: Optional[float] = None
    fcf_margin: Optional[float] = None
    fcf_conversion: Optional[float] = None
    # Balance sheet
    cash: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    # Valuation — sourced from FMP /key-metrics-ttm
    pe_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    fcf_yield: Optional[float] = None
    ev_ebitda: Optional[float] = None   # added: used by Evaluation Dashboard valuation scorecard
    dividend_yield: Optional[float] = None
    # Chart series
    revenue_series: list[dict] = []
    margin_series: list[dict] = []
    fcf_series: list[dict] = []
    warnings: list[str] = []
    visualization_type: str = "financial_validation_cards"
    confidence: str = "high"
    source_notes: list[str] = []


class CompanyOverviewResponse(BaseModel):
    symbol: str
    name: str
    price: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None
    as_of_date: Optional[date] = None
    revenue_segments: RevenueSegmentSection = RevenueSegmentSection()
    business_map: BusinessMapSection
    market_position: MarketPositionSection
    financial_check: FinancialCheckSection
    disclaimer: str = DISCLAIMER
    # CN market — AKShare news (empty for US stocks)
    cn_news: list[dict] = []
