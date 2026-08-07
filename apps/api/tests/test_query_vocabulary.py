"""Vocabulary and fold coverage for the home search box.

Every case here comes from a query Jimmy wrote as a candidate example for the
"traders ask" block. Three of his four extracted NOTHING and would have fallen
through to the LLM parser — which interrogates instead of screening. Example
queries that don't work are worse than no example queries.

The direction cases guard a bug this work surfaced: the MACD signal-cross
pattern ended in `(?:up|above)?` — optional — so "macd crossing down" matched it
and produced a **crosses_up** rule. The builder's "Crossing down" pill screened
for crossings up, with a chip that read "Crossing down". The existing contract
test passed throughout, because it only asserted that a phrase parses, never
that it parses to the right direction.
"""
from __future__ import annotations

import pytest

from app.services.screen_rule_parser import extract_rules


def _ops(query: str):
    rules, _ = extract_rules(query)
    return [(r["primitive_id"], r["operator"]) for r in rules]


def _folds(query: str):
    rules, _ = extract_rules(query)
    return [r["logic_with_prior"] for r in rules]


# ── hyphenation: people don't type the closed form ────────────────────────
@pytest.mark.parametrize("q", ["oversold", "over-sold", "over sold"])
def test_oversold_spellings(q) -> None:
    assert ("rsi", "lt") in _ops(q)


@pytest.mark.parametrize("q", ["overbought", "over-bought", "over bought"])
def test_overbought_spellings(q) -> None:
    assert ("rsi", "gt") in _ops(q)


# ── direction must survive ────────────────────────────────────────────────
def test_macd_crossing_down_is_not_a_crossing_up() -> None:
    assert _ops("macd crossing down") == [("macd_signal_cross", "crosses_down")]


def test_macd_crossing_up_still_works() -> None:
    assert _ops("macd crossing up") == [("macd_signal_cross", "crosses_up")]


# ── a break is an event, not a standing state ─────────────────────────────
@pytest.mark.parametrize(
    "q", ["break 50 MA", "breaks above the 50-day", "breaking the 50 day moving average"]
)
def test_breaking_an_ma_is_a_cross_not_a_level(q) -> None:
    assert _ops(q) == [("price_above_ma", "crosses_up")]


def test_standing_above_an_ma_is_still_a_level() -> None:
    # The distinction matters: "above the 200-day" is every name currently
    # above it; "breaks the 200-day" is the handful that crossed today.
    assert _ops("above the 200-day") == [("price_above_ma", "is_true")]


# ── compound conditions sharing one subject ───────────────────────────────
def test_macd_compound_yields_both_halves() -> None:
    ops = _ops("MACD above zero line and cross up")
    assert ("macd_signal_cross", "crosses_up") in ops
    assert ("macd_zero_line_cross", "crosses_up") in ops


# ── the fold has to match the connective ──────────────────────────────────
def test_or_query_folds_as_or() -> None:
    """RSI>70 AND RSI<30 is unsatisfiable — folding this as AND would return
    zero names and read as 'nothing matched' rather than 'we misread you'."""
    q = "Popular stocks that are over-bought or over sold"
    assert _ops(q) == [("rsi", "gt"), ("rsi", "lt")]
    assert _folds(q) == [None, "OR"]


def test_and_query_still_folds_as_and() -> None:
    assert _folds("oversold and above the 200-day") == [None, "AND"]


def test_juxtaposition_defaults_to_and() -> None:
    # No connective at all — "oversold above the 200 day MA".
    assert _folds("oversold above the 200 day MA") == [None, "AND"]


# ── quality phrasing ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "q", ["solid fundamentals", "strong fundamentals", "good fundamentals", "high quality"]
)
def test_quality_phrases_map_to_the_quality_primitive(q) -> None:
    assert _ops(q) == [("f_score", "gte")]


def test_the_bare_word_fundamentals_is_not_enough() -> None:
    # Conservative by design: "fundamentals" alone states a topic, not a
    # constraint. Inventing F-score >= 7 from it would screen on something the
    # user never asked for.
    assert _ops("fundamentals") == []


# ── Jimmy's four candidate example queries ────────────────────────────────
def test_jimmys_example_queries_extract_something() -> None:
    for q in [
        "Stocks with solid fundamentals and break 50 MA",
        "MACD above zero line and cross up",
        "Popular stocks that are over-bought or over sold",
    ]:
        assert _ops(q), f"{q!r} extracted nothing — it would fall through to the LLM"


def test_chinese_queries_are_still_unsupported() -> None:
    """Documents a known gap rather than asserting it's fine. The parsers are
    English-only regex; the 中文 toggle switches UI copy, not query parsing. If
    this ever starts passing, Chinese support arrived and the docs need it."""
    assert _ops("均线多头排列") == []
