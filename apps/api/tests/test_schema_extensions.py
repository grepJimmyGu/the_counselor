"""
Acceptance tests for strategy schema extensions (PRD: strategy-template-iteration).

Verifies:
  (a) Each new strategy_type parses into a valid StrategyJSON.
  (b) PositionSizing(method="vol_target", target_vol_annual=0.10) is valid.
  (c) PositionSizing(method="signal_weighted", signal_power=1.5) is valid.
  (d) Original 6 strategy types still validate unchanged.
  (e) validate_strategy emits a warning for new types with no rules.
  (f) validate_strategy does NOT emit the warning when rules are present.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.strategy import PositionSizing, StrategyJSON, StrategyRule
from app.services.strategy_validator import validate_strategy

# ── Shared fixture helpers ────────────────────────────────────────────────────

BASE = dict(
    strategy_name="Test Strategy",
    strategy_type="moving_average_filter",
    universe=["SPY"],
    benchmark="SPY",
    start_date="2020-01-01",
    end_date="2023-01-01",
    initial_capital=100_000,
    rebalance_frequency="monthly",
    transaction_cost_bps=5,
    slippage_bps=5,
    position_sizing={"method": "equal_weight"},
)


def make(**overrides) -> StrategyJSON:
    return StrategyJSON(**{**BASE, **overrides})


# ── (a) New strategy types ────────────────────────────────────────────────────

NEW_TYPES_WITH_RULES = [
    (
        "cross_sectional_momentum",
        [{"signal_source": "return", "rank_direction": "top", "top_pct": 0.2,
          "formation_period_days": 252, "skip_period_days": 21}],
    ),
    (
        "time_series_momentum",
        [{"signal_source": "return", "lookback_days": 252, "threshold": 0.0,
          "operator": "gt"}],
    ),
    (
        "short_term_reversal",
        [{"signal_source": "return", "rank_direction": "bottom",
          "formation_period_days": 5}],
    ),
    (
        "pairs_trading",
        [{"pair_symbol": "GLD", "zscore_entry": 2.0, "zscore_exit": 0.5,
          "zscore_stop": 3.0, "hedge_ratio": 1.0}],
    ),
    (
        "sector_rotation",
        [{"signal_source": "return", "rank_direction": "top", "top_n": 3,
          "formation_period_days": 63}],
    ),
    (
        "dual_momentum",
        [{"signal_source": "return", "lookback_days": 252, "threshold": 0.0,
          "operator": "gt"},
         {"signal_source": "return", "rank_direction": "top", "top_n": 1}],
    ),
    (
        "low_volatility",
        [{"signal_source": "vol", "rank_direction": "bottom", "top_pct": 0.2,
          "lookback_days": 63}],
    ),
    (
        "bollinger_mean_reversion",
        [{"indicator": "bollinger", "num_std": 2.0, "lookback_days": 20,
          "operator": "lt", "source": "close"}],
    ),
]


@pytest.mark.parametrize("strategy_type,rules", NEW_TYPES_WITH_RULES)
def test_new_strategy_type_parses(strategy_type, rules):
    s = make(strategy_type=strategy_type, rules=rules)
    assert s.strategy_type == strategy_type
    assert len(s.rules) == len(rules)


# ── (b) vol_target PositionSizing ─────────────────────────────────────────────

def test_vol_target_position_sizing_valid():
    ps = PositionSizing(method="vol_target", target_vol_annual=0.10)
    assert ps.method == "vol_target"
    assert ps.target_vol_annual == pytest.approx(0.10)
    assert ps.weights is None  # no weights required


def test_vol_target_in_full_strategy():
    s = make(
        strategy_type="low_volatility",
        rules=[{"signal_source": "vol", "rank_direction": "bottom", "top_pct": 0.2}],
        position_sizing={"method": "vol_target", "target_vol_annual": 0.15},
    )
    assert s.position_sizing.method == "vol_target"
    assert s.position_sizing.target_vol_annual == pytest.approx(0.15)


# ── (c) signal_weighted PositionSizing ────────────────────────────────────────

def test_signal_weighted_position_sizing_valid():
    ps = PositionSizing(method="signal_weighted", signal_power=1.5)
    assert ps.method == "signal_weighted"
    assert ps.signal_power == pytest.approx(1.5)
    assert ps.weights is None


# ── (d) Original 6 types still validate ──────────────────────────────────────

ORIGINAL_TYPES = [
    ("moving_average_filter",   [{"indicator": "sma", "lookback_days": 200,
                                   "operator": "gt", "source": "close"}]),
    ("moving_average_crossover",[{"fast_window": 50, "slow_window": 200}]),
    ("momentum_rotation",       [{"top_n": 3, "ranking_measure": "total_return",
                                   "ranking_lookback_days": 126}]),
    ("rsi_mean_reversion",      [{"indicator": "rsi", "lookback_days": 14,
                                   "threshold": 30, "operator": "lt"}]),
    ("breakout",                [{"entry_window": 20, "exit_window": 10}]),
    ("static_allocation",       []),
]


@pytest.mark.parametrize("strategy_type,rules", ORIGINAL_TYPES)
def test_original_strategy_types_still_valid(strategy_type, rules):
    extra = {}
    if strategy_type == "static_allocation":
        extra["position_sizing"] = {
            "method": "fixed_weight",
            "weights": {"SPY": 1.0},
        }
    s = make(strategy_type=strategy_type, rules=rules, **extra)
    assert s.strategy_type == strategy_type


def test_static_allocation_weight_sum_validation():
    with pytest.raises(ValidationError, match="weights must sum"):
        make(
            strategy_type="static_allocation",
            rules=[],
            position_sizing={"method": "fixed_weight", "weights": {"SPY": 0.5, "QQQ": 0.3}},
        )


def test_fixed_weight_requires_weights():
    with pytest.raises(ValidationError, match="requires weights"):
        make(position_sizing={"method": "fixed_weight"})


def test_end_date_must_be_after_start_date():
    with pytest.raises(ValidationError, match="end_date must be after"):
        make(start_date="2023-01-01", end_date="2022-01-01")


# ── (e) Validator warning for new type with no rules ─────────────────────────

def test_validator_warns_new_type_no_rules():
    # Prompt-2 and prompt-3 moved all schema types into ENGINE_SUPPORTED_TYPES,
    # so the "not yet supported" warning can no longer be triggered by normal
    # StrategyJSON construction.  We verify the logic still fires correctly by
    # temporarily shrinking the set, simulating a future schema extension that
    # has not yet been wired into the engine.
    import app.services.strategy_validator as _sv_mod
    import app.schemas.strategy as _schema_mod
    original = _schema_mod.ENGINE_SUPPORTED_TYPES
    try:
        # Remove pairs_trading from the supported set for this test
        _schema_mod.ENGINE_SUPPORTED_TYPES = original - {"pairs_trading"}
        _sv_mod.ENGINE_SUPPORTED_TYPES = _schema_mod.ENGINE_SUPPORTED_TYPES
        s = make(strategy_type="pairs_trading", rules=[])
        warnings = validate_strategy(s)
        assert any("pairs_trading" in w for w in warnings)
        assert any("not yet supported" in w for w in warnings)
    finally:
        _schema_mod.ENGINE_SUPPORTED_TYPES = original
        _sv_mod.ENGINE_SUPPORTED_TYPES = original


# ── (f) No warning when rules are present ────────────────────────────────────

def test_validator_no_warning_new_type_with_rules():
    s = make(
        strategy_type="pairs_trading",
        rules=[{"pair_symbol": "GLD", "zscore_entry": 2.0, "zscore_exit": 0.5}],
    )
    warnings = validate_strategy(s)
    # The "not yet supported" warning should NOT appear when rules are provided
    assert not any("not yet supported" in w for w in warnings)


# ── New StrategyRule fields parse correctly ───────────────────────────────────

def test_strategy_rule_new_fields():
    rule = StrategyRule(
        signal_source="f_score",
        rank_direction="top",
        zscore_entry=1.5,
        zscore_exit=0.0,
        zscore_stop=2.5,
        pair_symbol="MSFT",
        hedge_ratio=0.85,
        target_vol_annual=0.12,
        formation_period_days=252,
        skip_period_days=21,
        num_std=2.0,
        top_pct=0.25,
    )
    assert rule.signal_source == "f_score"
    assert rule.rank_direction == "top"
    assert rule.zscore_entry == pytest.approx(1.5)
    assert rule.top_pct == pytest.approx(0.25)


def test_strategy_rule_original_fields_unchanged():
    rule = StrategyRule(
        indicator="rsi",
        lookback_days=14,
        threshold=30.0,
        operator="lt",
        source="close",
        fast_window=50,
        slow_window=200,
        top_n=3,
        ranking_measure="total_return",
        ranking_lookback_days=126,
    )
    assert rule.indicator == "rsi"
    assert rule.fast_window == 50
    assert rule.ranking_measure == "total_return"
