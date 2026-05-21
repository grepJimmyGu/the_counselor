"""template_search chat tool — search the strategy template catalog.

The frontend at `apps/web/src/lib/contracts.ts:researchTemplates` is the
canonical catalog (consumed by `/templates` and `/templates/[slug]`). We
mirror a search-friendly subset of those entries here so the chat tool can
match by intent without round-tripping through the frontend.

**Drift risk:** the mirror duplicates frontend data. When a template is
added to `contracts.ts`, this list should be updated in the same PR. A
future refactor (PROJECT_BACKLOG candidate) could move the catalog to the
backend and have the frontend consume it via API — but for ticket #3 the
mirror is simpler and ships in one move.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class TemplateMatch(BaseModel):
    """One template, returned as a search hit."""

    id: str
    name: str
    category: str
    description: str
    chat_seed: str


class TemplateSearchResponse(BaseModel):
    """Top-N relevance-sorted matches."""

    query: str
    matches: List[TemplateMatch]
    total_in_catalog: int


# Mirror of `apps/web/src/lib/contracts.ts:researchTemplates`. Searchable
# subset only — chat doesn't need full strategy JSON to recommend; ticket
# #5's endpoint can fetch the full record via id if the user picks one.
_CATALOG: List[Dict[str, str]] = [
    {
        "id": "trend-following",
        "name": "Trend Following",
        "category": "Momentum",
        "description": "Price momentum with a trailing stop. Buy on 20-day breakout, exit on 10-day low or 8% stop.",
        "chat_seed": "I want to build a trend following strategy. Tell me your rules — breakout window, exit window, or stop type.",
    },
    {
        "id": "cross-sectional-momentum",
        "name": "Cross-Sectional Momentum",
        "category": "Momentum",
        "description": "Rank a universe by 6-month return monthly, hold the top 2, rotate the rest.",
        "chat_seed": "I want to build a cross-sectional momentum strategy. Which universe should I rank?",
    },
    {
        "id": "cross-sectional-momentum-12-1",
        "name": "Cross-Sectional Momentum (12-1)",
        "category": "Momentum",
        "description": "12-month return excluding the most recent month — the classic Jegadeesh-Titman signal.",
        "chat_seed": "I want to test the academic 12-minus-1 momentum signal on equities.",
    },
    {
        "id": "time-series-momentum",
        "name": "Time-Series Momentum",
        "category": "Momentum",
        "description": "Hold an asset when its trailing return is positive, cash when negative. Single-asset signal.",
        "chat_seed": "I want to build a time-series momentum strategy on one asset.",
    },
    {
        "id": "etf-rotation",
        "name": "ETF Rotation",
        "category": "Rotation",
        "description": "Rotate across a basket of sector or asset-class ETFs based on relative strength.",
        "chat_seed": "I want to build an ETF rotation strategy. Which ETFs should I rotate among?",
    },
    {
        "id": "sector-rotation-spdr",
        "name": "Sector Rotation — SPDR",
        "category": "Rotation",
        "description": "Rotate among the 11 SPDR sector ETFs based on 3-month relative momentum.",
        "chat_seed": "I want to build a sector rotation strategy using the SPDR sector ETFs.",
    },
    {
        "id": "dual-momentum",
        "name": "Dual Momentum",
        "category": "Rotation",
        "description": "Combine absolute and relative momentum — Gary Antonacci's signal across asset classes.",
        "chat_seed": "I want to build a dual momentum strategy across asset classes.",
    },
    {
        "id": "value-momentum",
        "name": "Value-Momentum",
        "category": "Factor",
        "description": "Combine cheap valuation with positive momentum — two of the most-replicated equity factors.",
        "chat_seed": "I want to build a value+momentum factor strategy.",
    },
    {
        "id": "low-volatility",
        "name": "Low Volatility",
        "category": "Factor",
        "description": "Hold the lowest-volatility names in the universe. Documented anomaly with high Sharpe.",
        "chat_seed": "I want to test a low-volatility factor strategy.",
    },
    {
        "id": "value-composite-cs",
        "name": "Value Composite (cross-sectional)",
        "category": "Factor",
        "description": "Rank by a composite value score (P/E, P/B, P/S, EV/EBITDA), hold the cheapest.",
        "chat_seed": "I want to build a multi-metric value composite factor strategy.",
    },
    {
        "id": "quality-piotroski-cs",
        "name": "Quality (Piotroski F-Score)",
        "category": "Factor",
        "description": "Hold high-quality stocks defined by the 9-component Piotroski F-Score.",
        "chat_seed": "I want to build a quality factor strategy using the Piotroski F-Score.",
    },
    {
        "id": "multi-factor-composite",
        "name": "Multi-Factor Composite",
        "category": "Factor",
        "description": "Combine value, momentum, quality, and low-volatility into a single ranking.",
        "chat_seed": "I want to build a multi-factor composite strategy combining value, momentum, and quality.",
    },
    {
        "id": "short-term-reversal",
        "name": "Short-Term Reversal",
        "category": "Mean Reversion",
        "description": "Buy losers, sell winners on a 1-week to 1-month horizon. The mean-reversion analogue of momentum.",
        "chat_seed": "I want to test a short-term reversal strategy.",
    },
    {
        "id": "bollinger-mean-reversion",
        "name": "Bollinger Mean Reversion",
        "category": "Mean Reversion",
        "description": "Buy when price closes below the lower Bollinger band, exit at the midline.",
        "chat_seed": "I want to build a Bollinger band mean-reversion strategy.",
    },
    {
        "id": "pairs-trading-long-only",
        "name": "Pairs Trading (long-only)",
        "category": "Mean Reversion",
        "description": "Long the underperformer in a correlated pair, exit on spread convergence. Long-only variant for retail.",
        "chat_seed": "I want to build a long-only pairs trading strategy.",
    },
    {
        "id": "commodity-carry",
        "name": "Commodity Carry",
        "category": "Carry",
        "description": "Long commodities in backwardation, flat in contango. Captures the roll yield.",
        "chat_seed": "I want to test a commodity carry strategy based on the futures curve.",
    },
    {
        "id": "news-sentiment-momentum",
        "name": "News Sentiment Momentum",
        "category": "Alternative Data",
        "description": "Long stocks with rising news sentiment, exit on sentiment decay.",
        "chat_seed": "I want to build a news sentiment momentum strategy.",
    },
    {
        "id": "insider-buying",
        "name": "Insider Buying",
        "category": "Alternative Data",
        "description": "Hold stocks that recent insider purchases. Form 4 filings as the signal.",
        "chat_seed": "I want to build an insider buying signal strategy.",
    },
    {
        "id": "pead-drift-cs",
        "name": "Post-Earnings Drift",
        "category": "Event-Driven",
        "description": "Hold stocks that beat earnings expectations. Captures the drift after announcement.",
        "chat_seed": "I want to test a post-earnings announcement drift strategy.",
    },
]


def _score(template: Dict[str, str], query_lower: str) -> int:
    """Heuristic relevance score. Higher = better match.

    Order matters: name match dominates because users usually type a name
    fragment they saw on /templates. Category and description provide
    fuzzier intent-style matching.
    """
    score = 0
    if query_lower in template["name"].lower():
        score += 100
    if query_lower in template["category"].lower():
        score += 50
    if query_lower in template["description"].lower():
        score += 20
    if query_lower in template["chat_seed"].lower():
        score += 10
    # Token-level bonus — split the query, score per-token hits in name.
    for token in query_lower.split():
        if len(token) < 3:
            continue  # skip "on", "of", "a", etc.
        if token in template["name"].lower():
            score += 15
        if token in template["description"].lower():
            score += 5
    return score


async def search_templates(query: str, limit: int = 5) -> TemplateSearchResponse:
    """Search the template catalog by name / category / description intent.

    Returns up to `limit` (default 5) matches sorted by relevance. Empty
    matches list means nothing crossed the relevance threshold (score > 0).
    The total catalog size is included so the LLM can hint at it.
    """
    q = query.strip().lower()
    if not q:
        return TemplateSearchResponse(query=query, matches=[], total_in_catalog=len(_CATALOG))

    scored = [(t, _score(t, q)) for t in _CATALOG]
    scored = [pair for pair in scored if pair[1] > 0]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    matches = [TemplateMatch(**t) for t, _ in scored[:limit]]
    return TemplateSearchResponse(
        query=query,
        matches=matches,
        total_in_catalog=len(_CATALOG),
    )


TEMPLATE_SEARCH_DEF: Dict[str, Any] = {
    "name": "template_search",
    "description": (
        "Search Livermore's strategy template catalog by intent. Useful "
        "when the user describes a strategy idea ('momentum on tech', "
        "'pairs trading', 'value factor') and you want to surface a "
        "pre-built template that matches. Returns up to 5 relevance-sorted "
        "matches with id, name, category, description, and a chat_seed "
        "prompt the user can use to start customizing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural-language description of the strategy intent. "
                    "Examples: 'cross-sectional momentum', 'pairs trading on "
                    "ETFs', 'low volatility factor'. The shorter and more "
                    "specific, the better."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max number of matches to return (default 5, max 10).",
                "default": 5,
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "handler": search_templates,
}
