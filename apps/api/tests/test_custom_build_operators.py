"""PRD-22c slice (a) — custom_build operator dispatch.

The composer's v2 kind-widgets serialize to new `StrategyRule` operators
(`fires` / `crosses_up` / `in_range` / …). The engine's `_apply_rule_threshold`
must evaluate them, while the legacy VALUE operators (gt/gte/lt/lte) stay
byte-identical (no-regression). This is also the exact evaluator PRD-23's
screener scan + rank call.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from app.schemas.strategy import StrategyRule
from app.services.backtester.engine import BacktestEngine


def _apply(operator, series, threshold=None):
    rule = StrategyRule(operator=operator, threshold=threshold)
    return BacktestEngine()._apply_rule_threshold(rule, pd.Series(series, dtype=float))


# ── New shape-reading operators ──────────────────────────────────────────────


def test_fires_is_nonzero() -> None:
    assert _apply("fires", [0, 1, 0, -1, 2]).tolist() == [False, True, False, True, True]


def test_is_true_is_bool_of_value() -> None:
    assert _apply("is_true", [0, 1, 0, 1]).tolist() == [False, True, False, True]


def test_crosses_up_is_plus_one() -> None:
    assert _apply("crosses_up", [0, 1, -1, 1, 0]).tolist() == [False, True, False, True, False]


def test_crosses_down_is_minus_one() -> None:
    assert _apply("crosses_down", [0, 1, -1, 1, -1]).tolist() == [False, False, True, False, True]


def test_legacy_cross_aliases_now_implemented() -> None:
    # crosses_above/below were in the schema but raised before — now they map
    # to the same ±1 semantics as crosses_up/down.
    assert _apply("crosses_above", [0, 1, -1]).tolist() == [False, True, False]
    assert _apply("crosses_below", [0, 1, -1]).tolist() == [False, False, True]


def test_divergence_operators() -> None:
    assert _apply("divergence_bullish", [0, 1, -1]).tolist() == [False, True, False]
    assert _apply("divergence_bearish", [0, 1, -1]).tolist() == [False, False, True]


def test_in_range_is_inclusive_between() -> None:
    # "within 2-25% below the 52-week high" → distance in [-25, -2].
    out = _apply("in_range", [-1, -2, -15, -25, -30], threshold={"min": -25, "max": -2})
    assert out.tolist() == [False, True, True, True, False]


def test_in_range_tolerates_reversed_bounds() -> None:
    out = _apply("in_range", [-1, -15, -30], threshold={"min": -2, "max": -25})
    assert out.tolist() == [False, True, False]


def test_equals_numeric_target() -> None:
    # regime code: squeeze "on" == 1
    assert _apply("equals", [0, 1, 0, 1], threshold=1).tolist() == [False, True, False, True]


def test_equals_string_target() -> None:
    rule = StrategyRule(operator="equals", threshold="trending")
    out = BacktestEngine()._apply_rule_threshold(
        rule, pd.Series(["ranging", "trending", "trending"]))
    assert out.tolist() == [False, True, True]


# ── Legacy VALUE operators — byte-identical (no-regression) ───────────────────


def test_value_operators_unchanged() -> None:
    assert _apply("gt", [1, 2, 3], threshold=2).tolist() == [False, False, True]
    assert _apply("gte", [1, 2, 3], threshold=2).tolist() == [False, True, True]
    assert _apply("lt", [1, 2, 3], threshold=2).tolist() == [True, False, False]
    assert _apply("lte", [1, 2, 3], threshold=2).tolist() == [True, True, False]


def test_threshold_none_falls_back_to_bool_for_value_ops() -> None:
    # The donchian_breakout 0/1 case — threshold None + a VALUE operator.
    assert _apply("gt", [0, 1, 0, 1], threshold=None).tolist() == [False, True, False, True]


def test_unknown_operator_raises_defensively() -> None:
    # The schema Literal now covers every operator, so the engine's fallback
    # raise is only reachable via a non-schema object — assert it still guards.
    bogus = SimpleNamespace(operator="bogus", threshold=1)
    with pytest.raises(ValueError, match="not supported"):
        BacktestEngine()._apply_rule_threshold(bogus, pd.Series([1.0, 2.0]))


# ── Schema accepts the widened operator + threshold shapes ────────────────────


def test_schema_accepts_new_operators_and_threshold_shapes() -> None:
    StrategyRule(operator="fires")
    StrategyRule(operator="in_range", threshold={"min": -25, "max": -2})
    StrategyRule(operator="equals", threshold="trending")
    StrategyRule(operator="gt", threshold=30.0)  # legacy float still valid
