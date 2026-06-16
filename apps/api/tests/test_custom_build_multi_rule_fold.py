"""PRD-16b-1 — Custom Build multi-rule fold + schema validation.

Three layers:
  1. Schema validation — first rule must NOT have logic_with_prior;
     custom_build subsequent rules MUST have it.
  2. Engine multi-rule fold — synthetic strategies with 2-3 rules
     under AND / OR / mixed verify fold output equals manual computation.
  3. Backwards compatibility — the additive schema fields don't
     affect any of the existing 22 templates' validation or backtest
     output. Covered by the full suite still passing on this commit.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.schemas.strategy import PositionSizing, StrategyJSON, StrategyRule
from app.services.backtester.engine import BacktestEngine


# ── Shared fixtures ──────────────────────────────────────────────────────────


def _base_strategy(rules: list[StrategyRule]) -> StrategyJSON:
    """A minimal valid custom_build StrategyJSON for testing fold + validation."""
    return StrategyJSON(
        strategy_name="Custom build test",
        strategy_type="custom_build",
        universe=["SPY"],
        benchmark="SPY",
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=5,
        slippage_bps=5,
        position_sizing=PositionSizing(method="equal_weight"),
        rules=rules,
    )


def _synthetic_close_matrix(periods: int = 252) -> pd.DataFrame:
    """Deterministic random-walk closes indexed by trading days."""
    rng = np.random.default_rng(123)
    returns = rng.normal(0.0005, 0.012, periods)
    closes = 100 * np.exp(np.cumsum(returns))
    dates = pd.date_range(end=date.today(), periods=periods, freq="B")
    return pd.DataFrame({"SPY": closes}, index=dates)


def _synthetic_ohlcv(
    close_matrix: pd.DataFrame, symbol: str = "SPY", volume: float = 1_000_000.0,
) -> "dict[str, pd.DataFrame]":
    """Full OHLCV frame for the engine's custom_build path — the real-data
    contract `_evaluate_custom_build_block` now requires. High/low bracket
    the close; volume is a constant test fixture (NOT a production
    fabrication — production threads in real `price_bars` OHLCV)."""
    close = close_matrix[symbol]
    return {
        symbol: pd.DataFrame(
            {
                "open": close.shift(1).fillna(close),
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "adjusted_close": close,
                "volume": pd.Series(volume, index=close.index),
            }
        )
    }


# ── Schema validation ───────────────────────────────────────────────────────


def test_first_rule_with_logic_with_prior_set_is_rejected() -> None:
    """The fold operator joins rules[i] to rules[i-1]; rules[0] has
    nothing to join to."""
    with pytest.raises(ValidationError) as exc:
        _base_strategy([
            StrategyRule(primitive_id="rsi", operator="lt", threshold=30,
                         logic_with_prior="AND"),
        ])
    assert "First rule" in str(exc.value)


def test_custom_build_with_missing_primitive_id_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _base_strategy([
            StrategyRule(operator="lt", threshold=30),
        ])
    assert "primitive_id" in str(exc.value)


def test_custom_build_subsequent_rule_without_logic_with_prior_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _base_strategy([
            StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
            StrategyRule(primitive_id="bbands", operator="lt", threshold=0.5),
        ])
    assert "logic_with_prior" in str(exc.value)


def test_custom_build_with_zero_rules_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _base_strategy([])
    assert "at least one rule" in str(exc.value)


def test_valid_two_rule_custom_build_passes() -> None:
    s = _base_strategy([
        StrategyRule(primitive_id="rsi", operator="lt", threshold=30),
        StrategyRule(primitive_id="bbands", operator="lt", threshold=0.5,
                     logic_with_prior="AND"),
    ])
    assert s.strategy_type == "custom_build"
    assert len(s.rules) == 2


def test_existing_template_with_legacy_multi_rule_block_still_validates() -> None:
    """rsi_mean_reversion has 2 rules (buy_rule + sell_rule) but it's not
    a fold — it uses rules[0] + rules[1] for separate buy/sell logic.
    The logic_with_prior contract should NOT apply to legacy types.

    Pitfall C — additive change must not break existing template
    validation."""
    s = StrategyJSON(
        strategy_name="Legacy RSI mean reversion",
        strategy_type="rsi_mean_reversion",
        universe=["NVDA"],
        benchmark="SPY",
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=5,
        slippage_bps=5,
        position_sizing=PositionSizing(method="equal_weight"),
        rules=[
            StrategyRule(indicator="rsi", lookback_days=14, threshold=30),
            StrategyRule(indicator="rsi", lookback_days=14, threshold=60),
        ],
    )
    assert s.strategy_type == "rsi_mean_reversion"


# ── Engine fold ──────────────────────────────────────────────────────────────


def test_single_rule_block_returns_threshold_comparison() -> None:
    """One rule, no fold: result is just the per-bar threshold comparison
    on the primitive's output."""
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [StrategyRule(primitive_id="sma", operator="lt", threshold=110.0,
                          primitive_params={"period": 10})]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    # Compare against the actual computed SMA.
    sma = closes["SPY"].rolling(10).mean()
    expected = (sma < 110.0).fillna(False)
    pd.testing.assert_series_equal(
        result, expected, check_names=False,
    )


def test_two_rule_AND_fold_intersection() -> None:
    """Two rules with AND — result should be the intersection of both
    boolean Series."""
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [
        StrategyRule(primitive_id="sma", operator="lt", threshold=110.0,
                     primitive_params={"period": 10}),
        StrategyRule(primitive_id="rsi", operator="lt", threshold=70.0,
                     primitive_params={"period": 14},
                     logic_with_prior="AND"),
    ]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    # Manual AND.
    sma = closes["SPY"].rolling(10).mean()
    delta = closes["SPY"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - (100 / (1 + avg_gain / avg_loss.replace(0, np.nan)))
    expected = ((sma < 110.0) & (rsi < 70.0)).fillna(False)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_two_rule_OR_fold_union() -> None:
    """OR — result is the union of both boolean Series."""
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [
        StrategyRule(primitive_id="sma", operator="lt", threshold=95.0,
                     primitive_params={"period": 10}),
        StrategyRule(primitive_id="sma", operator="gt", threshold=115.0,
                     primitive_params={"period": 10},
                     logic_with_prior="OR"),
    ]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    sma = closes["SPY"].rolling(10).mean()
    expected = ((sma < 95.0) | (sma > 115.0)).fillna(False)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_three_rule_mixed_fold_evaluates_left_to_right() -> None:
    """Mixed AND/OR — engine should fold left-to-right per the schema
    docstring. Verify the actual evaluation order produces the expected
    boolean."""
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [
        StrategyRule(primitive_id="sma", operator="lt", threshold=110.0,
                     primitive_params={"period": 10}),
        StrategyRule(primitive_id="sma", operator="lt", threshold=105.0,
                     primitive_params={"period": 20},
                     logic_with_prior="AND"),
        StrategyRule(primitive_id="sma", operator="gt", threshold=115.0,
                     primitive_params={"period": 30},
                     logic_with_prior="OR"),
    ]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    sma_10 = closes["SPY"].rolling(10).mean()
    sma_20 = closes["SPY"].rolling(20).mean()
    sma_30 = closes["SPY"].rolling(30).mean()
    # Left-to-right: ((sma_10 < 110) AND (sma_20 < 105)) OR (sma_30 > 115)
    expected_lr = (
        ((sma_10 < 110.0) & (sma_20 < 105.0)) | (sma_30 > 115.0)
    ).fillna(False)
    pd.testing.assert_series_equal(result, expected_lr, check_names=False)


def test_unknown_primitive_id_raises() -> None:
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [StrategyRule(primitive_id="not_a_real_primitive",
                          operator="gt", threshold=0)]
    with pytest.raises(ValueError, match="unknown primitive_id"):
        engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))


def test_av_endpoint_primitive_raises_in_custom_build_v1() -> None:
    """AV-endpoint primitives need async DB path — out of scope for
    v1's synchronous engine call. Pin the documented constraint with a
    test so a future agent doesn't accidentally support them and ship a
    half-working path."""
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    # KAMA is an AV-endpoint primitive per the catalog.
    rules = [StrategyRule(primitive_id="kama", operator="gt", threshold=100.0)]
    with pytest.raises(ValueError, match="not supported in custom_build v1"):
        engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))


# ── Threshold + operator handling ────────────────────────────────────────────


@pytest.mark.parametrize("operator,expected_fn", [
    ("gt", lambda s, t: s > t),
    ("gte", lambda s, t: s >= t),
    ("lt", lambda s, t: s < t),
    ("lte", lambda s, t: s <= t),
])
def test_operators_apply_correctly(operator: str, expected_fn) -> None:
    closes = _synthetic_close_matrix(periods=100)
    engine = BacktestEngine()
    rules = [StrategyRule(primitive_id="sma", operator=operator, threshold=100.0,
                          primitive_params={"period": 5})]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    sma = closes["SPY"].rolling(5).mean()
    expected = expected_fn(sma, 100.0).fillna(False)
    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_v2_cross_operator_now_evaluated_not_raised() -> None:
    # PRD-22c (slice a): the v2 kind operators (crosses_above/up, fires,
    # in_range, equals, divergence_*) are now evaluated by the custom_build
    # fold — previously `crosses_above` was "out of scope" and raised. It now
    # maps to the ±1 cross semantics; on `sma` (whose values are never ±1) the
    # block is all-False, but crucially it does NOT raise.
    closes = _synthetic_close_matrix()
    engine = BacktestEngine()
    rules = [StrategyRule(primitive_id="sma", operator="crosses_above")]
    block = engine._evaluate_custom_build_block(
        rules, closes, "SPY", _synthetic_ohlcv(closes))
    assert isinstance(block, pd.Series)
    assert not block.any()  # sma never equals +1


def test_no_threshold_treats_primitive_as_boolean() -> None:
    """Primitives like donchian_breakout return 0/1; in that case the
    rule's threshold is unnecessary — the primitive IS the signal."""
    closes = _synthetic_close_matrix(periods=100)
    engine = BacktestEngine()
    rules = [StrategyRule(primitive_id="donchian_breakout",
                          primitive_params={"period": 20})]
    result = engine._evaluate_custom_build_block(rules, closes, "SPY", _synthetic_ohlcv(closes))
    # Donchian returns 0/1; bool conversion keeps the breakout days True.
    assert result.dtype == bool
    # Some bars should be True (breakouts), some False.
    assert result.any()
    assert not result.all()


# ── REGRESSION: real OHLCV, never fabricated (2026-06-12) ────────────────────


def test_volume_primitive_uses_real_volume_not_fabricated() -> None:
    """The custom_build path used to synthesize `volume=1.0`, so
    `avg_dollar_volume` computed ~close-price (≈$100) and any
    `avg_dollar_volume > $5M` rule was ALWAYS FALSE — silently zeroing the
    backtest (the SATS/RKLB all-zero bug). With real volume threaded in,
    the rule reflects actual liquidity."""
    closes = _synthetic_close_matrix(periods=120)
    engine = BacktestEngine()
    rule = [StrategyRule(primitive_id="avg_dollar_volume", operator="gt",
                         threshold=5_000_000.0, primitive_params={"period": 21})]

    # Liquid: close ≈$100 × volume 1e6 ≈ $100M avg dollar volume ≫ $5M.
    liquid = _synthetic_ohlcv(closes, volume=1_000_000.0)
    result_liquid = engine._evaluate_custom_build_block(
        rule, closes, "SPY", liquid,
    )
    assert result_liquid.iloc[25:].any(), (
        "avg_dollar_volume should fire on a liquid name — all-False means "
        "volume is being fabricated again (the 2026-06-12 bug)"
    )

    # Illiquid: volume 10 → ≈$1k avg dollar volume ≪ $5M → never fires.
    illiquid = _synthetic_ohlcv(closes, volume=10.0)
    result_illiquid = engine._evaluate_custom_build_block(
        rule, closes, "SPY", illiquid,
    )
    assert not result_illiquid.any(), (
        "the rule must reflect REAL volume — a low-volume frame must never "
        "pass a $5M liquidity gate"
    )


def test_range_primitive_uses_real_high_low() -> None:
    """ATR needs high−low; the old fabrication set high=low=close → ATR≡0.
    With real high/low, ATR is positive after warmup."""
    closes = _synthetic_close_matrix(periods=80)
    engine = BacktestEngine()
    # ATR > 0 should be True for a name with a real intraday range.
    rule = [StrategyRule(primitive_id="atr", operator="gt", threshold=0.0,
                         primitive_params={"period": 14})]
    result = engine._evaluate_custom_build_block(
        rule, closes, "SPY", _synthetic_ohlcv(closes),
    )
    assert result.iloc[20:].any(), (
        "ATR should be > 0 with a real high/low range — all-False means "
        "high=low=close fabrication"
    )


def test_missing_ohlcv_refuses_to_fabricate() -> None:
    """No real OHLCV for the symbol → raise, never silently backtest on
    made-up bars."""
    closes = _synthetic_close_matrix(periods=60)
    engine = BacktestEngine()
    rule = [StrategyRule(primitive_id="avg_dollar_volume", operator="gt",
                         threshold=5_000_000.0)]
    with pytest.raises(ValueError, match="refusing to fabricate"):
        engine._evaluate_custom_build_block(rule, closes, "SPY", {})
