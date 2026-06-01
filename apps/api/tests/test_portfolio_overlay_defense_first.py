"""PRD-13c — defense-first overlay engine branch.

Breadth (fraction of holdings above MA) determines exposure. When most
holdings are above trend → full exposure. When most are below → scaled down.
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


def _make_mixed_close_matrix() -> pd.DataFrame:
    """SYM1, SYM2 drift up; SYM3, SYM4 drift down. Breadth hovers ~50%."""
    n_days = 756
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    rng1 = np.random.default_rng(61)
    sym1 = 100.0 * np.cumprod(1 + rng1.normal(0.0010, 0.012, n_days))
    rng2 = np.random.default_rng(62)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(0.0008, 0.012, n_days))
    rng3 = np.random.default_rng(63)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(-0.0008, 0.014, n_days))
    rng4 = np.random.default_rng(64)
    sym4 = 100.0 * np.cumprod(1 + rng4.normal(-0.0006, 0.013, n_days))
    return pd.DataFrame(
        {"SYM1": sym1, "SYM2": sym2, "SYM3": sym3, "SYM4": sym4}, index=dates
    )


def _make_all_up_close_matrix() -> pd.DataFrame:
    """All 3 holdings drift up strongly — breadth stays high."""
    n_days = 756
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    rng1 = np.random.default_rng(71)
    sym1 = 100.0 * np.cumprod(1 + rng1.normal(0.0010, 0.012, n_days))
    rng2 = np.random.default_rng(72)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(0.0009, 0.012, n_days))
    rng3 = np.random.default_rng(73)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(0.0011, 0.013, n_days))
    return pd.DataFrame(
        {"SYM1": sym1, "SYM2": sym2, "SYM3": sym3}, index=dates
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
async def test_defense_first_scales_down_when_breadth_weak():
    """When breadth < 0.5, exposure should be scaled to scale_down factor."""
    close_df = _make_mixed_close_matrix()
    holdings = ["SYM1", "SYM2", "SYM3", "SYM4"]
    scale_down = 0.5
    strategy = StrategyJSON(
        strategy_name="Defense-First Test",
        strategy_type="portfolio_defense_first_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=100, threshold=0.5, value=scale_down)],
        position_sizing=PositionSizing(
            method="fixed_weight",
            weights={"SYM1": 0.25, "SYM2": 0.25, "SYM3": 0.25, "SYM4": 0.25},
        ),
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

    # After warmup, some rows should show scaled exposure (since SYM3/SYM4 drift down)
    warmup_cutoff = close_matrix.index[120]
    late_exposure = exposure[exposure.index >= warmup_cutoff]
    low_exposure_rows = (late_exposure < 0.99).sum()
    assert low_exposure_rows > 0, (
        "Expected some rows with scaled exposure when breadth drops below 0.5"
    )


@pytest.mark.asyncio
async def test_defense_first_full_exposure_when_breadth_healthy():
    """When breadth >= threshold, portfolio stays at full exposure."""
    close_df = _make_all_up_close_matrix()
    holdings = ["SYM1", "SYM2", "SYM3"]
    strategy = StrategyJSON(
        strategy_name="Defense-First Healthy",
        strategy_type="portfolio_defense_first_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 1, 4),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=100, threshold=0.5, value=0.5)],
        position_sizing=PositionSizing(
            method="fixed_weight",
            weights={"SYM1": 1 / 3, "SYM2": 1 / 3, "SYM3": 1 / 3},
        ),
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

    exposure = weights.sum(axis=1)

    # After warmup, exposure should be near 1.0 since all names trend up
    rebalance_dates = close_matrix.index[
        engine._rebalance_mask(close_matrix.index, "monthly")
    ]
    warmup_cutoff = close_matrix.index[150]  # well past 100-day MA warmup
    late_dates = [d for d in rebalance_dates if d >= warmup_cutoff]
    late_exposures = exposure.loc[late_dates]
    avg_late_exposure = late_exposures.mean()
    assert avg_late_exposure > 0.90, (
        f"Expected near-full exposure when breadth is healthy; "
        f"avg late exposure={avg_late_exposure:.3f}"
    )
