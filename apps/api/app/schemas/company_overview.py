from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

DISCLAIMER = (
    "This tool provides research candidates, not financial advice. "
    "Market size estimates, competitive position, and financial data may be "
    "incomplete, delayed, or uncertain. Always verify with primary sources."
)


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
    business_map: BusinessMapSection
    market_position: MarketPositionSection
    financial_check: FinancialCheckSection
    disclaimer: str = DISCLAIMER
