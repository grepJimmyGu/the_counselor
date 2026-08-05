"""Fundamental-only queries must return a screen, not an interrogation.

The regression: "p/e under 15" carries no TECHNICAL rule, so `extract_rules`
returned nothing and the route fell through to the LLM strategy parser. That
parser exists to build a complete backtestable strategy, so it answered with
"Which strategy type should I use?" and discarded the symbols SQL had already
matched. Measured against production before the fix — all three of "p/e under
15", "cheap value stocks" and "dividend yield above 4%" came back
`intent=ambiguous`.
"""
from __future__ import annotations

from app.schemas.search import SearchIntent
from app.services.search_dispatch_service import (
    FundamentalNarrowing,
    build_screen_result_from_filters,
)


def test_fundamental_only_query_becomes_a_screen() -> None:
    r = build_screen_result_from_filters(
        "p/e under 15",
        FundamentalNarrowing(symbols=["JPM", "XOM"], applied=["P/E under 15"], total=2),
    )
    assert r.intent == SearchIntent.SCREEN
    # Not the LLM's "Which strategy type should I use?"
    assert "strategy type" not in (r.note or "")
    assert "Matched 2 names on P/E under 15" in r.note


def test_it_hands_the_symbols_to_the_scan_with_no_rules() -> None:
    r = build_screen_result_from_filters(
        "dividend yield above 4%",
        FundamentalNarrowing(symbols=["T", "VZ"], applied=["dividend yield over 4%"], total=2),
    )
    # "symbols" + empty rules is the contract `scan_service` reads as
    # "the filtering already happened upstream".
    assert r.screen.universe_id == "symbols"
    assert r.screen.rules == []
    assert r.screen.symbols == ["T", "VZ"]
    assert r.screen.fundamental_filters == ["dividend yield over 4%"]


def test_no_matches_is_ambiguous_not_an_empty_screen() -> None:
    r = build_screen_result_from_filters(
        "p/e under 1",
        FundamentalNarrowing(symbols=[], applied=["P/E under 1"], total=0),
    )
    assert r.intent == SearchIntent.AMBIGUOUS
    assert "No names match" in r.note


def test_truncation_is_disclosed_not_silently_capped() -> None:
    r = build_screen_result_from_filters(
        "large caps",
        FundamentalNarrowing(
            symbols=[f"S{i}" for i in range(1500)],
            applied=["large-cap"],
            total=4000,
            truncated_from=4000,
        ),
    )
    assert r.screen.universe_truncated_from == 4000
    assert "1500 largest of 4000" in r.note
