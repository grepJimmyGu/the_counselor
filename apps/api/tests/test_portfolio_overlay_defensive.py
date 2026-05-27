"""PRD-13b — defensive overlay engine branch.

Synthetic 3-symbol portfolio. Two of the three are in clear uptrends
(close > MA almost always); one is in a downtrend (close < MA most of
the time). Defensive overlay should keep the trending names allocated
and zero out the downtrending one.
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
    """SYM1, SYM2: drift up; SYM3: drift down. Daily bars over ~2y."""
    n_days = 504
    dates = pd.date_range("2021-01-04", periods=n_days, freq="B")
    rng = np.random.default_rng(13)
    sym1 = 100.0 * np.cumprod(1 + rng.normal(0.0008, 0.012, n_days))
    rng2 = np.random.default_rng(14)
    sym2 = 100.0 * np.cumprod(1 + rng2.normal(0.0006, 0.012, n_days))
    rng3 = np.random.default_rng(15)
    sym3 = 100.0 * np.cumprod(1 + rng3.normal(-0.0006, 0.014, n_days))
    return pd.DataFrame({"SYM1": sym1, "SYM2": sym2, "SYM3": sym3}, index=dates)


def _make_load_prices_return(close_df: pd.DataFrame):
    universe_frames = {
        sym: pd.DataFrame(
            {"adjusted_close": close_df[sym].values, "high": close_df[sym].values * 1.01},
            index=close_df.index,
        )
        for sym in close_df.columns
    }
    benchmark_frame = pd.DataFrame(
        {"adjusted_close": close_df["SYM1"].values, "high": close_df["SYM1"].values * 1.01},
        index=close_df.index,
    )
    return universe_frames, benchmark_frame


@pytest.mark.asyncio
async def test_defensive_overlay_runs_and_keeps_trending_names():
    close_df = _make_close_matrix()
    holdings = ["SYM1", "SYM2", "SYM3"]
    strategy = StrategyJSON(
        strategy_name="Defensive Overlay Test",
        strategy_type="portfolio_defensive_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="SYM1",
        start_date=date(2022, 1, 3),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=100)],
        position_sizing=PositionSizing(
            method="fixed_weight",
            weights={"SYM1": 0.4, "SYM2": 0.4, "SYM3": 0.2},
        ),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _make_load_prices_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    # Result is a valid BacktestResult; total return is finite.
    assert np.isfinite(result.metrics.total_return)
    # Exposure never exceeds 1.0.
    # Reconstruct close_matrix via _build_price_matrix then check weights.
    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    aligned = {s: f[f.index >= start_ts] for s, f in aligned.items()}
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all()

    # The downtrending name (SYM3) should be in cash MORE often than the
    # uptrending ones. Compare time-in-position across symbols.
    sym1_active = (weights["SYM1"] > 0).mean()
    sym3_active = (weights["SYM3"] > 0).mean()
    assert sym1_active > sym3_active, (
        f"Expected SYM1 active > SYM3 active "
        f"(SYM1={sym1_active:.2f}, SYM3={sym3_active:.2f})"
    )
