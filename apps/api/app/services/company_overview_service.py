from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.concurrency import PerLoop, TTLCache

logger = logging.getLogger(__name__)

from app.schemas.company_overview import (
    BusinessMapSection,
    CompanyOverviewResponse,
    CompetitorRankingEntry,
    CompetitorSegmentSection,
    FinancialCheckSection,
    MarketPositionSection,
    RevenueSegmentSection,
    SegmentYearSchema,
    SupplyChainEntry,
)
from app.services.financial_validation_service import FinancialCheckMetrics, FinancialValidationService
from app.services.fmp_client import FMPClient, FMPNotConfiguredError, FMPRateLimitError
from app.services.fundamental_scoring_service import (
    compute_financial_validation_score,
    compute_valuation_risk_score,
    compute_overall_score,
    get_financial_validation_label,
    get_warnings,
)
from app.services.fundamental_service import FundamentalService
from app.services.business_intelligence_service import BusinessIntelligenceService
from app.services.revenue_segment_service import RevenueSegmentService
from app.services.competitor_group_service import CompetitorGroupService
from app.services.live_quote_service import live_quote_service
from app.services.value_chain_classifier import (
    derive_margin_implication,
    get_cyclicality_implication,
    get_value_chain_role,
)

# ── What is remembered, and for how long ─────────────────────────────────────
#
# Measured in production on 2026-11-20, before any of this existed: one view of
# a company page took 2.9 s, every time, because each view made six FMP calls
# one after another on six new connections. Twelve people opening twelve
# different companies at once waited 20 s; twelve opening the SAME company
# waited 27 s, each view rebuilding what the others were building. At ~300 FMP
# calls a minute that is also a ceiling of about 45 company views a minute for
# the whole product.
#
# So a finished page is kept for ten minutes and shared by everyone who asks
# for that company, including the callers who arrive while it is being built.
# For two hours after that the kept page is still returned at once while a new
# one is built behind it, so only the first viewer of a company waits at all.
# The price on a kept page is replaced with the latest live quote on the way
# out, so it is never older than the quote service's own.
OVERVIEW_TTL_SECONDS = 10 * 60
OVERVIEW_STALE_SECONDS = 2 * 60 * 60

# (the page, whether every provider answered). A page built while FMP was
# failing is returned to whoever was waiting and not kept.
_OVERVIEWS: "TTLCache[Tuple[CompanyOverviewResponse, bool]]" = TTLCache(
    ttl=OVERVIEW_TTL_SECONDS, stale_for=OVERVIEW_STALE_SECONDS, max_entries=1500,
    keep=lambda built: built[1],
)

# The three financial statements change when a company reports, four times a
# year, so what is derived from them is kept for six hours; a rebuild of the
# page then costs one FMP call (key metrics) instead of five.
_STATEMENT_METRICS: "TTLCache[Optional[FinancialCheckMetrics]]" = TTLCache(
    ttl=6 * 3600, max_entries=3000, keep=lambda metrics: metrics is not None,
)
# FMP's peer list for a symbol. Still read from FMP rather than from the
# profile cache (whose peers are the stale ones the comment below is about),
# just not on every single view.
_PEERS: "TTLCache[list]" = TTLCache(ttl=6 * 3600, max_entries=3000, keep=bool)

# Pages built at once. Each build holds a database connection and makes
# several FMP calls; a burst of first views queues here instead of draining
# the pool or tripping FMP's rate limiter.
_BUILD_SLOTS: "PerLoop[asyncio.Semaphore]" = PerLoop(lambda: asyncio.Semaphore(3))


def forget_overview(symbol: str) -> None:
    """Drop the kept page for a symbol, so the next view rebuilds it."""
    _OVERVIEWS.invalidate(symbol.upper())


def _kf(d: dict, key: str) -> Optional[float]:
    """Extract a float from a raw dict, returning None on failure."""
    v = d.get(key)
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _match_names_to_symbols(names: list[str], db: Session) -> dict[str, Optional[str]]:
    """
    Fuzzy-match a list of company names against the symbols table.
    Returns {name: symbol_or_None}.  Uses simple ILIKE — good enough for named entities.
    """
    result: dict[str, Optional[str]] = {}
    for name in names:
        if not name or len(name) < 2:
            result[name] = None
            continue
        try:
            row = db.execute(
                text(
                    "SELECT symbol FROM symbols"
                    " WHERE LOWER(name) LIKE LOWER(:pat) OR LOWER(symbol) = LOWER(:exact)"
                    " ORDER BY LENGTH(name) LIMIT 1"
                ),
                {"pat": f"%{name}%", "exact": name.strip()},
            ).fetchone()
            result[name] = row[0] if row else None
        except Exception:
            result[name] = None
    return result


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
        self._segments = RevenueSegmentService()
        self._competitors = CompetitorGroupService()

    async def get_overview(self, db: Session, symbol: str) -> CompanyOverviewResponse:
        """The company page for a symbol: from memory when it was built in the
        last ten minutes, otherwise built once for everyone asking."""
        sym = symbol.upper()
        # The build runs as its own task and outlives the request that
        # started it, so it must not use the request's session. It gets one
        # of its own on the same engine (which is what keeps tests on theirs).
        bind = db.get_bind()

        async def build() -> Tuple[CompanyOverviewResponse, bool]:
            async with _BUILD_SLOTS.get():
                own = sessionmaker(bind=bind, autoflush=False, autocommit=False, future=True)()
                try:
                    return await self._build(own, sym)
                finally:
                    own.close()

        response, _complete = await _OVERVIEWS.get(sym, build)
        live = live_quote_service.cached(sym, max_age=OVERVIEW_TTL_SECONDS + OVERVIEW_STALE_SECONDS)
        if live is not None and live.price:
            response = response.model_copy(update={"price": float(live.price)})
        return response

    async def _build(self, db: Session, sym: str) -> Tuple[CompanyOverviewResponse, bool]:
        """Build the page from its sources. The second value is False when a
        provider failed and part of the page is a fallback."""
        complete = True

        # 1. Profile (cached in FundamentalService)
        profile = await self._fundamental.get_profile(db, sym)

        # 2. Everything FMP is asked that does not depend on anything else,
        #    together: the live price, key metrics, the statements, peers.
        async def statement_metrics() -> Optional[FinancialCheckMetrics]:
            return await _STATEMENT_METRICS.get(sym, lambda: self._financial_svc.statement_metrics(sym))

        async def fmp_peer_list() -> list:
            return await _PEERS.get(sym, lambda: self._fmp.get_peers(sym))

        quote, key_metrics, base_metrics, fmp_peers = await asyncio.gather(
            live_quote_service.get_quote(sym),
            self._fmp.get_key_metrics(sym),
            statement_metrics(),
            fmp_peer_list(),
            return_exceptions=True,
        )

        # Live price, through the quote service so the page and the quote
        # endpoint share one fetch and one 30-second cache.
        if isinstance(quote, BaseException) or quote is None or not quote.price:
            complete = False
        else:
            profile = profile.model_copy(update={"price": float(quote.price)})

        # Key metrics raw dict (for the valuation figures)
        key_metrics_raw: dict = {}
        if isinstance(key_metrics, BaseException):
            complete = False
        else:
            key_metrics_raw = key_metrics or {}

        # 3. Financial Check metrics. A statement that could not be read for
        #    any reason other than FMP being unavailable fails the page, as it
        #    always has.
        if isinstance(base_metrics, BaseException):
            raise base_metrics
        if base_metrics is None:
            complete = False
        fc = self._financial_svc.with_valuation(base_metrics, key_metrics_raw)

        # 4. Scoring (used for backward-compat financial_check section)
        fin_score = compute_financial_validation_score(fc)
        val_risk = compute_valuation_risk_score(fc)
        overall = compute_overall_score(fin_score, val_risk)
        warnings = get_warnings(fc, val_risk)

        # 5. PRD-08d: Revenue segments (product + geo, 24h cache)
        seg_data = None
        try:
            seg_data = await self._segments.get(sym, db)
        except Exception as exc:
            logger.warning("Revenue segment fetch failed for %s: %s", sym, exc)

        # 7. PRD-08e: Competitor group rankings (lazy, 7-day cache)
        competitor_segment_list: list[CompetitorSegmentSection] = []
        try:
            segment_names = seg_data.segment_names if seg_data else []
            raw_peers = profile.peers[:8] if profile.peers else []
            if segment_names and raw_peers:
                rankings = await self._competitors.get_rankings(
                    symbol=sym,
                    symbol_name=profile.name,
                    segments=segment_names,
                    raw_peers=raw_peers,
                    db=db,
                )
                competitor_segment_list = [
                    CompetitorSegmentSection(
                        segment=r.segment,
                        rankings=[
                            CompetitorRankingEntry(
                                symbol=e.symbol,
                                name=e.name,
                                revenue=e.revenue,
                                revenue_raw=e.revenue_raw,
                                share=e.share,
                                position=e.position,
                                trend_5yr=e.trend_5yr,
                            )
                            for e in r.rankings
                        ],
                        disclaimer=r.disclaimer,
                    )
                    for r in rankings
                ]
        except Exception as exc:
            logger.warning("Competitor rankings failed for %s: %s", sym, exc)

        # 8. Business Intelligence from 10-K (LLM-extracted, 90-day cache)
        bi = None
        try:
            bi = await self._bi.get(sym, db)
        except Exception as exc:
            logger.warning("Business intelligence fetch failed for %s: %s", sym, exc)

        # 9. Peers — from FMP's peer endpoint, not the profile cache
        # Filter to symbols in our screener universe (eliminates garbage FMP peers like RIME, TBCH)
        peers: list[str] = []
        if isinstance(fmp_peers, BaseException):
            complete = False
            peers = profile.peers or []
        elif fmp_peers:
            raw_peers = list(fmp_peers)
            # Keep only peers that exist in our symbols table (large/mid-cap screener universe)
            peer_placeholders = ", ".join(f":p{i}" for i in range(len(raw_peers)))
            peer_params = {f"p{i}": s for i, s in enumerate(raw_peers)}
            try:
                existing = db.execute(
                    text(f"SELECT symbol FROM symbols WHERE symbol IN ({peer_placeholders})"),
                    peer_params,
                ).fetchall()
                known = {r[0] for r in existing}
                # Preserve original FMP order; fall back to all raw peers if DB has no matches
                filtered = [s for s in raw_peers if s in known]
                peers = filtered if filtered else raw_peers
            except Exception:
                peers = raw_peers

        # 11. Business Map — merge rule-based baseline with 10-K intelligence
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

        # 10. Market Position — peers from FMP + intelligence from 10-K
        market_cat = None
        if bi and bi.market_category:
            market_cat = bi.market_category
        elif profile.sector:
            cap_cat = getattr(profile, "market_cap_category", None)
            market_cat = f"{cap_cat}-Cap {profile.sector}" if cap_cat else profile.sector

        # Supply chain — match named suppliers/customers to symbols
        def _is_valid_name(name: str | None) -> bool:
            """Filter out LLM artifacts like 'null', empty strings, or None."""
            if not name:
                return False
            normalized = name.strip().lower()
            return normalized not in ("null", "none", "n/a", "na", "unknown", "")

        upstream_entries: list[SupplyChainEntry] = []
        downstream_entries: list[SupplyChainEntry] = []
        if bi and (bi.upstream_suppliers or bi.downstream_customers):
            valid_upstream = [n for n in (bi.upstream_suppliers or []) if _is_valid_name(n)]
            valid_downstream = [n for n in (bi.downstream_customers or []) if _is_valid_name(n)]
            all_names = valid_upstream + valid_downstream
            name_to_sym = _match_names_to_symbols(all_names, db)
            upstream_entries = [
                SupplyChainEntry(name=n, symbol=name_to_sym.get(n))
                for n in valid_upstream
            ]
            downstream_entries = [
                SupplyChainEntry(name=n, symbol=name_to_sym.get(n))
                for n in valid_downstream
            ]

        market_position = MarketPositionSection(
            market_category=market_cat,
            market_size_estimate=(bi.market_size_estimate or "Not disclosed") if bi else "estimate unavailable",
            market_growth_label=(bi.market_growth_label if bi else None),
            competitive_position_label=(bi.competitive_position_label if bi else None),
            market_share_notes=(bi.market_share_notes if bi else None),
            key_competitors=peers[:8],
            key_growth_drivers=(bi.key_growth_drivers if bi else []),
            key_risks=(bi.key_risks if bi else []),
            upstream_suppliers=upstream_entries,
            downstream_customers=downstream_entries,
            competitor_segments=competitor_segment_list,
            confidence=("high" if bi and bi.confidence == "high" else "partial"),
            source_notes=(bi.source_notes if bi else ["FMP /stock_peers", "FinanceDatabase sector mapping"]),
        )

        # 11. Financial Check section
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
            ev_ebitda=_kf(key_metrics_raw, "evToEBITDATTM") or _kf(key_metrics_raw, "enterpriseValueOverEBITDATTM"),
            dividend_yield=fc.dividend_yield,
            revenue_series=fc.revenue_series,
            margin_series=fc.margin_series,
            fcf_series=fc.fcf_series,
            warnings=warnings,
            source_notes=["FMP /income-statement", "FMP /cash-flow-statement", "FMP /key-metrics-ttm"],
        )

        # Build RevenueSegmentSection from fetched data
        revenue_segments = RevenueSegmentSection()
        if seg_data is not None:
            revenue_segments = RevenueSegmentSection(
                product_years=[
                    SegmentYearSchema(year=y.year, segments=y.segments)
                    for y in seg_data.product_years
                ],
                geo_years=[
                    SegmentYearSchema(year=y.year, segments=y.segments)
                    for y in seg_data.geo_years
                ],
                segment_names=seg_data.segment_names,
                geo_names=seg_data.geo_names,
                segment_colors=seg_data.segment_colors,
                geo_colors=seg_data.geo_colors,
                fallback_note=seg_data.fallback_note,
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
            revenue_segments=revenue_segments,
            business_map=business_map,
            market_position=market_position,
            financial_check=financial_check,
        ), complete
