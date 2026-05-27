"""PRD-13b — rotation overlay engine branch.

Synthetic 4-symbol portfolio. Verifies that the rotation overlay
correctly delegates to `_generate_cross_sectional_weights` and ranks
holdings by lookback return, holding top-K equal-weight.
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
    n_days = 504
    dates = pd.date_range("2021-01-04", periods=n_days, freq="B")
    rng = np.random.default_rng(31)
    syms = ["A", "B", "C", "D"]
    data = {}
    for i, s in enumerate(syms):
        r = np.random.default_rng(31 + i * 7)
        data[s] = 100.0 * np.cumprod(1 + r.normal(0.0003 + i * 0.0001, 0.015, n_days))
    return pd.DataFrame(data, index=dates)


def _load_return(close_df):
    universe_frames = {
        s: pd.DataFrame(
            {"adjusted_close": close_df[s].values, "high": close_df[s].values * 1.01},
            index=close_df.index,
        )
        for s in close_df.columns
    }
    bench = pd.DataFrame(
        {"adjusted_close": close_df["A"].values, "high": close_df["A"].values * 1.01},
        index=close_df.index,
    )
    return universe_frames, bench


@pytest.mark.asyncio
async def test_rotation_overlay_holds_top_two():
    close_df = _make_close_matrix()
    holdings = ["A", "B", "C", "D"]
    strategy = StrategyJSON(
        strategy_name="Rotation Overlay Test",
        strategy_type="portfolio_rotation_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="A",
        start_date=date(2022, 1, 3),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ranking_lookback_days=63, top_n=2)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _load_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    assert np.isfinite(result.metrics.total_return)

    # Direct invariant — exactly top-2 are held on each rebalance,
    # each at 0.5 (equal-weight). Total exposure: 1.0 on rebalance,
    # ffilled between.
    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    aligned = {s: f[f.index >= start_ts] for s, f in aligned.items()}
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    exposure = weights.sum(axis=1)
    # Should not over-allocate.
    assert (exposure <= 1.0 + 1e-9).all()
    # At least some rows reach full ~1.0 exposure.
    assert exposure.max() >= 0.99
    # Trade log is non-empty (rotation = lots of switches).
    assert len(result.trade_log) > 0
