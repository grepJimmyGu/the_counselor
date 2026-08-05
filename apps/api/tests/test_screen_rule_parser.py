"""PRD-29 hotfix — extract screening rules WITHOUT the strategy parser.

SYMPTOM (production, 2026-08-05): typing a perfectly clear screen into the home
box returned an AMBIGUOUS clarification and zero rules —
  "oversold above 200 day MA"       -> "What universe of tickers…?"
  "SPY oversold above 200 day MA"   -> "What lookback period…?"
ROOT CAUSE: `/api/search/parse` reused `parse_strategy_message`, whose job is to
produce a COMPLETE backtestable StrategyJSON. Missing any field, it interrogates
the user instead of extracting the conditions it was given. A screen needs no
universe (the scope pill sets it) and no capital/rebalance settings.
FIX: extract conditions deterministically; the parser is now only a fallback.
"""
from __future__ import annotations

from app.schemas.search import SearchIntent
from app.services.screen_rule_parser import extract_rules
from app.services.search_dispatch_service import (
    FundamentalNarrowing,
    build_screen_result_from_rules,
)


# ── the exact reported failures ───────────────────────────────────────────


def test_the_reported_query_now_yields_rules() -> None:
    """'oversold above 200 day MA' — the query that asked about universe."""
    rules, readings = extract_rules("oversold above 200 day MA")
    ids = [r["primitive_id"] for r in rules]
    assert "rsi" in ids and "price_above_ma" in ids
    ma = next(r for r in rules if r["primitive_id"] == "price_above_ma")
    assert ma["primitive_params"]["period"] == 200
    assert readings


def test_a_named_ticker_does_not_break_extraction() -> None:
    rules, _ = extract_rules("SPY oversold above 200 day MA")
    assert [r["primitive_id"] for r in rules]


# ── vocabulary ────────────────────────────────────────────────────────────


def test_oversold_and_overbought_map_to_rsi_bounds() -> None:
    lo, _ = extract_rules("oversold names")
    assert lo[0] == {"primitive_id": "rsi", "operator": "lt", "threshold": 30,
                     "logic_with_prior": None, "primitive_params": {"period": 14}}
    hi, _ = extract_rules("overbought names")
    assert hi[0]["operator"] == "gt" and hi[0]["threshold"] == 70


def test_explicit_rsi_threshold_wins() -> None:
    rules, _ = extract_rules("rsi below 25")
    assert rules[0]["threshold"] == 25


def test_moving_average_period_is_read_from_the_query() -> None:
    for n in (50, 200):
        rules, _ = extract_rules(f"above the {n} day moving average")
        ma = next(r for r in rules if r["primitive_id"] == "price_above_ma")
        assert ma["primitive_params"]["period"] == n


def test_crosses_breakouts_squeezes_and_volume() -> None:
    assert extract_rules("golden cross")[0][0]["primitive_id"] == "golden_cross"
    assert extract_rules("death cross")[0][0]["primitive_id"] == "death_cross"
    assert extract_rules("breaking out")[0][0]["primitive_id"] == "donchian_breakout"
    assert extract_rules("volatility squeeze")[0][0]["primitive_id"] == "ttm_squeeze"
    assert extract_rules("unusual volume")[0][0]["primitive_id"] == "rvol_surge"


def test_operators_match_each_primitive_kind() -> None:
    """A rule carrying the wrong operator for its kind silently fails to
    evaluate (PRD-22c dispatch), so pin them."""
    kind_op = {
        "oversold": ("rsi", "lt"),                       # VALUE
        "golden cross": ("golden_cross", "crosses_up"),  # CROSS
        "above the 200 day": ("price_above_ma", "is_true"),   # LEVEL
        "breaking out": ("donchian_breakout", "fires"),  # EVENT
        "squeeze": ("ttm_squeeze", "is_true"),           # emits 0/1
    }
    for phrase, (pid, op) in kind_op.items():
        rules, _ = extract_rules(phrase)
        r = next(r for r in rules if r["primitive_id"] == pid)
        assert r["operator"] == op, f"{phrase}: expected {op}, got {r['operator']}"


def test_first_rule_has_null_fold_and_rest_are_and() -> None:
    """The backend validator rejects a first rule with a non-null fold."""
    rules, _ = extract_rules("oversold above the 200 day and breaking out")
    assert rules[0]["logic_with_prior"] is None
    assert all(r["logic_with_prior"] == "AND" for r in rules[1:])


def test_unrecognised_text_extracts_nothing() -> None:
    """Must fall through to the LLM rather than invent a condition."""
    assert extract_rules("something completely unrelated") == ([], [])


# ── result shaping ────────────────────────────────────────────────────────


def test_builds_a_screen_without_ever_asking_for_a_universe() -> None:
    rules, readings = extract_rules("oversold above 200 day MA")
    result = build_screen_result_from_rules("oversold above 200 day MA", rules, readings)
    assert result.intent == SearchIntent.SCREEN
    assert result.screen.universe_id == "sp500"
    assert "universe" not in (result.note or "").lower()


def test_mixed_query_still_narrows_by_fundamentals() -> None:
    rules, readings = extract_rules("small caps that are oversold")
    result = build_screen_result_from_rules(
        "small caps that are oversold", rules, readings,
        FundamentalNarrowing(symbols=["AAA"], applied=["small-cap"], total=1),
    )
    assert result.screen.universe_id == "symbols"
    assert result.screen.symbols == ["AAA"]
    assert "small-cap" in result.note
