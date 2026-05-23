"""stock_lookup chat tool — Health / Valuation / Trend scorecard for a ticker.

Wraps `CompanyOverviewService.get_overview()` which already produces the
full Health/Val/Trend bundle the `/stocks/[ticker]` page renders. The
chat tool projects this into a compact summary the LLM can weave into a
prose response.

Stage 3 S&P 500 scope for Scout is enforced at the chat endpoint layer
(ticket #5) — same convention as backtest_execute. This tool happily
looks up any ticker that has overview data cached.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.db.session import SessionLocal
from app.services.company_overview_service import CompanyOverviewService


class ScoreSection(BaseModel):
    """One Health / Valuation / Trend score with its top drivers."""

    label: str
    score: str  # "Strongly Positive" / "Moderately Positive" / "Neutral" / "Caution" / "Concerning"
    drivers: List[str]


class StockLookupResponse(BaseModel):
    """Compact scorecard. Full overview is at `/api/company/{ticker}/overview`."""

    success: bool
    ticker: str
    as_of: Optional[str] = None
    name: Optional[str] = None
    sector: Optional[str] = None
    health: Optional[ScoreSection] = None
    valuation: Optional[ScoreSection] = None
    trend: Optional[ScoreSection] = None
    one_line_summary: Optional[str] = None
    error: Optional[str] = None


def _section_from_financial_check(overview) -> Optional[ScoreSection]:
    """Project the financial_check block into the Health scorecard.

    The CompanyOverviewService returns rich numeric fields; we surface the
    label-style summaries that already exist on the response.
    """
    fc = getattr(overview, "financial_check", None)
    if fc is None:
        return None
    drivers: List[str] = []
    if getattr(fc, "growth_summary", None):
        drivers.append(fc.growth_summary)
    if getattr(fc, "profitability_summary", None):
        drivers.append(fc.profitability_summary)
    if getattr(fc, "cash_flow_summary", None):
        drivers.append(fc.cash_flow_summary)
    if getattr(fc, "balance_sheet_summary", None):
        drivers.append(fc.balance_sheet_summary)
    return ScoreSection(
        label="Health",
        score=getattr(fc, "financial_validation_label", "Neutral"),
        drivers=drivers[:3],  # cap at 3 drivers — chat-context budget
    )


def _section_from_valuation(overview) -> Optional[ScoreSection]:
    fc = getattr(overview, "financial_check", None)
    if fc is None:
        return None
    drivers: List[str] = []
    if getattr(fc, "valuation_summary", None):
        drivers.append(fc.valuation_summary)
    warnings = getattr(fc, "warnings", None) or []
    drivers.extend(warnings[:2])

    score_raw = getattr(fc, "valuation_risk_score", None)
    if score_raw is None:
        score = "Neutral"
    elif score_raw < 33:
        score = "Strongly Positive"
    elif score_raw < 66:
        score = "Neutral"
    else:
        score = "Caution"
    return ScoreSection(label="Valuation", score=score, drivers=drivers[:3])


async def lookup_stock(ticker: str) -> StockLookupResponse:
    """Fetch the Health/Val/Trend scorecard for `ticker`. Errors are caught."""
    sym = ticker.strip().upper()
    if not sym:
        return StockLookupResponse(success=False, ticker=ticker, error="Empty ticker.")

    db = SessionLocal()
    try:
        service = CompanyOverviewService()
        try:
            overview = await service.get_overview(db, sym)
        except Exception as exc:
            return StockLookupResponse(
                success=False,
                ticker=sym,
                error=f"No overview data for {sym}: {exc}",
            )

        # Defensive date→str coercion at the seam. CompanyOverviewService
        # returns `as_of_date` as a `datetime.date`, but this response model
        # uses Optional[str] (LLM consumes JSON serialization). Pydantic v2
        # is strict and won't coerce date → str on construction. Production
        # symptom: every stock_lookup call raised ValidationError, swallowed
        # by dispatch loop into {"error": "Tool stock_lookup failed: ..."},
        # LLM apologized for "temporary issue". See KNOWN_ISSUES.md 2026-05-23
        # + the parametrized prod-shape test at
        # tests/test_chat_tools_production_shapes.py.
        as_of_raw = getattr(overview, "as_of_date", None)
        if as_of_raw is None:
            as_of_str = None
        elif hasattr(as_of_raw, "isoformat"):
            as_of_str = as_of_raw.isoformat()
        else:
            as_of_str = str(as_of_raw)

        return StockLookupResponse(
            success=True,
            ticker=overview.symbol,
            as_of=as_of_str,
            name=getattr(overview, "name", None),
            sector=getattr(overview, "sector", None),
            health=_section_from_financial_check(overview),
            valuation=_section_from_valuation(overview),
            # Trend section comes from a separate route in the existing code;
            # for ticket #4 the chat returns a placeholder trend so the LLM
            # can ask the user to view the full stock page for the chart.
            trend=ScoreSection(
                label="Trend",
                score="See /stocks/{} for the chart".format(overview.symbol),
                drivers=[],
            ),
            one_line_summary=getattr(
                getattr(overview, "business_map", None), "one_line_summary", None
            ),
        )
    finally:
        db.close()


STOCK_LOOKUP_DEF: Dict[str, Any] = {
    "name": "stock_lookup",
    "description": (
        "Look up a stock's Health, Valuation, and Trend scorecard. Use for "
        "stock-specific questions ('what's the bear case for AAPL', "
        "'should I look at NVDA', 'how does TSLA look fundamentally'). "
        "Returns the same Health/Val scores the user sees on the stock "
        "detail page. Combine with concept_explainer if the user also "
        "asks what a specific metric means. Do NOT use for general market "
        "or sector questions — use the Market Pulse data through chat "
        "context instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": (
                    "Stock ticker symbol, e.g., 'AAPL', 'TSLA'. Case-"
                    "insensitive; the tool uppercases internally."
                ),
            },
        },
        "required": ["ticker"],
        "additionalProperties": False,
    },
    "handler": lookup_stock,
}
