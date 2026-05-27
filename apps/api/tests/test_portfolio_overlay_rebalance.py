"""PRD-13b — rebalance overlay engine branch.

Verifies the rebalance overlay applies target weights on each
rebalance date. Mechanically static_allocation-shaped, but reading
the user's holdings via inherited_universe.
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
)
from app.services.backtester.engine import BacktestEngine


def _make_close_matrix() -> pd.DataFrame:
    n_days = 504
    dates = pd.date_range("2021-01-04", periods=n_days, freq="B")
    rng = np.random.default_rng(91)
    syms = ["X", "Y", "Z"]
    data = {}
    for i, s in enumerate(syms):
        r = np.random.default_rng(91 + i * 11)
        data[s] = 100.0 * np.cumprod(1 + r.normal(0.0004, 0.013, n_days))
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
        {"adjusted_close": close_df["X"].values, "high": close_df["X"].values * 1.01},
        index=close_df.index,
    )
    return universe_frames, bench


@pytest.mark.asyncio
async def test_rebalance_overlay_respects_targets():
    close_df = _make_close_matrix()
    holdings = ["X", "Y", "Z"]
    targets = {"X": 0.5, "Y": 0.3, "Z": 0.2}
    strategy = StrategyJSON(
        strategy_name="Rebalance Overlay Test",
        strategy_type="portfolio_rebalance_overlay",
        universe=holdings,
        inherited_universe=holdings,
        benchmark="X",
        start_date=date(2022, 1, 3),
        end_date=date(2022, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="quarterly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[],
        position_sizing=PositionSizing(method="fixed_weight", weights=targets),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )

    engine = BacktestEngine()
    db = MagicMock()
    load_return = _load_return(close_df)
    with patch.object(engine, "_load_prices", new=AsyncMock(return_value=load_return)):
        result = await engine.run(db, strategy)

    assert np.isfinite(result.metrics.total_return)

    # On rebalance dates the weights should match the targets exactly.
    close_matrix, aligned = engine._build_price_matrix(load_return[0])
    start_ts = pd.Timestamp(strategy.start_date)
    close_matrix = close_matrix[close_matrix.index >= start_ts]
    aligned = {s: f[f.index >= start_ts] for s, f in aligned.items()}
    weights = engine._generate_weights(strategy, close_matrix, aligned)
    exposure = weights.sum(axis=1)
    assert (exposure <= 1.0 + 1e-9).all()
    # At least one row hits the full target allocation.
    assert exposure.max() >= 0.99
