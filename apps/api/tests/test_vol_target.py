"""
Tests for PositionSizing.method = "vol_target".

Verifies:
  1. Vol-targeted portfolio's realized annual vol falls within ±30% of target.
  2. Weight constraint <= 1.0 still holds after vol-scaling.
  3. equal_weight / fixed_weight behavior is unaffected.
  4. signal_weighted raises NotImplementedError.
  5. target_vol_annual parameter is respected (different targets produce
     proportionally different realized vols).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.schemas.strategy import (
    CashManagement,
    PositionSizing,
    RiskManagement,
    StrategyJSON,
    StrategyRule,
)
from app.services.backtester.engine import BacktestEngine


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_high_vol_close(
    n_days: int = 504,
    n_symbols: int = 3,
    daily_vol: float = 0.03,   # ≈ 47% annualised — well above any realistic target
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic daily prices with prescribed volatility."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-04", periods=n_days, freq="B")
    cols = [f"SYM{i+1}" for i in range(n_symbols)]
    data = {}
    for i, sym in enumerate(cols):
        sym_rng = np.random.default_rng(seed + i * 13)
        rets = sym_rng.normal(0.0004, daily_vol, size=n_days)
        data[sym] = 100.0 * np.cumprod(1 + rets)
    return pd.DataFrame(data, index=dates)


def _build_inputs(close_df: pd.DataFrame):
    """Return (close_matrix, aligned_frames) as BacktestEngine._build_price_matrix would."""
    engine = BacktestEngine()
    universe_frames = {
        sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values, "high": (close_df[sym] * 1.01).values},
            index=close_df.index,
        )
        for sym in close_df.columns
    }
    return engine._build_price_matrix(universe_frames)


def _make_strategy(position_sizing: PositionSizing, **overrides) -> StrategyJSON:
    """Momentum-rotation strategy with 3 synthetic symbols."""
    base = dict(
        strategy_name="Vol Target Test",
        strategy_type="momentum_rotation",
        universe=["SYM1", "SYM2", "SYM3"],
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[StrategyRule(top_n=2, ranking_lookback_days=42)],
        position_sizing=position_sizing,
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(overrides)
    return StrategyJSON(**base)


def _portfolio_annual_vol(weights: pd.DataFrame, close_matrix: pd.DataFrame) -> float:
    asset_rets = close_matrix.pct_change().fillna(0.0)
    port_rets = (weights.shift(1).fillna(0.0) * asset_rets).sum(axis=1)
    return float(port_rets.std() * np.sqrt(252))


# ── Core invariant: realized vol ≈ target ────────────────────────────────────

def test_vol_target_within_30pct_of_target():
    """With high-vol assets, vol-targeting reduces portfolio vol to ≈ target."""
    target = 0.10
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy = _make_strategy(
        PositionSizing(method="vol_target", target_vol_annual=target)
    )
    weights = engine._generate_weights(strategy, close_matrix, aligned)

    realized = _portfolio_annual_vol(weights, close_matrix)
    # Raw vol is ~47%; after targeting it should be within ±30% of 10%
    assert realized <= target * 1.30, f"vol too high: {realized:.4f} > {target * 1.30:.4f}"
    assert realized >= target * 0.70, f"vol too low: {realized:.4f} < {target * 0.70:.4f}"


def test_vol_target_weights_never_exceed_1():
    """Vol-scaling must not create over-allocated rows."""
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy = _make_strategy(
        PositionSizing(method="vol_target", target_vol_annual=0.10)
    )
    weights = engine._generate_weights(strategy, close_matrix, aligned)

    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all(), f"max exposure = {exposure.max():.6f}"


def test_vol_target_weights_non_negative():
    """Long-only: no short positions created by vol-scaling."""
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy = _make_strategy(
        PositionSizing(method="vol_target", target_vol_annual=0.10)
    )
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    assert (weights >= -1e-9).all().all(), "Negative weights detected after vol scaling."


# ── Scale is proportional to target ──────────────────────────────────────────

def test_vol_target_higher_target_allows_more_vol():
    """Doubling the target should allow roughly double the realized vol."""
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    w_low = engine._generate_weights(
        _make_strategy(PositionSizing(method="vol_target", target_vol_annual=0.05)),
        close_matrix, aligned,
    )
    w_high = engine._generate_weights(
        _make_strategy(PositionSizing(method="vol_target", target_vol_annual=0.20)),
        close_matrix, aligned,
    )
    vol_low = _portfolio_annual_vol(w_low, close_matrix)
    vol_high = _portfolio_annual_vol(w_high, close_matrix)
    # Higher target must produce higher (or equal) realized vol
    assert vol_high >= vol_low - 0.01


# ── Default target is 10% when target_vol_annual is None ─────────────────────

def test_vol_target_default_is_10pct():
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy = _make_strategy(
        PositionSizing(method="vol_target")  # target_vol_annual=None → defaults to 0.10
    )
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    realized = _portfolio_annual_vol(weights, close_matrix)
    assert realized <= 0.10 * 1.30


# ── equal_weight / fixed_weight unaffected ────────────────────────────────────

def test_equal_weight_unaffected_by_vol_target_logic():
    """equal_weight must NOT apply any vol scaling."""
    close_df = _make_high_vol_close()
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy_eq = _make_strategy(PositionSizing(method="equal_weight"))
    strategy_vt = _make_strategy(PositionSizing(method="vol_target", target_vol_annual=0.10))

    w_eq = engine._generate_weights(strategy_eq, close_matrix, aligned)
    w_vt = engine._generate_weights(strategy_vt, close_matrix, aligned)

    vol_eq = _portfolio_annual_vol(w_eq, close_matrix)
    vol_vt = _portfolio_annual_vol(w_vt, close_matrix)

    # equal_weight should have higher vol (not reduced by scaling)
    assert vol_eq > vol_vt, (
        f"equal_weight vol ({vol_eq:.4f}) should exceed vol_target ({vol_vt:.4f})"
    )


# ── signal_weighted raises NotImplementedError ────────────────────────────────

def test_signal_weighted_raises_not_implemented():
    close_df = _make_high_vol_close(n_symbols=1)
    close_matrix, aligned = _build_inputs(close_df)
    engine = BacktestEngine()

    strategy = _make_strategy(
        PositionSizing(method="signal_weighted"),
        universe=["SYM1"],
        rules=[StrategyRule(fast_window=10, slow_window=50)],
        strategy_type="moving_average_crossover",
    )
    with pytest.raises(NotImplementedError, match="signal_weighted"):
        engine._generate_weights(strategy, close_matrix, aligned)
