from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.schemas.company_overview import (
    BusinessMapSection,
    CompanyOverviewResponse,
    FinancialCheckSection,
    HealthScoreSection,
    MarketPositionSection,
)
from app.services.financial_validation_service import FinancialValidationService
from app.services.fmp_client import FMPClient, FMPNotConfiguredError, FMPRateLimitError
from app.services.fundamental_scoring_service import (
    compute_financial_validation_score,
    compute_valuation_risk_score,
    compute_overall_score,
    get_financial_validation_label,
    get_overall_label,
    get_warnings,
)
from app.services.fundamental_service import FundamentalService
from app.services.business_intelligence_service import BusinessIntelligenceService
from app.services.health_score_service import HealthScoreService
from app.services.value_chain_classifier import (
    derive_margin_implication,
    get_cyclicality_implication,
    get_value_chain_role,
)


def _pct(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    return f"{v * 100:.1f}%"


def _build_growth_summary(fc) -> Optional[str]:
    parts = []
    if fc.revenue_yoy is not None:
        parts.append(f"Revenue grew {_pct(fc.revenue_yoy)} YoY")
    if fc.eps_yoy is not None:
        direction = "grew" if fc.eps_yoy > 0 else "declined"
        parts.append(f"EPS {direction} {_pct(abs(fc.eps_yoy))} YoY")
    if fc.eps_growth_years and fc.eps_growth_years >= 2:
        parts.append(f"{fc.eps_growth_years} consecutive years of EPS growth")
    return ". ".join(parts) + "." if parts else None


def _build_profitability_summary(fc) -> Optional[str]:
    parts = []
    if fc.gross_margin is not None:
        parts.append(f"Gross margin {_pct(fc.gross_margin)}")
    if fc.operating_margin is not None:
        parts.append(f"operating margin {_pct(fc.operating_margin)}")
    if fc.net_margin is not None:
        parts.append(f"net margin {_pct(fc.net_margin)}")
    if fc.roe is not None:
        parts.append(f"ROE {fc.roe:.0%}")
    return ". ".join(parts) + "." if parts else None


def _build_cashflow_summary(fc) -> Optional[str]:
    if fc.free_cash_flow is None:
        return None
    parts = [f"Free cash flow ${fc.free_cash_flow / 1e9:.1f}B" if fc.free_cash_flow >= 1e9 else f"FCF ${fc.free_cash_flow / 1e6:.0f}M"]
    if fc.fcf_conversion is not None:
        parts.append(f"{fc.fcf_conversion:.0%} FCF conversion")
    if fc.fcf_margin is not None:
        parts.append(f"FCF margin {_pct(fc.fcf_margin)}")
    return ". ".join(parts) + "." if parts else None


def _build_balance_sheet_summary(fc) -> Optional[str]:
    if fc.net_debt is None:
        return None
    if fc.net_debt < 0:
        return f"Net cash position of ${abs(fc.net_debt) / 1e9:.1f}B — strong balance sheet."
    return f"Net debt ${fc.net_debt / 1e9:.1f}B. D/E ratio {fc.debt_to_equity:.1f}x." if fc.debt_to_equity else f"Net debt ${fc.net_debt / 1e9:.1f}B."


def _build_valuation_summary(fc, risk_score: int) -> Optional[str]:
    parts = []
    if fc.pe_ratio:
        parts.append(f"P/E {fc.pe_ratio:.1f}x")
    if fc.ps_ratio:
        parts.append(f"P/S {fc.ps_ratio:.1f}x")
    if fc.fcf_yield:
        parts.append(f"FCF yield {_pct(fc.fcf_yield)}")
    if not parts:
        return None
    risk_label = "Elevated" if risk_score > 70 else "Moderate" if risk_score > 40 else "Reasonable"
    return f"{'. '.join(parts)}. Valuation risk: {risk_label}."


class CompanyOverviewService:
    def __init__(self) -> None:
        self._fundamental = FundamentalService()
        self._financial_svc = FinancialValidationService()
        self._fmp = FMPClient()
        self._bi = BusinessIntelligenceService()
        self._health = HealthScoreService()

    async def get_overview(self, db: Session, symbol: str) -> CompanyOverviewResponse:
        sym = symbol.upper()

        # 1. Profile (cached in FundamentalService)
        profile = await self._fundamental.get_profile(db, sym)

        # 2. Key metrics raw dict (for financial validation service)
        key_metrics_raw: dict = {}
        try:
            key_metrics_raw = await self._fmp.get_key_metrics(sym)
        except (FMPNotConfiguredError, FMPRateLimitError, Exception):
            pass

        # 3. Financial Check metrics
        fc = await self._financial_svc.compute(sym, key_metrics_raw)

        # 4. Scoring
        fin_score = compute_financial_validation_score(fc)
        val_risk = compute_valuation_risk_score(fc)
        overall = compute_overall_score(fin_score, val_risk)
        warnings = get_warnings(fc, val_risk)

        # 5. PRD-08c: Health scores (Piotroski + Altman Z + QSV insights)
        health_score_result = None
        try:
            health_score_result = await self._health.compute(
                symbol=sym,
                company_name=profile.name,
                sector=profile.sector,
                market_cap=profile.market_cap,
                db=db,
                key_metrics=key_metrics_raw,
                net_debt=fc.net_debt,
                interest_coverage=fc.interest_coverage,
            )
        except Exception as exc:
            logger.warning("Health score computation failed for %s: %s", sym, exc)

        # 6. Business Intelligence from 10-K (LLM-extracted, 90-day cache)
        bi = None
        try:
            bi = await self._bi.get(sym, db)
        except Exception as exc:
            logger.warning("Business intelligence fetch failed for %s: %s", sym, exc)

        # 7. Business Map — merge rule-based baseline with 10-K intelligence
        role = get_value_chain_role(profile.sector, profile.industry)
        desc = profile.description or ""
        fallback_summary = ". ".join(desc.split(".")[:2]).strip() + "." if desc else None
        margin_impl = derive_margin_implication(fc.gross_margin, role)
        cyclicality = get_cyclicality_implication(profile.sector)

        business_map = BusinessMapSection(
            one_line_summary=(bi.one_line_summary if bi and bi.one_line_summary else fallback_summary),
            primary_value_chain_role=role,
            customer_types=(bi.customer_types if bi else []),
            revenue_model=(bi.revenue_model if bi else None),
            margin_implication=margin_impl,
            cyclicality_implication=cyclicality,
            pricing_power_implication=(bi.pricing_power_implication if bi else None),
            confidence=("high" if bi and bi.confidence == "high" else "partial"),
            source_notes=(bi.source_notes if bi else ["FMP /profile", "sector-to-value-chain mapping v1"]),
        )

        # 8. Market Position — peers from FMP + intelligence from 10-K
        market_cat = None
        if bi and bi.market_category:
            market_cat = bi.market_category
        elif profile.sector:
            cap_cat = getattr(profile, "market_cap_category", None)
            market_cat = f"{cap_cat}-Cap {profile.sector}" if cap_cat else profile.sector

        market_position = MarketPositionSection(
            market_category=market_cat,
            market_size_estimate=(bi.market_size_estimate or "Not disclosed") if bi else "estimate unavailable",
            market_growth_label=(bi.market_growth_label if bi else None),
            competitive_position_label=(bi.competitive_position_label if bi else None),
            market_share_notes=(bi.market_share_notes if bi else None),
            key_competitors=profile.peers[:5] if profile.peers else [],
            key_growth_drivers=(bi.key_growth_drivers if bi else []),
            key_risks=(bi.key_risks if bi else []),
            confidence=("high" if bi and bi.confidence == "high" else "partial"),
            source_notes=(bi.source_notes if bi else ["FMP /stock_peers", "FinanceDatabase sector mapping"]),
        )

        # 9. Financial Check section
        financial_check = FinancialCheckSection(
            financial_validation_label=get_financial_validation_label(fin_score),
            financial_validation_score=fin_score,
            valuation_risk_score=val_risk,
            overall_score=overall,
            growth_summary=_build_growth_summary(fc),
            profitability_summary=_build_profitability_summary(fc),
            cash_flow_summary=_build_cashflow_summary(fc),
            balance_sheet_summary=_build_balance_sheet_summary(fc),
            valuation_summary=_build_valuation_summary(fc, val_risk),
            revenue_yoy=fc.revenue_yoy,
            revenue_3y_cagr=fc.revenue_3y_cagr,
            eps_yoy=fc.eps_yoy,
            gross_margin=fc.gross_margin,
            operating_margin=fc.operating_margin,
            net_margin=fc.net_margin,
            roe=fc.roe,
            free_cash_flow=fc.free_cash_flow,
            fcf_margin=fc.fcf_margin,
            fcf_conversion=fc.fcf_conversion,
            cash=fc.cash,
            total_debt=fc.total_debt,
            net_debt=fc.net_debt,
            debt_to_equity=fc.debt_to_equity,
            current_ratio=fc.current_ratio,
            pe_ratio=fc.pe_ratio,
            ps_ratio=fc.ps_ratio,
            pb_ratio=fc.pb_ratio,
            peg_ratio=fc.peg_ratio,
            fcf_yield=fc.fcf_yield,
            dividend_yield=fc.dividend_yield,
            revenue_series=fc.revenue_series,
            margin_series=fc.margin_series,
            fcf_series=fc.fcf_series,
            warnings=warnings,
            source_notes=["FMP /income-statement", "FMP /cash-flow-statement", "FMP /key-metrics-ttm"],
        )

        # Build HealthScoreSection from computed result
        health_score = HealthScoreSection()
        if health_score_result is not None:
            health_score = HealthScoreSection(
                piotroski_score=health_score_result.piotroski_score,
                piotroski_label=health_score_result.piotroski_label,
                piotroski_signals=health_score_result.piotroski_signals.to_dict(),
                altman_z_score=health_score_result.altman_z_score,
                altman_z_label=health_score_result.altman_z_label,
                altman_z_na_reason=health_score_result.altman_z_na_reason,
                sector_piotroski_pct=health_score_result.sector_piotroski_pct,
                sector_piotroski_n=health_score_result.sector_piotroski_n,
                insight_quality=health_score_result.insight_quality,
                insight_safety=health_score_result.insight_safety,
                insight_value=health_score_result.insight_value,
                ev_ebitda=health_score_result.ev_ebitda,
                fcf_yield=health_score_result.fcf_yield,
                pe_ratio=health_score_result.pe_ratio,
                peg_ratio=health_score_result.peg_ratio,
            )

        return CompanyOverviewResponse(
            symbol=sym,
            name=profile.name,
            price=profile.price,
            market_cap=profile.market_cap,
            sector=profile.sector,
            industry=profile.industry,
            exchange=profile.exchange,
            country=profile.country,
            as_of_date=profile.as_of_date,
            health_score=health_score,
            business_map=business_map,
            market_position=market_position,
            financial_check=financial_check,
        )
