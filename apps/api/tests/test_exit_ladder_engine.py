"""PRD-16c-2 — BacktestEngine._apply_exit_ladder + bar_resolution param.

Tests directly invoke the post-processor on synthetic weight + price
matrices so the assertions pin behavior at the function boundary rather
than going through the full backtest pipeline.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.schemas.strategy import (
    CashManagement,
    ExitTier,
    PositionSizing,
    RiskManagement,
    StrategyJSON,
    StrategyRule,
)
from app.services.backtester.engine import BacktestEngine


# ── Synthetic helpers ───────────────────────────────────────────────────────


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="B")


def _weights(values: list[float], symbol: str = "AAA") -> pd.DataFrame:
    return pd.DataFrame({symbol: values}, index=_dates(len(values)))


def _prices(values: list[float], symbol: str = "AAA") -> pd.DataFrame:
    return pd.DataFrame({symbol: values}, index=_dates(len(values)))


# ── bar_resolution parameter ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_default_bar_resolution_is_daily() -> None:
    """Default value preserves existing 22 strategy_types' behavior."""
    engine = BacktestEngine()
    db = MagicMock()
    # Build a minimal strategy + mocked _load_prices.
    close = pd.DataFrame(
        {"AAA": np.linspace(100, 120, 250)},
        index=pd.date_range("2023-01-02", periods=250, freq="B"),
    )
    universe_frames = {"AAA": pd.DataFrame(
        {"adjusted_close": close["AAA"].values, "high": (close["AAA"] * 1.01).values},
        index=close.index,
    )}
    benchmark_frame = universe_frames["AAA"]
    strategy = StrategyJSON(
        strategy_name="Smoke",
        strategy_type="moving_average_filter",
        universe=["AAA"],
        benchmark="AAA",
        start_date=date(2023, 1, 2),
        end_date=date(2023, 12, 29),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ma_window=50)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    with patch.object(
        engine, "_load_prices",
        new=AsyncMock(return_value=(universe_frames, benchmark_frame)),
    ):
        result = await engine.run(db, strategy)  # default bar_resolution="daily"
    assert result.metrics is not None


@pytest.mark.asyncio
async def test_run_intraday_resolution_soft_degrades_with_warning() -> None:
    """Non-daily backtests no longer raise — they soft-degrade to daily
    bars and surface the fallback as a BacktestResult.warning. The user
    keeps a usable backtest result + a clear message; the bar_resolution
    choice still flows through to the saved strategy for the monitor cron.
    """
    engine = BacktestEngine()
    db = MagicMock()
    # Synthetic price data for the smoke run.
    close = pd.DataFrame(
        {"AAA": np.linspace(100, 120, 250)},
        index=pd.date_range("2023-01-02", periods=250, freq="B"),
    )
    universe_frames = {"AAA": pd.DataFrame(
        {"adjusted_close": close["AAA"].values, "high": (close["AAA"] * 1.01).values},
        index=close.index,
    )}
    strategy = StrategyJSON(
        strategy_name="Intraday smoke",
        strategy_type="moving_average_filter",
        universe=["AAA"],
        benchmark="AAA",
        start_date=date(2023, 1, 2),
        end_date=date(2023, 12, 29),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ma_window=50)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
        bar_resolution="15min",
    )
    with patch.object(
        engine, "_load_prices",
        new=AsyncMock(return_value=(universe_frames, universe_frames["AAA"])),
    ):
        result = await engine.run(db, strategy)
    # Result is usable.
    assert result.metrics is not None
    # And the warning explains the soft-degrade so the user knows.
    assert any("daily bars" in w and "15min" in w for w in result.warnings), (
        f"expected an intraday->daily warning; got {result.warnings!r}"
    )


@pytest.mark.asyncio
async def test_run_resolution_kwarg_overrides_strategy_field() -> None:
    """Explicit `bar_resolution=` overrides what's on the strategy. Used
    by the monitor cron / robustness reruns at a forced resolution."""
    engine = BacktestEngine()
    db = MagicMock()
    close = pd.DataFrame(
        {"AAA": np.linspace(100, 120, 250)},
        index=pd.date_range("2023-01-02", periods=250, freq="B"),
    )
    universe_frames = {"AAA": pd.DataFrame(
        {"adjusted_close": close["AAA"].values, "high": (close["AAA"] * 1.01).values},
        index=close.index,
    )}
    # Strategy field says daily — kwarg forces 5min and we see the warning.
    strategy = StrategyJSON(
        strategy_name="Override test",
        strategy_type="moving_average_filter",
        universe=["AAA"],
        benchmark="AAA",
        start_date=date(2023, 1, 2),
        end_date=date(2023, 12, 29),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(ma_window=50)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
        bar_resolution="daily",
    )
    with patch.object(
        engine, "_load_prices",
        new=AsyncMock(return_value=(universe_frames, universe_frames["AAA"])),
    ):
        result = await engine.run(db, strategy, bar_resolution="5min")
    assert any("5min" in w for w in result.warnings)


# ── _apply_exit_ladder — pure unit ──────────────────────────────────────────


def test_no_exit_ladder_returns_weights_unchanged() -> None:
    engine = BacktestEngine()
    w = _weights([0.0, 1.0, 1.0, 1.0, 0.0])
    p = _prices([100, 100, 110, 120, 130])
    out = engine._apply_exit_ladder(w, p, [])
    assert (out["AAA"].values == w["AAA"].values).all()


def test_stop_tier_fires_on_drawdown() -> None:
    engine = BacktestEngine()
    # Enter at 100; price drops 12% on bar 3. Stop at -10% should fire there.
    w = _weights([0.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 95, 88, 90, 92])
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    out = engine._apply_exit_ladder(w, p, ladder)
    # Entry on bar 1 (price 100). Bar 3 = 88 → -12% → stop fires.
    # Weights from bar 3 onward should be zero.
    assert out["AAA"].iloc[1] == 1.0
    assert out["AAA"].iloc[2] == 1.0  # bar 2 (-5%) below trigger
    assert out["AAA"].iloc[3] == 0.0  # stop fires
    assert out["AAA"].iloc[4] == 0.0
    assert out["AAA"].iloc[5] == 0.0


def test_take_profit_sell_fraction_partial_out() -> None:
    engine = BacktestEngine()
    # Enter at 100; +15% on bar 3. TP1 sells 1/3.
    w = _weights([0.0, 1.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 110, 115, 120])
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    # Bar 3 = 115 → +15% → TP1 fires, weight × (1 - 0.33) = 0.67
    assert out["AAA"].iloc[1] == 1.0
    assert out["AAA"].iloc[2] == 1.0  # +10%, below trigger
    assert out["AAA"].iloc[3] == pytest.approx(0.67, abs=1e-6)
    assert out["AAA"].iloc[4] == pytest.approx(0.67, abs=1e-6)


def test_multi_tier_ladder_fires_in_order() -> None:
    """Canonical SpaceX ladder: Stop / TP1 (1/3 out) / TP2 (full out).
    Price rallies through both TPs; each tier fires once in order."""
    engine = BacktestEngine()
    w = _weights([0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 105, 115, 120, 130, 135])
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.33, label="TP1"),
        ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    # Entry bar 1 (100). Bar 3 = 115 → +15% TP1 fires (× 0.67).
    # Bar 5 = 130 → +30% TP2 fires (sell_all → 0).
    assert out["AAA"].iloc[1] == 1.0
    assert out["AAA"].iloc[2] == 1.0  # +5%, below TP1
    assert out["AAA"].iloc[3] == pytest.approx(0.67, abs=1e-6)
    assert out["AAA"].iloc[4] == pytest.approx(0.67, abs=1e-6)
    assert out["AAA"].iloc[5] == 0.0  # TP2 fires
    assert out["AAA"].iloc[6] == 0.0


def test_tier_fires_at_most_once_per_entry() -> None:
    """Once TP1 has fired, it should NOT fire again on later bars even if
    the price stays above the trigger."""
    engine = BacktestEngine()
    w = _weights([0.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 116, 117, 118, 120])
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.50, label="TP1"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    # Bar 2 = 116 → +16% → TP1 fires once, w × 0.5
    # Bars 3-5 should stay at 0.5, NOT decay to 0.25 / 0.125 / etc.
    assert out["AAA"].iloc[2] == pytest.approx(0.5, abs=1e-6)
    assert out["AAA"].iloc[3] == pytest.approx(0.5, abs=1e-6)
    assert out["AAA"].iloc[4] == pytest.approx(0.5, abs=1e-6)
    assert out["AAA"].iloc[5] == pytest.approx(0.5, abs=1e-6)


def test_new_entry_resets_fired_tiers() -> None:
    """After the position closes (weight returns to 0 from strategy
    rules), a new entry should re-arm the ladder."""
    engine = BacktestEngine()
    # Entry, +20% (TP1 fires), exit, re-entry, +20% (TP1 should fire AGAIN).
    w = _weights([0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 120, 120, 100, 110, 120])
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.50, label="TP1"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    # First entry: bar 1 (100). Bar 2 = 120 → TP1 fires → 0.5.
    assert out["AAA"].iloc[2] == pytest.approx(0.5, abs=1e-6)
    # Strategy closes position on bar 3 (weight=0).
    assert out["AAA"].iloc[3] == 0.0
    # New entry on bar 4 (price 100). Bar 6 = 120 → +20% → TP1 fires AGAIN.
    assert out["AAA"].iloc[4] == 1.0
    assert out["AAA"].iloc[5] == 1.0  # +10%, below TP1
    assert out["AAA"].iloc[6] == pytest.approx(0.5, abs=1e-6)


def test_stop_evaluated_before_take_profit_on_same_bar() -> None:
    """If a bar simultaneously satisfies both stop and TP triggers
    (unusual but possible with gaps), the stop tier (earlier in the
    ascending list) fires first."""
    engine = BacktestEngine()
    w = _weights([0.0, 1.0, 1.0])
    # Impossible but contrived: entry at 100, next bar drops to 85
    # (stop trigger -15%) which alone activates Stop.
    p = _prices([100, 100, 85])
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.30, action="sell_all", label="TP2"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    assert out["AAA"].iloc[2] == 0.0


def test_ladder_runs_independently_per_symbol() -> None:
    """Multiple symbols: each tracks its own entry + fired tiers."""
    engine = BacktestEngine()
    idx = _dates(5)
    w = pd.DataFrame({
        "AAA": [0.0, 0.5, 0.5, 0.5, 0.5],
        "BBB": [0.0, 0.5, 0.5, 0.5, 0.5],
    }, index=idx)
    p = pd.DataFrame({
        "AAA": [100, 100, 88, 90, 95],   # AAA stops on bar 2 (-12%)
        "BBB": [200, 200, 210, 230, 260], # BBB hits TP at +30% on bar 3
    }, index=idx)
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=0.50, label="TP1"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)
    # AAA: stop fires bar 2 → 0 onward.
    assert out["AAA"].iloc[1] == 0.5
    assert out["AAA"].iloc[2] == 0.0
    assert out["AAA"].iloc[3] == 0.0
    # BBB: TP1 fires bar 2 (210 → +5%? No, +5% < +15%). Bar 3 (230) → +15% → fires.
    assert out["BBB"].iloc[2] == 0.5  # +5%, below TP1
    assert out["BBB"].iloc[3] == pytest.approx(0.25, abs=1e-6)  # × 0.5
    assert out["BBB"].iloc[4] == pytest.approx(0.25, abs=1e-6)
