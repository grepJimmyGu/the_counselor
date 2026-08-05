"""Extract the FUNDAMENTAL half of a mixed search query (PRD-29).

"Small caps that are oversold" carries two independent asks:
  - fundamental: market-cap tier = small        → this module
  - technical:   RSI oversold                   → parse_strategy_message

Splitting them lets the search path narrow the universe with cheap SQL and then
run the technical scan over the survivors, which is what makes a 問財-style
mixed query work at all.

Pure and deterministic — no DB, no LLM, no I/O — so the whole vocabulary is
unit-testable and costs nothing on a public endpoint. It is intentionally
CONSERVATIVE: an unrecognised phrase yields no filter, and the query degrades
to a technical-only screen rather than inventing a constraint the user didn't
ask for. Never guess a sector.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.data.sectors import normalize_sector

from app.data.screen_filter_vocab import (
    CAP_SYNONYMS,
    DEFAULT_MIN_DIVIDEND_YIELD,
    DIVIDEND_PHRASES,
    SECTOR_SYNONYMS,
    VALUE_MAX_PE,
)
from app.schemas.screener import ScreenerFilters

# "p/e under 15", "pe below 20", "p/e < 12".
# The trailing `(?!\d)` is load-bearing: without it `\d{1,3}` happily captures
# the first three digits of "999999" and yields a bogus P/E of 999 that passes
# every sanity check downstream.
_PE_UNDER = re.compile(
    r"\bp\.?/?e\b[^0-9]{0,18}?(?:under|below|less than|<|<=|beneath)?\s*"
    r"(\d{1,3}(?:\.\d+)?)(?!\d)",
    re.I,
)
# "under a 15 p/e" — the number precedes the metric.
_PE_UNDER_REVERSED = re.compile(
    r"\b(?:under|below|less than|<|<=)\s*(?:a\s+)?(\d{1,3}(?:\.\d+)?)(?!\d)\s*p\.?/?e\b",
    re.I,
)
# "dividend yield above 3%" / "yielding more than 4%"
_YIELD_OVER = re.compile(
    r"(?:yield|yielding)[^0-9]{0,18}?(?:above|over|more than|>|>=|at least)?\s*"
    r"(\d{1,2}(?:\.\d+)?)(?!\d)\s*%",
    re.I,
)


def _match_phrase(haystack: str, phrase: str) -> bool:
    """Whole-phrase match, tolerating a plural.

    Word-boundaried so 'retail' doesn't fire inside 'retailer earnings' and
    'oil' doesn't fire inside 'toil'. The trailing `s?` matters more than it
    looks: people type "small caps", not "small cap", and without it the most
    common phrasing of the most common filter silently extracts nothing.
    """
    return (
        re.search(r"(?<!\w)" + re.escape(phrase) + r"s?(?!\w)", haystack) is not None
    )


def _extract_sector(lowered: str) -> Optional[str]:
    """Canonical sector key, longest synonym first so 'consumer staples' wins
    over 'staples'. Returns None when nothing matches — never a guess."""
    for synonym in sorted(SECTOR_SYNONYMS, key=len, reverse=True):
        if _match_phrase(lowered, synonym):
            return SECTOR_SYNONYMS[synonym]
    return None


def _extract_cap(lowered: str) -> Optional[str]:
    for phrase in sorted(CAP_SYNONYMS, key=len, reverse=True):
        if _match_phrase(lowered, phrase):
            return CAP_SYNONYMS[phrase]
    return None


def _extract_max_pe(lowered: str) -> Optional[float]:
    for pattern in (_PE_UNDER_REVERSED, _PE_UNDER):
        m = pattern.search(lowered)
        if m:
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            # A "P/E" over 1000 is a parse artefact, not an intent.
            if 0 < value <= 1000:
                return value
    for phrase, ceiling in VALUE_MAX_PE:
        if _match_phrase(lowered, phrase):
            return ceiling
    return None


def _extract_min_dividend(lowered: str) -> Optional[float]:
    m = _YIELD_OVER.search(lowered)
    if m:
        try:
            pct = float(m.group(1))
        except ValueError:
            pct = -1.0
        if 0 < pct <= 100:
            return pct / 100.0
    for phrase in DIVIDEND_PHRASES:
        if _match_phrase(lowered, phrase):
            return DEFAULT_MIN_DIVIDEND_YIELD
    return None


def extract_filters(query: str) -> Tuple[Optional[ScreenerFilters], List[str]]:
    """Pull any fundamental constraints out of a free-text query.

    Returns `(filters, applied)` where `applied` is a list of plain-English
    descriptions of what was understood — the caller shows these so the user
    can see which part of their sentence became a filter, rather than trusting
    an opaque result. `filters` is None when nothing matched.
    """
    lowered = query.lower()
    applied: List[str] = []

    sector = _extract_sector(lowered)
    cap = _extract_cap(lowered)
    max_pe = _extract_max_pe(lowered)
    min_div = _extract_min_dividend(lowered)

    if sector is None and cap is None and max_pe is None and min_div is None:
        return None, []

    filters = ScreenerFilters()
    if sector is not None:
        # Stored as a canonical key; `matching_symbols` expands it to every
        # spelling in the DB (see screen_filter_vocab on why that matters).
        filters.sector = sector
        applied.append(f"{sector} sector")
    if cap is not None:
        filters.market_cap_category = cap
        applied.append(f"{cap}-cap")
    if max_pe is not None:
        filters.max_pe = max_pe
        applied.append(f"P/E under {max_pe:g}")
    if min_div is not None:
        filters.min_dividend_yield = min_div
        applied.append(f"dividend yield over {min_div * 100:g}%")

    return filters, applied


def screener_query_params(filters: ScreenerFilters) -> Dict[str, str]:
    """The `/stocks` query string that reproduces `filters`.

    A fundamental-only query ("p/e under 15") has no technical rule, so there is
    nothing for the signal scan to evaluate — its natural home is the stock
    screener page, which already renders P/E and dividend-yield columns and
    reads exactly these params from the URL. This is the inverse of
    `extract_filters`; keep the two in step.
    """
    out: Dict[str, str] = {}
    if filters.sector:
        # `filters.sector` is our internal key ("healthcare"); the screener
        # endpoint matches the stored GICS label ("Health Care") exactly, so
        # canonicalise or the URL silently returns nothing.
        out["sector"] = normalize_sector(filters.sector) or filters.sector
    if filters.market_cap_category:
        out["market_cap_category"] = filters.market_cap_category
    if filters.max_pe is not None:
        out["max_pe"] = f"{filters.max_pe:g}"
    if filters.min_pe is not None:
        out["min_pe"] = f"{filters.min_pe:g}"
    if filters.min_dividend_yield is not None:
        out["min_dividend_yield"] = f"{filters.min_dividend_yield:g}"
    return out
