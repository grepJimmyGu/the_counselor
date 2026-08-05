"""Route a smart-search query to COMPANY / SCREEN / AMBIGUOUS (PRD-27).

The pure decision (`classify`) and the result-builders live here so they're
unit-testable without the DB or the LLM. The route does the async I/O (symbol
lookup + the parser) and calls into these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.market_data import SymbolSearchItem
from app.schemas.search import ParseResult, SearchIntent, SearchScreen
from app.schemas.strategy import StrategyChatResponse

# The universe when the query carries no fundamental constraint of its own.
DEFAULT_SCREEN_UNIVERSE = "sp500"


@dataclass
class FundamentalNarrowing:
    """Result of resolving the fundamental half of a mixed query to symbols.

    Built by the route (it needs the DB); passed in here so the result-shaping
    stays pure and testable.
    """

    symbols: List[str]
    # Plain-English echo of what was understood, e.g. ["small-cap", "P/E under 15"].
    applied: List[str] = field(default_factory=list)
    # Total matches before the cap — equals len(symbols) when nothing was cut.
    total: int = 0
    # Set only when the cap actually bit, so the caller can disclose it.
    truncated_from: Optional[int] = None

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


def build_screen_result(
    query: str,
    parsed: StrategyChatResponse,
    fundamental: Optional[FundamentalNarrowing] = None,
) -> ParseResult:
    """Turn the parser output into a runnable SCREEN, or AMBIGUOUS if it
    produced no usable conditions.

    `fundamental` carries the pre-resolved fundamental half of a mixed query
    (PRD-29). None = purely technical, which keeps the previous behaviour.
    """
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

    # PRD-29 — mixed query. When the sentence also carried fundamental
    # constraints, the caller has already resolved them to a symbol list; the
    # technical rules then run over exactly those names instead of the whole
    # standing universe.
    if fundamental is not None and fundamental.symbols:
        screen = SearchScreen(
            universe_id="symbols",
            rules=rules,
            symbols=fundamental.symbols,
            fundamental_filters=fundamental.applied,
            universe_truncated_from=fundamental.truncated_from,
        )
        applied = " + ".join(fundamental.applied)
        notes.append(
            f"Matched {fundamental.total} names on {applied}, then screened "
            "them on your technical rules."
        )
        if fundamental.truncated_from:
            notes.append(
                f"Only the {len(fundamental.symbols)} largest of "
                f"{fundamental.truncated_from} matches were screened — narrow "
                "the query to cover the rest."
            )
    elif fundamental is not None and not fundamental.symbols:
        # The fundamental half was understood but matched nothing. Say so
        # rather than silently widening back to the whole index, which would
        # return names that contradict what the user asked for.
        applied = " + ".join(fundamental.applied)
        return ParseResult(
            intent=SearchIntent.AMBIGUOUS,
            query=query,
            note=f"No names match {applied}. Try loosening that part.",
            confidence=0.3,
        )
    else:
        screen = SearchScreen(universe_id=DEFAULT_SCREEN_UNIVERSE, rules=rules)
        notes.append(
            "Screened the S&P 500 on your technical rules."
        )

    return ParseResult(
        intent=SearchIntent.SCREEN,
        query=query,
        screen=screen,
        strategy_json=sj_dict,
        note=" ".join(notes),
        confidence=0.7,
    )


def build_screen_result_from_rules(
    query: str,
    rules: List[dict],
    readings: List[str],
    fundamental: Optional[FundamentalNarrowing] = None,
) -> ParseResult:
    """Build a SCREEN from rules extracted DIRECTLY from the query.

    The LLM strategy parser interrogates the user for every field a
    backtestable strategy needs (universe, lookback, thresholds) and returns
    NO rules when any are missing — measured in production, it answered
    "oversold above 200 day MA" with "What universe of tickers?" and zero
    rules. A screen needs none of that: the scope pill sets the universe and
    the primitive defaults supply the rest. So when the deterministic
    extractor understands the query, we skip the parser entirely.
    """
    notes: List[str] = []
    screen_kwargs = {"rules": rules}

    if fundamental is not None and fundamental.symbols:
        screen_kwargs.update(
            universe_id="symbols",
            symbols=fundamental.symbols,
            fundamental_filters=fundamental.applied,
            universe_truncated_from=fundamental.truncated_from,
        )
        notes.append(
            f"Matched {fundamental.total} names on "
            f"{' + '.join(fundamental.applied)}, then screened them on "
            f"{' + '.join(readings)}."
        )
        if fundamental.truncated_from:
            notes.append(
                f"Only the {len(fundamental.symbols)} largest of "
                f"{fundamental.truncated_from} matches were screened — narrow "
                "the query to cover the rest."
            )
    elif fundamental is not None and not fundamental.symbols:
        return ParseResult(
            intent=SearchIntent.AMBIGUOUS,
            query=query,
            note=f"No names match {' + '.join(fundamental.applied)}. "
            "Try loosening that part.",
            confidence=0.3,
        )
    else:
        screen_kwargs["universe_id"] = DEFAULT_SCREEN_UNIVERSE
        notes.append(f"Screened the S&P 500 on {' + '.join(readings)}.")

    return ParseResult(
        intent=SearchIntent.SCREEN,
        query=query,
        screen=SearchScreen(**screen_kwargs),
        note=" ".join(notes),
        confidence=0.8,
    )
