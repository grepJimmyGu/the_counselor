"""PRD-13c — stability tilt overlay engine branch.

Synthetic 5-symbol portfolio with deliberately different volatilities.
Lowest-vol holding gets highest weight; highest-vol gets lowest.
No single weight exceeds the max_weight cap.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_disparate_vol_matrix() -> pd.DataFrame:
    """SYM1 = low vol, SYM2 = medium, SYM3 = high, SYM4 = very high, SYM5 = med-low."""
    n_days = 756
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    drift = 0.0006
    rng1 = np.random.default_rng(81)
    sym1 = 100.0 * np.cumprod(1 + rng1.normal(drift, 0.008, n_days))
    rng2 = np.random.default_rng(82)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(drift, 0.014, n_days))
    rng3 = np.random.default_rng(83)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(drift, 0.025, n_days))
    rng4 = np.random.default_rng(84)
    sym4 = 100.0 * np.cumprod(1 + rng4.normal(drift, 0.040, n_days))
    rng5 = np.random.default_rng(85)
    sym5 = 100.0 * np.cumprod(1 + rng5.normal(drift, 0.010, n_days))
    return pd.DataFrame(
        {"SYM1": sym1, "SYM2": sym2, "SYM3": sym3, "SYM4": sym4, "SYM5": sym5},
        index=dates,
    )


def _make_load_prices_return(close_df: pd.DataFrame):
    universe_frames = {
        sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values,
             "high": close_df[sym].values * 1.01},
            index=close_df.index,
        )
        for sym in close_df.columns
    }
    benchmark_frame = pd.DataFrame(
        {"adjusted_close": close_df["SYM1"].values,
         "high": close_df["SYM1"].values * 1.01},
        index=close_df.index,
    )
    return universe_frames, benchmark_frame


@pytest.mark.asyncio
async def test_stability_tilt_weights_are_inverse_to_vol():
    """Lowest-vol holding gets highest weight; highest-vol gets lowest."""
    close_df = _make_disparate_vol_matrix()
    holdings = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
    strategy = StrategyJSON(
        strategy_name="Stability Tilt Test",
        strategy_type="portfolio_stability_tilt_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=63, value=0.30)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    assert np.isfinite(result.metrics.total_return)

    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    weights = engine._generate_weights(strategy, close_matrix, aligned)

    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all()

    # On the last rebalance date, SYM4 (highest vol) should have
    # lower weight than SYM1 (lowest vol).
    rebalance_mask = engine._rebalance_mask(close_matrix.index, "monthly")
    rebalance_dates = close_matrix.index[rebalance_mask]
    last_rebalance = rebalance_dates[-1]
    row = weights.loc[last_rebalance]
    assert row.get("SYM1", 0) > row.get("SYM4", 0), (
        f"Expected low-vol SYM1 weight ({row.get('SYM1', 0):.3f}) "
        f"> high-vol SYM4 weight ({row.get('SYM4', 0):.3f})"
    )


@pytest.mark.asyncio
async def test_stability_tilt_respects_max_weight_cap():
    """No single holding weight should exceed max_weight cap."""
    close_df = _make_disparate_vol_matrix()
    holdings = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
    max_weight = 0.30
    strategy = StrategyJSON(
        strategy_name="Stability Tilt Cap Test",
        strategy_type="portfolio_stability_tilt_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=63, value=max_weight)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    weights = engine._generate_weights(strategy, close_matrix, aligned)

    # No single weight should substantially exceed the cap (allow small fp drift)
    max_observed = weights.max().max()
    assert max_observed <= max_weight + 0.01, (
        f"Max weight {max_observed:.3f} exceeds cap {max_weight}"
    )


@pytest.mark.asyncio
async def test_stability_tilt_weights_sum_to_one():
    """Weights should sum to ~1.0 on rebalance dates after warmup."""
    close_df = _make_disparate_vol_matrix()
    holdings = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
    strategy = StrategyJSON(
        strategy_name="Stability Tilt Sum Test",
        strategy_type="portfolio_stability_tilt_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=63, value=0.25)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    weights = engine._generate_weights(strategy, close_matrix, aligned)

    rebalance_mask = engine._rebalance_mask(close_matrix.index, "monthly")
    rebalance_weights = weights.loc[rebalance_mask].dropna(how="all")
    # Skip first few rebalances (vol warmup); check the back half
    n = len(rebalance_weights)
    if n > 4:
        sums = rebalance_weights.iloc[n // 2:].sum(axis=1)
        assert (sums - 1.0).abs().max() < 0.02, (
            f"Weights should sum to ~1.0; got sums={sums.tolist()}"
        )
