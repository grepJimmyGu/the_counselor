"""Chain-stage classifier (PRD-25) — fixes the pre-ramp mis-ranking (P3).

Deterministic, no LLM. Reads annual FMP fundamentals and labels a company
``pre_ramp | ramping | mature | declining`` and — critically — whether trailing
metrics are meaningful at that stage. A pre-revenue, qualification-stage company
is ranked *below* a declining incumbent by any trailing-metric screen; this flag
lets the UI say "trailing metrics are not meaningful here" instead of silently
mis-ranking.

Annual data only (FMP ``get_income_statement`` / ``get_cash_flow``, limit=5), so
figures carry an as-of date and the classifier degrades to ``unknown`` when
statements are missing rather than guessing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("livermore.supply_chain")

# A sub-scale company spending heavily on R&D is treated as pre-ramp: the thesis
# is that revenue has not arrived yet, so trailing metrics mislead. Thresholds
# match the PRD heuristic.
_PRE_RAMP_REVENUE_CEILING = 50_000_000.0
_PRE_RAMP_RND_RATIO = 0.40
_RAMPING_GROWTH = 0.60


@dataclass
class StageResult:
    stage: str  # pre_ramp | ramping | mature | declining | unknown
    trailing_metrics_meaningful: bool
    figures: dict = field(default_factory=dict)
    as_of_date: Optional[str] = None


def _f(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify_stage(income_statements: list[dict], cash_flows: list[dict]) -> StageResult:
    """Classify from annual statements (most-recent-first, as FMP returns them).

    Pure function — no network, no DB — so it is trivially unit-testable with
    synthetic statements. ``ChainStageService`` fetches the inputs.
    """
    if not income_statements:
        return StageResult("unknown", True, {"reason": "no income statement"})

    latest = income_statements[0]
    revenue = _f(latest.get("revenue"))
    rnd = _f(latest.get("researchAndDevelopmentExpenses"))
    as_of = latest.get("date") or latest.get("calendarYear")

    prev_revenue = (
        _f(income_statements[1].get("revenue")) if len(income_statements) > 1 else None
    )
    growth_yoy: Optional[float] = None
    if revenue is not None and prev_revenue not in (None, 0):
        growth_yoy = (revenue - prev_revenue) / abs(prev_revenue)

    # Consecutive annual revenue declines, counted from the most recent year.
    declining_years = 0
    for i in range(len(income_statements) - 1):
        cur = _f(income_statements[i].get("revenue"))
        older = _f(income_statements[i + 1].get("revenue"))
        if cur is not None and older not in (None, 0) and cur < older:
            declining_years += 1
        else:
            break

    fcf = _f(cash_flows[0].get("freeCashFlow")) if cash_flows else None
    rnd_ratio = (
        (rnd / revenue) if (rnd is not None and revenue not in (None, 0)) else None
    )

    figures = {
        "revenue": revenue,
        "revenue_growth_yoy": round(growth_yoy, 4) if growth_yoy is not None else None,
        "rnd_to_revenue": round(rnd_ratio, 4) if rnd_ratio is not None else None,
        "free_cash_flow": fcf,
        "declining_years": declining_years,
    }

    if revenue is None:
        return StageResult("unknown", True, figures, as_of)

    # Pre-ramp: sub-scale revenue + heavy R&D. (The "qualification language in
    # filings" branch of the PRD heuristic lands with the extraction backend;
    # the R&D-ratio branch is computable from fundamentals today.)
    if (
        revenue < _PRE_RAMP_REVENUE_CEILING
        and rnd_ratio is not None
        and rnd_ratio > _PRE_RAMP_RND_RATIO
    ):
        return StageResult("pre_ramp", False, figures, as_of)

    if growth_yoy is not None and growth_yoy > _RAMPING_GROWTH:
        return StageResult("ramping", True, figures, as_of)

    if declining_years >= 2:
        return StageResult("declining", True, figures, as_of)

    # Mature default — flat/positive growth; trailing metrics are valid.
    return StageResult("mature", True, figures, as_of)


class ChainStageService:
    """Fetches FMP fundamentals and classifies stage.

    Holds no DB session — the caller passes only the FMP client — so the network
    await never pins a pooled connection (trap #13).
    """

    def __init__(self, fmp_client) -> None:
        self._fmp = fmp_client

    async def get_stage(self, symbol: str) -> StageResult:
        try:
            income = await self._fmp.get_income_statement(symbol, limit=5)
            cash = await self._fmp.get_cash_flow(symbol, limit=5)
        except Exception:
            # trap #20: never silence a warmup/fetch failure with .warning()
            logger.exception("chain stage: FMP fetch failed for %s", symbol)
            return StageResult("unknown", True, {"reason": "fmp fetch failed"})
        return classify_stage(income or [], cash or [])
