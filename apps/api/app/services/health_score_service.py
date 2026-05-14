"""
PRD-08c: Financial Health Check — Piotroski F-Score + Altman Z-Score
======================================================================
Deterministic calculation from FMP raw statements.
No LLM involved — purely quantitative.

Piotroski F-Score: 9 binary signals across profitability, leverage, efficiency.
Altman Z-Score: bankruptcy predictor (N/A for financial sector companies).
QSV insights: 50-100 word paragraphs assembled from numbers.
Industry percentile: SQL query against symbol_health_scores table.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.fmp_client import FMPClient, FMPNotConfiguredError, FMPRateLimitError

logger = logging.getLogger(__name__)

# Sectors where Altman Z-Score is not applicable
_FINANCIAL_SECTORS = {"Financials", "Financial Services", "Banking", "Insurance"}

# Piotroski label thresholds
def _piotroski_label(score: Optional[int]) -> str:
    if score is None:
        return "N/A"
    if score >= 8:
        return "Strong"
    if score >= 6:
        return "Good"
    if score >= 4:
        return "Neutral"
    return "Weak"


def _altman_label(z: Optional[float]) -> str:
    if z is None:
        return "N/A"
    if z > 2.99:
        return "Safe"
    if z >= 1.81:
        return "Grey Zone"
    return "Distress"


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    try:
        if a is None or b is None or b == 0:
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def _fmt_pct(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.{digits}f}%"


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1e12:
        return f"{sign}${abs_v / 1e12:.1f}T"
    if abs_v >= 1e9:
        return f"{sign}${abs_v / 1e9:.1f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v / 1e6:.0f}M"
    return f"{sign}${abs_v:.0f}"


def _fmt_x(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}x"


@dataclass
class PiotroskiSignals:
    roa_positive: Optional[bool] = None        # ROA > 0
    cash_quality: Optional[bool] = None        # OCF > Net Income
    roa_improving: Optional[bool] = None       # ΔROA > 0
    cfo_improving: Optional[bool] = None       # Δ(OCF/Assets) > 0
    leverage_falling: Optional[bool] = None   # Δ D/E < 0
    liquidity_improving: Optional[bool] = None # Δ Current Ratio > 0
    no_dilution: Optional[bool] = None        # Shares ≤ prior year
    gross_margin_improving: Optional[bool] = None  # Δ GP% > 0
    asset_turnover_improving: Optional[bool] = None  # Δ (Rev/Assets) > 0

    def score(self) -> int:
        signals = [
            self.roa_positive, self.cash_quality, self.roa_improving,
            self.cfo_improving, self.leverage_falling, self.liquidity_improving,
            self.no_dilution, self.gross_margin_improving, self.asset_turnover_improving,
        ]
        return sum(1 for s in signals if s is True)

    def available(self) -> int:
        """How many signals were computable (not None)."""
        signals = [
            self.roa_positive, self.cash_quality, self.roa_improving,
            self.cfo_improving, self.leverage_falling, self.liquidity_improving,
            self.no_dilution, self.gross_margin_improving, self.asset_turnover_improving,
        ]
        return sum(1 for s in signals if s is not None)

    def to_dict(self) -> dict:
        return {
            "roa_positive": self.roa_positive,
            "cash_quality": self.cash_quality,
            "roa_improving": self.roa_improving,
            "cfo_improving": self.cfo_improving,
            "leverage_falling": self.leverage_falling,
            "liquidity_improving": self.liquidity_improving,
            "no_dilution": self.no_dilution,
            "gross_margin_improving": self.gross_margin_improving,
            "asset_turnover_improving": self.asset_turnover_improving,
        }


@dataclass
class HealthScoreResult:
    symbol: str
    sector: Optional[str] = None

    # Piotroski
    piotroski_score: Optional[int] = None          # 0-9 or None if insufficient data
    piotroski_label: str = "N/A"
    piotroski_signals: PiotroskiSignals = field(default_factory=PiotroskiSignals)

    # Altman Z
    altman_z_score: Optional[float] = None
    altman_z_label: str = "N/A"
    altman_z_na_reason: Optional[str] = None

    # Industry percentile
    sector_piotroski_pct: Optional[float] = None   # 0-100
    sector_piotroski_n: Optional[int] = None

    # QSV insights
    insight_quality: Optional[str] = None
    insight_safety: Optional[str] = None
    insight_value: Optional[str] = None

    # Value metrics carried through
    ev_ebitda: Optional[float] = None
    fcf_yield: Optional[float] = None
    pe_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None


# ── Piotroski computation ──────────────────────────────────────────────────────

def _compute_piotroski(
    income: list[dict],
    cashflow: list[dict],
    balance: list[dict],
) -> tuple[Optional[int], PiotroskiSignals]:
    """
    Compute Piotroski F-Score from annual statements.
    Requires at least 2 years (current + prior) for trend signals.
    Returns (score, signals).  score=None if data insufficient.
    """
    sigs = PiotroskiSignals()

    if not income or not balance:
        return None, sigs

    i_curr = income[0]
    i_prior = income[1] if len(income) > 1 else None
    cf_curr = cashflow[0] if cashflow else None
    cf_prior = cashflow[1] if len(cashflow) > 1 else None
    b_curr = balance[0]
    b_prior = balance[1] if len(balance) > 1 else None

    # Helper extractors
    def _f(d: Optional[dict], *keys: str) -> Optional[float]:
        if d is None:
            return None
        for k in keys:
            v = d.get(k)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return None

    # Raw values
    net_income_curr = _f(i_curr, "netIncome")
    net_income_prior = _f(i_prior, "netIncome")
    revenue_curr = _f(i_curr, "revenue", "totalRevenue")
    revenue_prior = _f(i_prior, "revenue", "totalRevenue")
    gross_profit_curr = _f(i_curr, "grossProfit")
    gross_profit_prior = _f(i_prior, "grossProfit")
    op_income_curr = _f(i_curr, "operatingIncome")

    ocf_curr = _f(cf_curr, "operatingCashFlow")
    ocf_prior = _f(cf_prior, "operatingCashFlow")

    total_assets_curr = _f(b_curr, "totalAssets")
    total_assets_prior = _f(b_prior, "totalAssets")
    total_debt_curr = _f(b_curr, "totalDebt")
    total_debt_prior = _f(b_prior, "totalDebt")
    equity_curr = _f(b_curr, "totalStockholdersEquity")
    equity_prior = _f(b_prior, "totalStockholdersEquity")
    curr_assets = _f(b_curr, "totalCurrentAssets")
    curr_liab = _f(b_curr, "totalCurrentLiabilities")
    curr_assets_prior = _f(b_prior, "totalCurrentAssets")
    curr_liab_prior = _f(b_prior, "totalCurrentLiabilities")

    shares_curr = _f(i_curr, "weightedAverageShsOut", "weightedAverageShsOutDil")
    shares_prior = _f(i_prior, "weightedAverageShsOut", "weightedAverageShsOutDil")

    # ── Signal 1: ROA > 0 ─────────────────────────────────────────────────────
    roa_curr = _safe_div(net_income_curr, total_assets_curr)
    if roa_curr is not None:
        sigs.roa_positive = roa_curr > 0

    # ── Signal 2: OCF > Net Income ────────────────────────────────────────────
    if ocf_curr is not None and net_income_curr is not None:
        sigs.cash_quality = ocf_curr > net_income_curr

    # ── Signal 3: Δ ROA improving ─────────────────────────────────────────────
    roa_prior = _safe_div(net_income_prior, total_assets_prior)
    if roa_curr is not None and roa_prior is not None:
        sigs.roa_improving = roa_curr > roa_prior

    # ── Signal 4: Δ OCF/Assets improving ─────────────────────────────────────
    cfo_to_assets_curr = _safe_div(ocf_curr, total_assets_curr)
    cfo_to_assets_prior = _safe_div(ocf_prior, total_assets_prior)
    if cfo_to_assets_curr is not None and cfo_to_assets_prior is not None:
        sigs.cfo_improving = cfo_to_assets_curr > cfo_to_assets_prior

    # ── Signal 5: Leverage falling (D/E ratio) ────────────────────────────────
    de_curr = _safe_div(total_debt_curr, equity_curr)
    de_prior = _safe_div(total_debt_prior, equity_prior)
    if de_curr is not None and de_prior is not None:
        sigs.leverage_falling = de_curr < de_prior

    # ── Signal 6: Liquidity improving (current ratio) ────────────────────────
    cr_curr = _safe_div(curr_assets, curr_liab)
    cr_prior = _safe_div(curr_assets_prior, curr_liab_prior)
    if cr_curr is not None and cr_prior is not None:
        sigs.liquidity_improving = cr_curr > cr_prior

    # ── Signal 7: No dilution (shares ≤ prior) ────────────────────────────────
    if shares_curr is not None and shares_prior is not None:
        sigs.no_dilution = shares_curr <= shares_prior

    # ── Signal 8: Gross margin improving ─────────────────────────────────────
    gm_curr = _safe_div(gross_profit_curr, revenue_curr)
    gm_prior = _safe_div(gross_profit_prior, revenue_prior)
    if gm_curr is not None and gm_prior is not None:
        sigs.gross_margin_improving = gm_curr > gm_prior

    # ── Signal 9: Asset turnover improving (Rev/Assets) ───────────────────────
    at_curr = _safe_div(revenue_curr, total_assets_curr)
    at_prior = _safe_div(revenue_prior, total_assets_prior)
    if at_curr is not None and at_prior is not None:
        sigs.asset_turnover_improving = at_curr > at_prior

    # Only return a score if we have at least 5 computable signals
    if sigs.available() < 5:
        return None, sigs

    return sigs.score(), sigs


# ── Altman Z-Score computation ────────────────────────────────────────────────

def _compute_altman_z(
    income: list[dict],
    balance: list[dict],
    market_cap: Optional[float],
    sector: Optional[str],
) -> tuple[Optional[float], str, Optional[str]]:
    """
    Returns (z_score, label, na_reason).
    z_score=None and na_reason set for financial sector companies.
    """
    # N/A for financial sector
    if sector and any(fs.lower() in sector.lower() for fs in _FINANCIAL_SECTORS):
        return None, "N/A", "Altman Z-Score is not applicable to financial sector companies"

    if not income or not balance:
        return None, "N/A", None

    i = income[0]
    b = balance[0]

    def _f(d: dict, *keys: str) -> Optional[float]:
        for k in keys:
            v = d.get(k)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return None

    total_assets = _f(b, "totalAssets")
    total_liabilities = _f(b, "totalLiabilities")
    retained_earnings = _f(b, "retainedEarnings")
    curr_assets = _f(b, "totalCurrentAssets")
    curr_liab = _f(b, "totalCurrentLiabilities")
    operating_income = _f(i, "operatingIncome")
    revenue = _f(i, "revenue", "totalRevenue")

    if not total_assets or total_assets == 0:
        return None, "N/A", None

    working_capital = (curr_assets - curr_liab) if (curr_assets is not None and curr_liab is not None) else None

    x1 = _safe_div(working_capital, total_assets)
    x2 = _safe_div(retained_earnings, total_assets)
    x3 = _safe_div(operating_income, total_assets)
    x4 = _safe_div(market_cap, total_liabilities) if total_liabilities else None
    x5 = _safe_div(revenue, total_assets)

    # Need at least x1, x3, x5 to compute a meaningful Z-Score
    if x1 is None or x3 is None or x5 is None:
        return None, "N/A", None

    z = (
        1.2 * (x1 or 0)
        + 1.4 * (x2 or 0)
        + 3.3 * (x3 or 0)
        + 0.6 * (x4 or 0)
        + 1.0 * (x5 or 0)
    )
    return round(z, 2), _altman_label(z), None


# ── QSV insight synthesis (deterministic) ─────────────────────────────────────

def _synthesize_quality_insight(
    company: str,
    piotroski_score: Optional[int],
    piotroski_label: str,
    income: list[dict],
    cashflow: list[dict],
) -> str:
    """50-100 word Quality insight paragraph."""
    parts = []
    parts.append(
        f"{company} has a Piotroski F-Score of {piotroski_score}/9 ({piotroski_label})."
        if piotroski_score is not None
        else f"{company}'s Piotroski F-Score could not be fully computed due to limited data."
    )

    # Revenue direction
    if len(income) >= 4:
        rev_curr = (income[0].get("revenue") or income[0].get("totalRevenue") or 0)
        rev_3yr = (income[3].get("revenue") or income[3].get("totalRevenue") or 0)
        if rev_curr and rev_3yr and rev_3yr > 0:
            cagr = (rev_curr / rev_3yr) ** (1 / 3) - 1
            direction = "growing" if cagr > 0.02 else ("declining" if cagr < -0.02 else "stable")
            parts.append(f"Revenue has been {direction} at {abs(cagr) * 100:.1f}% CAGR over 3 years.")
    elif len(income) >= 2:
        rev_curr = income[0].get("revenue") or income[0].get("totalRevenue")
        rev_prior = income[1].get("revenue") or income[1].get("totalRevenue")
        if rev_curr and rev_prior and rev_prior > 0:
            yoy = (rev_curr - rev_prior) / abs(rev_prior)
            direction = "growing" if yoy > 0.02 else ("declining" if yoy < -0.02 else "stable")
            parts.append(f"Revenue is {direction} ({yoy:+.1%} YoY).")

    # Gross margin trend
    if len(income) >= 2:
        gp0 = income[0].get("grossProfit")
        rev0 = income[0].get("revenue") or income[0].get("totalRevenue")
        gp1 = income[1].get("grossProfit")
        rev1 = income[1].get("revenue") or income[1].get("totalRevenue")
        gm0 = _safe_div(gp0, rev0)
        gm1 = _safe_div(gp1, rev1)
        if gm0 is not None and gm1 is not None:
            change = "expanded" if gm0 > gm1 + 0.005 else ("contracted" if gm0 < gm1 - 0.005 else "stable")
            parts.append(f"Gross margin {change} from {gm1 * 100:.1f}% to {gm0 * 100:.1f}%.")

    # Cash quality
    if income and cashflow:
        ocf = cashflow[0].get("operatingCashFlow")
        ni = income[0].get("netIncome")
        if ocf is not None and ni is not None:
            quality = "exceeds" if ocf > ni else "trails"
            quality_label = "high earnings quality" if ocf > ni else "potential accounting risk"
            parts.append(f"Operating cash flow {quality} net income, indicating {quality_label}.")

    return " ".join(parts)


def _synthesize_safety_insight(
    company: str,
    altman_z: Optional[float],
    altman_label: str,
    altman_na_reason: Optional[str],
    net_debt: Optional[float],
    interest_coverage: Optional[float],
    income: list[dict],
) -> str:
    """50-100 word Safety insight paragraph."""
    parts = []

    if altman_na_reason:
        parts.append(f"{company}'s balance sheet strength is assessed on a standalone basis ({altman_na_reason}).")
    elif altman_z is not None:
        parts.append(
            f"Altman Z-Score of {altman_z:.2f} places {company} in the {altman_label}."
        )

    # Net cash/debt
    if net_debt is not None:
        if net_debt < 0:
            parts.append(f"Net cash position of {_fmt_money(abs(net_debt))} — conservatively capitalized.")
        elif net_debt == 0:
            parts.append("The company carries no net debt.")
        else:
            parts.append(f"Net debt of {_fmt_money(net_debt)}.")

    # Interest coverage
    if interest_coverage is not None:
        cov_label = "strong" if interest_coverage > 5 else ("adequate" if interest_coverage > 2 else "tight")
        parts.append(f"Interest coverage of {interest_coverage:.1f}x — {cov_label}.")

    # Share dilution trend
    if len(income) >= 3:
        shares = [
            s.get("weightedAverageShsOut") or s.get("weightedAverageShsOutDil")
            for s in income[:3]
        ]
        if all(s is not None for s in shares):
            if shares[0] < shares[2] * 0.97:
                parts.append("Share count has been shrinking — buybacks returning capital.")
            elif shares[0] > shares[2] * 1.03:
                parts.append("Share count has grown — existing shareholders diluted.")
            else:
                parts.append("Share count has been broadly stable over the past 3 years.")

    if not parts:
        parts.append(f"Insufficient data to assess {company}'s financial safety profile fully.")

    return " ".join(parts)


def _synthesize_value_insight(
    company: str,
    pe_ratio: Optional[float],
    peg_ratio: Optional[float],
    fcf_yield: Optional[float],
    ev_ebitda: Optional[float],
    sector: Optional[str],
    sector_pct: Optional[float],
) -> str:
    """50-100 word Value insight paragraph."""
    parts = []

    if ev_ebitda is not None:
        sector_ctx = f" in the {sector} sector" if sector else ""
        if sector_pct is not None:
            pct_label = "top" if sector_pct > 50 else "bottom"
            expensive = sector_pct > 50
            parts.append(
                f"EV/EBITDA of {ev_ebitda:.1f}x places {company} among the "
                f"{pct_label} {int(sector_pct) if expensive else int(100 - sector_pct)}% "
                f"most {'expensive' if expensive else 'attractively valued'} companies{sector_ctx}."
            )
        else:
            parts.append(f"EV/EBITDA of {ev_ebitda:.1f}x.")

    if fcf_yield is not None:
        yield_label = "attractive" if fcf_yield > 0.05 else ("modest" if fcf_yield > 0.02 else "low")
        parts.append(f"FCF yield of {fcf_yield * 100:.1f}% — {yield_label}.")

    if pe_ratio is not None:
        if peg_ratio is not None:
            peg_label = "growth appears priced in" if peg_ratio > 2 else ("fair value" if peg_ratio > 1 else "discounted relative to growth")
            parts.append(f"P/E of {pe_ratio:.1f}x with PEG ratio {peg_ratio:.1f} — {peg_label}.")
        else:
            parts.append(f"P/E ratio of {pe_ratio:.1f}x.")

    if not parts:
        parts.append(f"Valuation data for {company} is limited — verify via primary sources.")

    return " ".join(parts)


# ── DB persistence ─────────────────────────────────────────────────────────────

def _save_health_score(result: HealthScoreResult, db: Session) -> None:
    """Upsert computed scores into symbol_health_scores."""
    is_sqlite = db.bind.dialect.name == "sqlite" if db.bind else False
    signals_json = json.dumps(result.piotroski_signals.to_dict())
    try:
        if is_sqlite:
            db.execute(
                text("""
                    INSERT OR REPLACE INTO symbol_health_scores
                    (symbol, sector, piotroski_score, piotroski_signals,
                     altman_z_score, altman_z_label,
                     sector_piotroski_pct, sector_piotroski_n,
                     insight_quality, insight_safety, insight_value,
                     ev_ebitda, fcf_yield, computed_at)
                    VALUES (:sym, :sector, :p_score, :p_sigs,
                            :az, :az_label,
                            :pct, :n,
                            :iq, :is_, :iv,
                            :ev, :fcf, :now)
                """),
                {
                    "sym": result.symbol, "sector": result.sector,
                    "p_score": result.piotroski_score, "p_sigs": signals_json,
                    "az": result.altman_z_score, "az_label": result.altman_z_label,
                    "pct": result.sector_piotroski_pct, "n": result.sector_piotroski_n,
                    "iq": result.insight_quality, "is_": result.insight_safety, "iv": result.insight_value,
                    "ev": result.ev_ebitda, "fcf": result.fcf_yield,
                    "now": datetime.utcnow(),
                },
            )
        else:
            db.execute(
                text("""
                    INSERT INTO symbol_health_scores
                    (symbol, sector, piotroski_score, piotroski_signals,
                     altman_z_score, altman_z_label,
                     sector_piotroski_pct, sector_piotroski_n,
                     insight_quality, insight_safety, insight_value,
                     ev_ebitda, fcf_yield, computed_at)
                    VALUES (:sym, :sector, :p_score, :p_sigs::jsonb,
                            :az, :az_label,
                            :pct, :n,
                            :iq, :is_, :iv,
                            :ev, :fcf, now())
                    ON CONFLICT (symbol) DO UPDATE SET
                        sector=:sector,
                        piotroski_score=:p_score,
                        piotroski_signals=:p_sigs::jsonb,
                        altman_z_score=:az,
                        altman_z_label=:az_label,
                        sector_piotroski_pct=:pct,
                        sector_piotroski_n=:n,
                        insight_quality=:iq,
                        insight_safety=:is_,
                        insight_value=:iv,
                        ev_ebitda=:ev,
                        fcf_yield=:fcf,
                        computed_at=now()
                """),
                {
                    "sym": result.symbol, "sector": result.sector,
                    "p_score": result.piotroski_score, "p_sigs": signals_json,
                    "az": result.altman_z_score, "az_label": result.altman_z_label,
                    "pct": result.sector_piotroski_pct, "n": result.sector_piotroski_n,
                    "iq": result.insight_quality, "is_": result.insight_safety, "iv": result.insight_value,
                    "ev": result.ev_ebitda, "fcf": result.fcf_yield,
                },
            )
        db.commit()
    except Exception as exc:
        logger.warning("Failed to save health score for %s: %s", result.symbol, exc)
        db.rollback()


def _get_industry_percentile(
    symbol: str,
    sector: Optional[str],
    piotroski_score: Optional[int],
    db: Session,
) -> tuple[Optional[float], Optional[int]]:
    """
    Return (percentile 0-100, peer_count).
    Percentile = fraction of same-sector peers with LOWER score × 100.
    """
    if sector is None or piotroski_score is None:
        return None, None
    try:
        row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE piotroski_score < :target) * 100.0 / NULLIF(COUNT(*), 0) AS pct,
                    COUNT(*) AS peer_count
                FROM symbol_health_scores
                WHERE sector = :sector AND piotroski_score IS NOT NULL AND symbol != :sym
            """),
            {"target": piotroski_score, "sector": sector, "sym": symbol},
        ).fetchone()
        if row and row[1] and row[1] > 0:
            return round(float(row[0]), 1), int(row[1])
    except Exception as exc:
        logger.debug("Percentile query failed: %s", exc)
    return None, None


# ── Main service ───────────────────────────────────────────────────────────────

class HealthScoreService:
    """
    Computes Piotroski F-Score + Altman Z-Score + QSV insights for a given symbol.
    Results are cached in symbol_health_scores table (24h TTL recompute on page load).
    """

    def __init__(self) -> None:
        self._fmp = FMPClient()

    async def compute(
        self,
        symbol: str,
        company_name: str,
        sector: Optional[str],
        market_cap: Optional[float],
        db: Session,
        # Optionally accept pre-fetched statements to avoid duplicate FMP calls
        income: Optional[list[dict]] = None,
        cashflow: Optional[list[dict]] = None,
        balance: Optional[list[dict]] = None,
        key_metrics: Optional[dict] = None,
        # Financial check metrics for insight synthesis
        net_debt: Optional[float] = None,
        interest_coverage: Optional[float] = None,
    ) -> HealthScoreResult:
        sym = symbol.upper()
        result = HealthScoreResult(symbol=sym, sector=sector)

        try:
            # Fetch raw statements if not provided (limit=2 years for Piotroski, balance=2 for Altman)
            if income is None:
                income = await self._fmp.get_income_statement(sym, limit=4)
            if cashflow is None:
                cashflow = await self._fmp.get_cash_flow(sym, limit=2)
            if balance is None:
                balance = await self._fmp.get_balance_sheet(sym, limit=2)
        except (FMPNotConfiguredError, FMPRateLimitError, Exception) as exc:
            logger.warning("Health score: FMP fetch failed for %s: %s", sym, exc)
            return result

        # ── Piotroski F-Score ──────────────────────────────────────────────────
        p_score, p_signals = _compute_piotroski(income, cashflow, balance)
        result.piotroski_score = p_score
        result.piotroski_label = _piotroski_label(p_score)
        result.piotroski_signals = p_signals

        # ── Altman Z-Score ─────────────────────────────────────────────────────
        z_score, z_label, z_na = _compute_altman_z(income, balance, market_cap, sector)
        result.altman_z_score = z_score
        result.altman_z_label = z_label
        result.altman_z_na_reason = z_na

        # ── Valuation metrics from key_metrics ────────────────────────────────
        if key_metrics:
            def _kf(k: str) -> Optional[float]:
                v = key_metrics.get(k)
                try:
                    return float(v) if v is not None else None
                except (ValueError, TypeError):
                    return None
            result.ev_ebitda = _kf("enterpriseValueOverEBITDATTM") or _kf("evToEBITDATTM")
            result.fcf_yield = _kf("freeCashFlowYieldTTM")
            result.pe_ratio = _kf("peRatioTTM")
            if result.pe_ratio:
                # PEG: need EPS growth rate — approximate from income statements
                if len(income) >= 2:
                    eps0 = income[0].get("eps") or income[0].get("epsDiluted")
                    eps1 = income[1].get("eps") or income[1].get("epsDiluted")
                    if eps0 and eps1 and eps1 > 0 and eps0 > eps1:
                        eps_growth = (eps0 - eps1) / abs(eps1) * 100  # in %
                        if eps_growth > 0:
                            result.peg_ratio = round(result.pe_ratio / eps_growth, 2)

        # ── Industry percentile ────────────────────────────────────────────────
        # Save current result first so it's included in peer pool
        _save_health_score(result, db)

        pct, peer_n = _get_industry_percentile(sym, sector, p_score, db)
        result.sector_piotroski_pct = pct
        result.sector_piotroski_n = peer_n

        # ── QSV Insight synthesis ──────────────────────────────────────────────
        result.insight_quality = _synthesize_quality_insight(
            company_name, p_score, result.piotroski_label, income, cashflow
        )
        result.insight_safety = _synthesize_safety_insight(
            company_name, z_score, z_label, z_na, net_debt, interest_coverage, income
        )
        result.insight_value = _synthesize_value_insight(
            company_name, result.pe_ratio, result.peg_ratio,
            result.fcf_yield, result.ev_ebitda, sector, pct
        )

        # Update DB with full insights + percentile
        _save_health_score(result, db)

        return result
