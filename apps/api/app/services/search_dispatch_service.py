"""Route a smart-search query to COMPANY / SCREEN / AMBIGUOUS (PRD-27).

The pure decision (`classify`) and the result-builders live here so they're
unit-testable without the DB or the LLM. The route does the async I/O (symbol
lookup + the parser) and calls into these.
"""
from __future__ import annotations

from typing import List, Optional

from app.schemas.market_data import SymbolSearchItem
from app.schemas.search import ParseResult, SearchIntent, SearchScreen
from app.schemas.strategy import StrategyChatResponse

# Broad + responsive default. Fundamental universe selection ("small cap") is
# the deferred fundamental-filter slice — v1 runs technical rules over sp500.
DEFAULT_SCREEN_UNIVERSE = "sp500"

_SCREEN_KEYWORDS = (
    "above", "below", "over ", "under", "cross", "oversold", "overbought",
    "breakout", "breakdown", "rsi", "macd", "sma", "ema", "moving average",
    "bollinger", "momentum", "volume", "dividend", "yield", "p/e", "pe ratio",
    "earnings", "gap", "52-week", "52 week", "small cap", "large cap",
    "mid cap", "growth", "value", "200-day", "200 day", "50-day", "50 day",
)


def exact_symbol_match(
    query: str, matches: List[SymbolSearchItem]
) -> Optional[SymbolSearchItem]:
    qu = query.strip().upper()
    for m in matches:
        if m.symbol.upper() == qu:
            return m
    return None


def _is_screen_like(query: str) -> bool:
    q = query.lower()
    if any(ch.isdigit() for ch in q):
        return True
    if any(token in q for token in ("<", ">", "%")):
        return True
    if len(q.split()) >= 3:
        return True
    return any(kw in q for kw in _SCREEN_KEYWORDS)


def classify(query: str, matches: List[SymbolSearchItem]) -> SearchIntent:
    """Decide the route from the query + symbol matches (no I/O).

    COMPANY when the query resolves to a ticker / company; otherwise SCREEN —
    the box's non-company job is screening (v3.1 §4). A SCREEN the parser can't
    turn into runnable rules is downgraded to AMBIGUOUS in `build_screen_result`,
    so classify itself only picks COMPANY vs SCREEN.
    """
    if exact_symbol_match(query, matches) is not None:
        return SearchIntent.COMPANY
    if _is_screen_like(query):
        return SearchIntent.SCREEN
    # Short, non-screen-like: a company-name match wins; else a loose screen.
    return SearchIntent.COMPANY if matches else SearchIntent.SCREEN


def best_company_match(
    query: str, matches: List[SymbolSearchItem]
) -> Optional[SymbolSearchItem]:
    return exact_symbol_match(query, matches) or (matches[0] if matches else None)


def build_company_result(
    query: str, match: Optional[SymbolSearchItem]
) -> ParseResult:
    if match is None:
        return ParseResult(
            intent=SearchIntent.AMBIGUOUS,
            query=query,
            note="No matching company found.",
        )
    return ParseResult(
        intent=SearchIntent.COMPANY,
        query=query,
        symbol=match.symbol,
        company_name=match.name,
        confidence=0.9,
    )


def build_screen_result(query: str, parsed: StrategyChatResponse) -> ParseResult:
    """Turn the parser output into a runnable SCREEN, or AMBIGUOUS if it
    produced no usable conditions."""
    sj_dict = parsed.strategy_json.model_dump() if parsed.strategy_json else None
    rules = (sj_dict or {}).get("rules") or []

    if not rules:
        note = parsed.suggested_reformulation or (
            parsed.clarification_questions[0]
            if parsed.clarification_questions
            else "Couldn't turn that into a screen — try naming an indicator, "
            "e.g. 'RSI below 30'."
        )
        return ParseResult(
            intent=SearchIntent.AMBIGUOUS, query=query, note=note, confidence=0.3
        )

    notes: List[str] = []
    if parsed.approximation_note:
        notes.append(parsed.approximation_note)
    notes.append(
        "Screened the S&P 500 on your technical rules. Fundamental filters "
        "(e.g. market cap, P/E) aren't applied yet."
    )
    return ParseResult(
        intent=SearchIntent.SCREEN,
        query=query,
        screen=SearchScreen(universe_id=DEFAULT_SCREEN_UNIVERSE, rules=rules),
        strategy_json=sj_dict,
        note=" ".join(notes),
        confidence=0.7,
    )
