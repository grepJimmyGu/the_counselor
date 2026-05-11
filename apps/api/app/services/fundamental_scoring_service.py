from __future__ import annotations

from typing import Optional

from app.services.financial_validation_service import FinancialCheckMetrics


def _score_revenue_growth(yoy: Optional[float]) -> int:
    if yoy is None: return 50
    if yoy > 0.20: return 100
    if yoy > 0.10: return 75
    if yoy > 0.0: return 50
    return 20


def _score_gross_margin(gm: Optional[float]) -> int:
    if gm is None: return 50
    if gm > 0.60: return 100
    if gm > 0.40: return 80
    if gm > 0.20: return 60
    if gm > 0.10: return 40
    return 20


def _score_operating_margin(om: Optional[float]) -> int:
    if om is None: return 50
    if om > 0.20: return 100
    if om > 0.10: return 75
    if om > 0.0: return 40
    return 0


def _score_fcf_conversion(conv: Optional[float]) -> int:
    if conv is None: return 50
    if conv > 1.0: return 100
    if conv > 0.75: return 80
    if conv > 0.50: return 50
    return 20


def _score_balance_sheet(net_debt_to_ebitda: Optional[float]) -> int:
    if net_debt_to_ebitda is None: return 60  # unknown, neutral
    if net_debt_to_ebitda < 0: return 100    # net cash
    if net_debt_to_ebitda < 1: return 100
    if net_debt_to_ebitda < 2: return 75
    if net_debt_to_ebitda < 3: return 50
    return 20


def _score_eps_growth(years: int) -> int:
    if years >= 3: return 100
    if years >= 1: return 60
    return 20


# ── Valuation risk (higher = more risk) ─────────────────────────────────────

def _val_risk_pe(pe: Optional[float]) -> float:
    if pe is None: return 30  # unknown, moderate risk assumed
    sector_median = 20.0  # rough global median
    ratio = pe / sector_median
    if ratio > 3: return 100
    if ratio > 2: return 70
    if ratio > 1.5: return 40
    return 0


def _val_risk_ps(ps: Optional[float]) -> float:
    if ps is None: return 20
    if ps > 20: return 100
    if ps > 10: return 70
    if ps > 5: return 40
    return 10


def _val_risk_fcf_yield(yield_: Optional[float]) -> float:
    if yield_ is None: return 40  # unknown
    # yield_ is in decimal (e.g. 0.036 = 3.6%)
    if yield_ < 0.01: return 100
    if yield_ < 0.02: return 70
    if yield_ < 0.04: return 40
    return 0


def _val_risk_peg(peg: Optional[float]) -> float:
    if peg is None: return 20
    if peg > 3: return 100
    if peg > 2: return 70
    if peg > 1: return 30
    return 0


def compute_financial_validation_score(m: FinancialCheckMetrics) -> int:
    # net debt / EBITDA proxy — use debt/equity as rough stand-in
    nd_ebitda = None
    if m.net_debt is not None and m.operating_cf is not None and m.operating_cf > 0:
        nd_ebitda = m.net_debt / m.operating_cf

    score = (
        _score_revenue_growth(m.revenue_yoy) * 0.20
        + _score_gross_margin(m.gross_margin) * 0.15
        + _score_operating_margin(m.operating_margin) * 0.15
        + _score_fcf_conversion(m.fcf_conversion) * 0.20
        + _score_balance_sheet(nd_ebitda) * 0.15
        + _score_eps_growth(m.eps_growth_years) * 0.15
    )
    return max(0, min(100, round(score)))


def compute_valuation_risk_score(m: FinancialCheckMetrics) -> int:
    score = (
        _val_risk_pe(m.pe_ratio) * 0.35
        + _val_risk_ps(m.ps_ratio) * 0.25
        + _val_risk_fcf_yield(m.fcf_yield) * 0.25
        + _val_risk_peg(m.peg_ratio) * 0.15
    )
    return max(0, min(100, round(score)))


def compute_overall_score(financial_score: int, valuation_risk: int) -> int:
    return max(0, min(100, round(financial_score * 0.70 - valuation_risk * 0.30)))


def get_financial_validation_label(score: int) -> str:
    if score >= 80: return "Financials Strongly Support Story"
    if score >= 60: return "Financials Mostly Support Story"
    if score >= 40: return "Mixed Financial Validation"
    if score >= 20: return "Financials Do Not Yet Support Story"
    return "Weak Financial Support"


def get_overall_label(overall: int, financial: int, valuation_risk: int) -> str:
    warnings = []
    if valuation_risk > 70:
        warnings.append("Valuation Risk High")
    label = f"{get_financial_validation_label(financial)} (financial only — business analysis pending)"
    if warnings:
        label += f" · {', '.join(warnings)}"
    return label


def get_warnings(m: FinancialCheckMetrics, valuation_risk: int) -> list[str]:
    warnings = []
    if valuation_risk > 70:
        warnings.append("Valuation Risk High")
    if m.net_debt is not None and m.operating_cf and m.operating_cf > 0:
        nd_ebitda = m.net_debt / m.operating_cf
        if nd_ebitda > 3:
            warnings.append("Balance Sheet Risk High")
    if m.fcf_conversion is not None and m.fcf_conversion < 0.5:
        warnings.append("Cash Flow Quality Weak")
    return warnings
