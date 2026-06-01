"""PRD-13c — dual momentum overlay engine branch.

Synthetic 5-symbol portfolio. Three trend up (positive absolute return),
two trend down. The absolute momentum filter zeroes out down-trending
names even when they rank well on relative momentum.
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


def _make_close_matrix() -> pd.DataFrame:
    """SYM1, SYM2, SYM3: drift up; SYM4, SYM5: drift down."""
    n_days = 756  # ~3 years to give 252-day lookback enough warmup
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    rng1 = np.random.default_rng(41)
    sym1 = 100.0 * np.cumprod(1 + rng1.normal(0.0008, 0.012, n_days))
    rng2 = np.random.default_rng(42)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(0.0006, 0.012, n_days))
    rng3 = np.random.default_rng(43)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(0.0007, 0.013, n_days))
    rng4 = np.random.default_rng(44)
    sym4 = 100.0 * np.cumprod(1 + rng4.normal(-0.0006, 0.014, n_days))
    rng5 = np.random.default_rng(45)
    sym5 = 100.0 * np.cumprod(1 + rng5.normal(-0.0004, 0.013, n_days))
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
async def test_dual_momentum_keeps_up_trending_names():
    """Only holdings with positive absolute return should be allocated."""
    close_df = _make_close_matrix()
    holdings = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
    strategy = StrategyJSON(
        strategy_name="Dual Momentum Test",
        strategy_type="portfolio_dual_momentum_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 6, 1),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ranking_lookback_days=126, lookback_days=252, top_n=3)],
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

    # Down-trending names should be in cash more often than up-trending ones.
    sym1_active = (weights["SYM1"] > 0).mean()
    sym4_active = (weights["SYM4"] > 0).mean()
    assert sym1_active > sym4_active, (
        f"Expected SYM1 active > SYM4 active "
        f"(SYM1={sym1_active:.2f}, SYM4={sym4_active:.2f})"
    )


@pytest.mark.asyncio
async def test_dual_momentum_all_down_portfolio_goes_to_cash():
    """When all holdings have negative absolute returns → mostly cash."""
    n_days = 756
    dates = pd.date_range("2020-01-02", periods=n_days, freq="B")
    rng = np.random.default_rng(99)
    sym1 = 100.0 * np.cumprod(1 + rng.normal(-0.001, 0.015, n_days))
    rng2 = np.random.default_rng(98)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(-0.0008, 0.014, n_days))
    rng3 = np.random.default_rng(97)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(-0.0012, 0.016, n_days))
    close_df = pd.DataFrame(
        {"SYM1": sym1, "SYM2": sym2, "SYM3": sym3}, index=dates
    )

    holdings = ["SYM1", "SYM2", "SYM3"]
    strategy = StrategyJSON(
        strategy_name="Dual Momentum Bear",
        strategy_type="portfolio_dual_momentum_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2021, 7, 1),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ranking_lookback_days=126, lookback_days=252, top_n=3)],
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

    avg_exposure = weights.sum(axis=1).mean()
    assert avg_exposure < 0.3, (
        f"Expected mostly cash when all holdings are falling; "
        f"avg exposure={avg_exposure:.2f}"
    )
