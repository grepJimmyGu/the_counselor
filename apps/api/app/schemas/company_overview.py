from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel

DISCLAIMER = (
    "This tool provides research candidates, not financial advice. "
    "Market size estimates, competitive position, and financial data may be "
    "incomplete, delayed, or uncertain. Always verify with primary sources."
)


class TrendSection(BaseModel):
    """PRD-trend: Price trend metrics computed from price_bars (Alpha Vantage)."""
    latest_price: Optional[float] = None
    latest_date: Optional[str] = None       # ISO date string

    # Performance (decimal, e.g. 0.12 = +12%)
    perf_1m: Optional[float] = None
    perf_3m: Optional[float] = None
    perf_6m: Optional[float] = None
    perf_12m: Optional[float] = None

    # Moving averages
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    price_vs_ma50: Optional[float] = None    # e.g. 0.08 = 8% above MA50
    price_vs_ma200: Optional[float] = None

    # Volume
    vol_trend: Optional[str] = None          # "increasing" | "stable" | "decreasing"
    avg_vol_20d: Optional[float] = None
    avg_vol_65d: Optional[float] = None

    # Relative strength vs SPY
    rs_vs_spy_3m: Optional[float] = None
    rs_vs_spy_12m: Optional[float] = None

    # 90-day sparkline [{date, price}]
    price_series_90d: list[dict] = []

    bar_count: int = 0
    data_source: str = "alpha_vantage"


class SegmentYearSchema(BaseModel):
    year: int
    segments: dict[str, float] = {}


class RevenueSegmentSection(BaseModel):
    """PRD-08d: Revenue segment + geographic breakdown charts."""
    product_years: list[SegmentYearSchema] = []    # newest first, up to 5
    geo_years: list[SegmentYearSchema] = []
    segment_names: list[str] = []                  # ordered by latest revenue
    geo_names: list[str] = []
    segment_colors: list[str] = []
    geo_colors: list[str] = []
    fallback_note: Optional[str] = None


class HealthScoreSection(BaseModel):
    """PRD-08c: Piotroski F-Score + Altman Z-Score + QSV insights."""
    # Piotroski
    piotroski_score: Optional[int] = None          # 0-9 or None
    piotroski_label: str = "N/A"                   # Weak / Neutral / Good / Strong / N/A
    piotroski_signals: dict[str, Optional[bool]] = {}  # signal name → pass/fail/None

    # Altman Z
    altman_z_score: Optional[float] = None
    altman_z_label: str = "N/A"                    # Safe / Grey Zone / Distress / N/A
    altman_z_na_reason: Optional[str] = None

    # Industry percentile
    sector_piotroski_pct: Optional[float] = None   # 0-100 (percentile ABOVE which this stock sits)
    sector_piotroski_n: Optional[int] = None       # peer count

    # QSV insights (deterministic, no LLM)
    insight_quality: Optional[str] = None
    insight_safety: Optional[str] = None
    insight_value: Optional[str] = None

    # Valuation carry-through for V insight
    ev_ebitda: Optional[float] = None
    fcf_yield: Optional[float] = None
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None


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


class SupplyChainEntry(BaseModel):
    name: str
    symbol: Optional[str] = None   # None if not a publicly-traded company


class CompetitorRankingEntry(BaseModel):
    symbol: str
    name: str
    revenue: str          # formatted, e.g. "$209B"
    revenue_raw: float
    share: float          # 0.0 - 1.0
    position: str         # Dominant / Market Leader / Major Participant / Niche
    trend_5yr: list[float] = []


class CompetitorSegmentSection(BaseModel):
    segment: str
    rankings: list[CompetitorRankingEntry] = []
    disclaimer: str = ""


class MarketPositionSection(BaseModel):
    market_category: Optional[str] = None
    market_size_estimate: str = "estimate unavailable"
    market_growth_label: Optional[str] = None
    competitive_position_label: Optional[str] = None
    market_share_notes: Optional[str] = None
    key_competitors: list[str] = []
    key_growth_drivers: list[str] = []
    key_risks: list[str] = []
    # PRD-08e: supply chain
    upstream_suppliers: list[SupplyChainEntry] = []
    downstream_customers: list[SupplyChainEntry] = []
    # PRD-08e: per-segment competitor rankings
    competitor_segments: list[CompetitorSegmentSection] = []
    visualization_type: str = "market_position_card"
    confidence: str = "partial"
    source_notes: list[str] = []


class FinancialCheckSection(BaseModel):
    financial_validation_label: str = "Mixed Financial Validation"
    financial_validation_score: int = 50
    valuation_risk_score: int = 50
    overall_score: int = 50
    # Summaries
    growth_summary: Optional[str] = None
    profitability_summary: Optional[str] = None
    cash_flow_summary: Optional[str] = None
    balance_sheet_summary: Optional[str] = None
    valuation_summary: Optional[str] = None
    # Raw metrics
    revenue_yoy: Optional[float] = None
    revenue_3y_cagr: Optional[float] = None
    eps_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    free_cash_flow: Optional[float] = None
    fcf_margin: Optional[float] = None
    fcf_conversion: Optional[float] = None
    cash: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    pe_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    fcf_yield: Optional[float] = None
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
    health_score: HealthScoreSection = HealthScoreSection()
    revenue_segments: RevenueSegmentSection = RevenueSegmentSection()
    business_map: BusinessMapSection
    market_position: MarketPositionSection
    financial_check: FinancialCheckSection
    disclaimer: str = DISCLAIMER
