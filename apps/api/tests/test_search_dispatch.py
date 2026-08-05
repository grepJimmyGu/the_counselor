"""PRD-27 — unified smart-search dispatch (pure routing + result builders).

No DB / LLM here: `classify` and the builders are pure, so we exercise the
routing table and the SCREEN/AMBIGUOUS shaping directly. The route's async I/O
(symbol lookup + parser) is thin glue over these.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import List, Optional

from app.schemas.market_data import SymbolSearchItem
from app.schemas.search import SearchIntent
from app.services.search_dispatch_service import (
    DEFAULT_SCREEN_UNIVERSE,
    build_company_result,
    build_screen_result,
    universe_label,
    classify,
)


def _items(*pairs: tuple) -> List[SymbolSearchItem]:
    return [SymbolSearchItem(symbol=s, name=n) for s, n in pairs]


def _parsed(
    rules: Optional[list],
    approximation_note: Optional[str] = None,
    suggested_reformulation: Optional[str] = None,
    clarification_questions: Optional[list] = None,
) -> SimpleNamespace:
    """Duck-typed StrategyChatResponse (avoids building a full StrategyJSON)."""
    sj = (
        SimpleNamespace(
            model_dump=lambda: {
                "strategy_type": "custom_build",
                "universe": ["AAPL"],
                "rules": rules,
            }
        )
        if rules is not None
        else None
    )
    return SimpleNamespace(
        strategy_json=sj,
        approximation_note=approximation_note,
        suggested_reformulation=suggested_reformulation,
        clarification_questions=clarification_questions or [],
    )


# ── classify: the routing table ───────────────────────────────────────────


def test_bare_ticker_routes_to_company() -> None:
    assert classify("AAPL", _items(("AAPL", "Apple Inc"))) == SearchIntent.COMPANY


def test_company_name_match_routes_to_company() -> None:
    # "apple" != symbol "AAPL", but the name match wins for a short query.
    assert classify("apple", _items(("AAPL", "Apple Inc"))) == SearchIntent.COMPANY


def test_phrase_starting_with_a_ticker_routes_to_screen() -> None:
    # The whole query isn't the ticker "V" — it's a screen phrase → SCREEN.
    assert (
        classify("V above 200-day", _items(("V", "Visa Inc"))) == SearchIntent.SCREEN
    )


def test_free_text_routes_to_screen() -> None:
    assert (
        classify("oversold stocks above their 200 day", []) == SearchIntent.SCREEN
    )


def test_screen_keyword_without_digits_routes_to_screen() -> None:
    assert classify("stocks with a bullish macd cross", []) == SearchIntent.SCREEN


def test_unknown_short_token_falls_through_to_screen() -> None:
    # No symbol match, not screen-like → loose screen (parser then decides).
    assert classify("zzzz", []) == SearchIntent.SCREEN


# ── builders ──────────────────────────────────────────────────────────────


def test_build_company_result() -> None:
    r = build_company_result("aapl", SymbolSearchItem(symbol="AAPL", name="Apple Inc"))
    assert r.intent == SearchIntent.COMPANY
    assert r.symbol == "AAPL"
    assert r.company_name == "Apple Inc"


def test_build_company_result_no_match_is_ambiguous() -> None:
    r = build_company_result("zzzz", None)
    assert r.intent == SearchIntent.AMBIGUOUS
    assert r.symbol is None


def test_build_screen_result_with_rules() -> None:
    parsed = _parsed(rules=[{"primitive_id": "rsi", "operator": "lt", "threshold": 30}])
    r = build_screen_result("oversold names", parsed)
    assert r.intent == SearchIntent.SCREEN
    assert r.screen is not None
    assert r.screen.universe_id == DEFAULT_SCREEN_UNIVERSE
    assert r.screen.rules and r.screen.rules[0]["primitive_id"] == "rsi"
    assert r.strategy_json is not None
    # Transparency: says which universe + that fundamental filters are deferred.
    assert "S&P 500" in (r.note or "")


def test_build_screen_result_no_rules_is_ambiguous() -> None:
    parsed = _parsed(rules=[], clarification_questions=["Which indicator did you mean?"])
    r = build_screen_result("do the thing", parsed)
    assert r.intent == SearchIntent.AMBIGUOUS
    assert "indicator" in (r.note or "").lower()


def test_build_screen_result_no_strategy_json_is_ambiguous() -> None:
    r = build_screen_result("???", _parsed(rules=None))
    assert r.intent == SearchIntent.AMBIGUOUS


def test_universe_label_is_human_readable() -> None:
    assert universe_label("sp500") == "the S&P 500"
    assert universe_label("russell3000") == "the Russell 3000"


def test_universe_label_falls_back_to_the_raw_id() -> None:
    # Unknown ids can't reach here (the route 422s first), but the note should
    # degrade to something printable rather than raising.
    assert universe_label("nasdaq100") == "nasdaq100"


def test_screen_note_names_the_universe_it_scanned() -> None:
    parsed = _parsed(rules=[{"primitive_id": "rsi_14", "operator": "lt"}])
    assert "the S&P 500" in build_screen_result("oversold names", parsed).note
    assert (
        "the Russell 3000"
        in build_screen_result(
            "oversold names", parsed, universe_id="russell3000"
        ).note
    )
