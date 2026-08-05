"""Vocabulary for turning plain English into `ScreenerFilters` (PRD-29).

The box has to answer "small caps that are oversold" — one query mixing a
FUNDAMENTAL filter (small cap) with a TECHNICAL reading (oversold). The
technical half already works via `parse_strategy_message`; this file supplies
the closed vocabulary for the fundamental half.

**Deliberately deterministic, not an LLM call.** `ScreenerFilters` is a tiny,
closed vocabulary (sector / market-cap tier / P/E / dividend), and
`POST /api/search/parse` is public and unauthenticated — it already makes one
LLM call, and a second would double the cost and abuse surface of an endpoint
that has no rate limit yet. A miss here degrades gracefully: the query still
runs as a technical-only screen.

**Sector aliases are load-bearing.** Production stores 17 spellings for 11
sectors because more than one upstream provider populates `SymbolCache.sector`
(plus a literal `'nan'`). Since the shipped screener filters with `==`, a query
that resolves "healthcare" to a single spelling silently drops every company
stored as the other one. Every canonical sector below therefore maps to ALL of
its known spellings, and the new symbol lookup matches with `IN`, not `==`.
(The underlying data bug is tracked separately; this map keeps the search path
correct meanwhile.)
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# canonical sector → every spelling seen in production (verified against
# GET /api/screener/filters on 2026-08-05).
SECTOR_ALIASES: Dict[str, List[str]] = {
    "technology": ["Technology", "Information Technology"],
    "healthcare": ["Healthcare", "Health Care"],
    "financials": ["Financials", "Financial Services"],
    "consumer discretionary": ["Consumer Discretionary", "Consumer Cyclical"],
    "consumer staples": ["Consumer Staples", "Consumer Defensive"],
    "materials": ["Materials", "Basic Materials"],
    "energy": ["Energy"],
    "industrials": ["Industrials"],
    "utilities": ["Utilities"],
    "real estate": ["Real Estate"],
    "communication services": ["Communication Services"],
}

# Words a user is likely to type → canonical sector key above.
SECTOR_SYNONYMS: Dict[str, str] = {
    "tech": "technology",
    "technology": "technology",
    "software": "technology",
    "semiconductor": "technology",
    "semiconductors": "technology",
    "semis": "technology",
    "health": "healthcare",
    "healthcare": "healthcare",
    "health care": "healthcare",
    "biotech": "healthcare",
    "pharma": "healthcare",
    "financial": "financials",
    "financials": "financials",
    "finance": "financials",
    "bank": "financials",
    "banks": "financials",
    "consumer discretionary": "consumer discretionary",
    "consumer cyclical": "consumer discretionary",
    "retail": "consumer discretionary",
    "consumer staples": "consumer staples",
    "consumer defensive": "consumer staples",
    "staples": "consumer staples",
    "materials": "materials",
    "basic materials": "materials",
    "mining": "materials",
    "energy": "energy",
    "oil": "energy",
    "oil and gas": "energy",
    "industrial": "industrials",
    "industrials": "industrials",
    "utility": "utilities",
    "utilities": "utilities",
    "real estate": "real estate",
    "reit": "real estate",
    "reits": "real estate",
    "communication": "communication services",
    "communication services": "communication services",
    "telecom": "communication services",
    "media": "communication services",
}

# Market-cap tier — the stored `SymbolCache.market_cap_category` values are
# mega / large / mid / small / micro.
CAP_SYNONYMS: Dict[str, str] = {
    "mega cap": "mega",
    "megacap": "mega",
    "mega-cap": "mega",
    "large cap": "large",
    "largecap": "large",
    "large-cap": "large",
    "big cap": "large",
    "mid cap": "mid",
    "midcap": "mid",
    "mid-cap": "mid",
    "small cap": "small",
    "smallcap": "small",
    "small-cap": "small",
    "micro cap": "micro",
    "microcap": "micro",
    "micro-cap": "micro",
}

# Phrases implying a cheap / expensive valuation, mapped to a P/E bound.
# Conservative, conventional cut-offs — not optimised, and stated as such to
# the user in the result note.
VALUE_MAX_PE: Tuple[Tuple[str, float], ...] = (
    ("deep value", 10.0),
    ("cheap", 15.0),
    ("undervalued", 15.0),
    ("low pe", 15.0),
    ("low p/e", 15.0),
    ("value stocks", 15.0),
    ("value names", 15.0),
)

# Phrases implying the user wants dividend payers.
DIVIDEND_PHRASES: Tuple[str, ...] = (
    "dividend",
    "dividends",
    "income stocks",
    "yielders",
    "high yield",
)
DEFAULT_MIN_DIVIDEND_YIELD = 0.02  # 2% — a payer, not a token distribution


def sector_spellings(canonical: str) -> List[str]:
    """Every stored spelling for a canonical sector (empty if unknown)."""
    return SECTOR_ALIASES.get(canonical, [])
