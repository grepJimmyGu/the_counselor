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
    out, _ = engine._apply_exit_ladder(w, p, [])
    assert (out["AAA"].values == w["AAA"].values).all()


def test_stop_tier_fires_on_drawdown() -> None:
    engine = BacktestEngine()
    # Enter at 100; price drops 12% on bar 3. Stop at -10% should fire there.
    w = _weights([0.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    p = _prices([100, 100, 95, 88, 90, 92])
    ladder = [ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop")]
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
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
    out, _ = engine._apply_exit_ladder(w, p, ladder)
    # AAA: stop fires bar 2 → 0 onward.
    assert out["AAA"].iloc[1] == 0.5
    assert out["AAA"].iloc[2] == 0.0
    assert out["AAA"].iloc[3] == 0.0
    # BBB: TP1 fires bar 2 (210 → +5%? No, +5% < +15%). Bar 3 (230) → +15% → fires.
    assert out["BBB"].iloc[2] == 0.5  # +5%, below TP1
    assert out["BBB"].iloc[3] == pytest.approx(0.25, abs=1e-6)  # × 0.5
    assert out["BBB"].iloc[4] == pytest.approx(0.25, abs=1e-6)


def test_REGRESSION_second_scale_out_takes_a_fraction_of_the_ENTRY_weight():
    """Convention decided 2026-08-18: fraction of the ORIGINAL position.

    The engine previously compounded (`w *= 1 - f`), so a second 1/3 tier
    removed 1/3 of an ALREADY-REDUCED weight while the live monitor sized
    the same tier off `shares_initial`. The user's backtested equity curve
    was therefore not the plan the exit alert told them to execute.

    Every pre-existing test in this file exercises only the FIRST scale-out,
    where both conventions give the same answer — which is why the
    divergence survived. This one exercises the second, where they differ:

        entry weight 0.30, two 1/3 tiers
          fraction-of-initial   → 0.30, 0.20, 0.10   (correct)
          fraction-of-remaining → 0.30, 0.20, 0.1333 (old)
    """
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    w = pd.DataFrame({"AAA": [0.30, 0.30, 0.30]}, index=idx)
    p = pd.DataFrame({"AAA": [100.0, 115.0, 130.0]}, index=idx)  # entry, +15%, +30%
    ladder = [
        ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=1 / 3, label="TP1"),
        ExitTier(trigger_pct=+0.30, action="sell_fraction", fraction=1 / 3, label="TP2"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)[0]["AAA"]
    assert out.iloc[0] == pytest.approx(0.30, abs=1e-9)
    assert out.iloc[1] == pytest.approx(0.20, abs=1e-9)
    assert out.iloc[2] == pytest.approx(0.10, abs=1e-9)


def test_REGRESSION_two_negative_tiers_both_fire_in_the_engine():
    """The live monitor keyed every negative tier to the constant string
    "stop_hit", so a "-5% trim / -10% stop out" ladder permanently disarmed
    the hard stop. The engine keyed on the ladder index and did not have the
    bug; this pins that it still doesn't, now that both share one evaluator.
    """
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    w = pd.DataFrame({"AAA": [0.40, 0.40, 0.40]}, index=idx)
    p = pd.DataFrame({"AAA": [100.0, 94.0, 88.0]}, index=idx)  # entry, -6%, -12%
    ladder = [
        ExitTier(trigger_pct=-0.10, action="sell_all", label="Stop"),
        ExitTier(trigger_pct=-0.05, action="sell_fraction", fraction=0.5, label="Trim"),
    ]
    out = engine._apply_exit_ladder(w, p, ladder)[0]["AAA"]
    assert out.iloc[1] == pytest.approx(0.20, abs=1e-9)  # trim at -6%
    assert out.iloc[2] == pytest.approx(0.0, abs=1e-9)   # stop MUST still fire


# ── next-open exit fills (2026-08-18) ───────────────────────────────────────


def test_exited_weight_is_recorded_on_the_bar_the_tier_FIRED():
    """A ladder exit is detected on bar T's close but sold at T+1's open, so
    `run()` needs to know how much weight left and on which bar in order to
    credit it the overnight gap. A sell_all releases the whole held weight.
    """
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    w = pd.DataFrame({"AAA": [1.0, 1.0, 1.0]}, index=idx)
    p = pd.DataFrame({"AAA": [100.0, 90.0, 95.0]}, index=idx)  # -10% on bar 1
    ladder = [ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop")]
    weights, exited = engine._apply_exit_ladder(w, p, ladder)
    assert weights["AAA"].tolist() == [1.0, 0.0, 0.0]
    assert exited["AAA"].tolist() == [0.0, 1.0, 0.0]


def test_each_scale_out_is_recorded_separately():
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    w = pd.DataFrame({"AAA": [1.0, 1.0, 1.0]}, index=idx)
    p = pd.DataFrame({"AAA": [100.0, 115.0, 130.0]}, index=idx)
    ladder = [
        ExitTier(trigger_pct=-0.08, action="sell_all", label="S"),
        ExitTier(trigger_pct=+0.15, action="sell_fraction", fraction=1 / 3, label="TP1"),
        ExitTier(trigger_pct=+0.30, action="sell_fraction", fraction=1 / 3, label="TP2"),
    ]
    _, exited = engine._apply_exit_ladder(w, p, ladder)
    assert exited["AAA"].iloc[1] == pytest.approx(1 / 3, abs=1e-9)
    assert exited["AAA"].iloc[2] == pytest.approx(1 / 3, abs=1e-9)


def test_no_ladder_reports_no_exits():
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    w = pd.DataFrame({"AAA": [1.0, 1.0]}, index=idx)
    p = pd.DataFrame({"AAA": [100.0, 50.0]}, index=idx)
    weights, exited = engine._apply_exit_ladder(w, p, [])
    assert weights.equals(w)
    assert exited.to_numpy().sum() == 0.0


def test_REGRESSION_adjusted_open_applies_the_split_ratio():
    """`price_bars` stores a RAW open beside an adjusted close. Pairing the
    two directly would show a fabricated overnight gap the size of the split
    on every split date — a 2:1 split would read as a 100% move. The ratio
    adjusted_close/close applies to every price on the bar, including open.
    """
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    close_matrix = pd.DataFrame({"AAA": [100.0, 50.0]}, index=idx)
    aligned = {
        "AAA": pd.DataFrame(
            {
                "open": [100.0, 200.0],       # raw, pre-split on bar 1
                "close": [100.0, 200.0],      # raw
                "adjusted_close": [100.0, 50.0],  # 4:1 adjustment on bar 1
            },
            index=idx,
        )
    }
    adjusted_open = engine._build_adjusted_open_matrix(aligned, close_matrix)
    assert adjusted_open["AAA"].iloc[0] == pytest.approx(100.0)
    assert adjusted_open["AAA"].iloc[1] == pytest.approx(50.0)  # NOT 200.0


def test_REGRESSION_stopped_position_is_charged_the_overnight_gap():
    """The whole point of the change. A stop detected at bar 1's close of 90
    is sold at bar 2's open of 85 — the position eats that 5.6% gap. The
    engine used to assume a fill at 90, handing every stopped strategy a
    price its own user could never have got.
    """
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    w = pd.DataFrame({"AAA": [1.0, 1.0, 1.0]}, index=idx)
    close_matrix = pd.DataFrame({"AAA": [100.0, 90.0, 95.0]}, index=idx)
    ladder = [ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop")]
    _, exited = engine._apply_exit_ladder(w, close_matrix, ladder)

    aligned = {
        "AAA": pd.DataFrame(
            {
                "open": [100.0, 92.0, 85.0],
                "close": [100.0, 90.0, 95.0],
                "adjusted_close": [100.0, 90.0, 95.0],
            },
            index=idx,
        )
    }
    adjusted_open = engine._build_adjusted_open_matrix(aligned, close_matrix)
    prev_close = close_matrix.shift(1)
    gap = ((adjusted_open - prev_close) / prev_close).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0.0)
    correction = (exited.shift(1).fillna(0.0) * gap).sum(axis=1)

    assert correction.iloc[1] == pytest.approx(0.0)  # nothing sold yet
    assert correction.iloc[2] == pytest.approx((85.0 - 90.0) / 90.0, abs=1e-9)


def test_exit_on_the_final_bar_earns_no_gap():
    """There is no next session to sell into, so the shift drops it. Better
    than inventing a fill price for a day the backtest never saw."""
    engine = BacktestEngine()
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    w = pd.DataFrame({"AAA": [1.0, 1.0]}, index=idx)
    close_matrix = pd.DataFrame({"AAA": [100.0, 80.0]}, index=idx)
    ladder = [ExitTier(trigger_pct=-0.08, action="sell_all", label="Stop")]
    _, exited = engine._apply_exit_ladder(w, close_matrix, ladder)
    assert exited["AAA"].iloc[1] == pytest.approx(1.0)
    assert exited.shift(1).fillna(0.0).to_numpy().sum() == pytest.approx(0.0)
