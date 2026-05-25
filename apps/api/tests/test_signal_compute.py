"""Stage 8 v0 — signal_service pure helpers + engine-backed compute.

Phase A: `signals_equal` (with float-noise tolerance) and `classify_change`.
Phase B: `compute_current_signal` (synthetic-price end-to-end).
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
from app.services.signal_service import (
    classify_change,
    compute_current_signal,
    signals_equal,
)


# ── signals_equal ────────────────────────────────────────────────────────────


def test_signals_equal_returns_true_for_identical_long_position() -> None:
    a = {"position": "long", "ticker": "NVDA"}
    b = {"position": "long", "ticker": "NVDA"}
    assert signals_equal(a, b) is True


def test_signals_equal_returns_false_when_ticker_changes() -> None:
    a = {"position": "long", "ticker": "NVDA"}
    b = {"position": "long", "ticker": "AAPL"}
    assert signals_equal(a, b) is False


def test_signals_equal_handles_float_rounding() -> None:
    """Spec §13 — float-derived signals must not false-flip on noise. The two
    payloads describe the same RSI signal; their `trigger_rsi` values differ
    only in the 12th decimal place after independent recomputation."""
    a = {"position": "long", "ticker": "AAPL", "trigger_rsi": 28.4000000001}
    b = {"position": "long", "ticker": "AAPL", "trigger_rsi": 28.4000000009}
    assert signals_equal(a, b) is True


def test_signals_equal_detects_real_basket_weight_change() -> None:
    """4-decimal normalization must NOT mask a real rebalance — 50.0% vs 50.1%
    is a legitimate weight change that should propagate as a rebalance event."""
    a = {"holdings": [{"ticker": "GLD", "weight": 0.5000}, {"ticker": "SLV", "weight": 0.5000}]}
    b = {"holdings": [{"ticker": "GLD", "weight": 0.5010}, {"ticker": "SLV", "weight": 0.4990}]}
    assert signals_equal(a, b) is False


def test_signals_equal_treats_both_none_as_equal() -> None:
    assert signals_equal(None, None) is True


def test_signals_equal_treats_one_none_as_unequal() -> None:
    assert signals_equal(None, {"position": "cash"}) is False


# ── classify_change ──────────────────────────────────────────────────────────


def test_classify_change_long_to_cash_is_flip_to_cash() -> None:
    prev = {"position": "long", "ticker": "NVDA"}
    new = {"position": "cash"}
    assert classify_change(prev, new) == "flip_to_cash"


def test_classify_change_cash_to_long_is_flip_to_long() -> None:
    prev = {"position": "cash"}
    new = {"position": "long", "ticker": "NVDA"}
    assert classify_change(prev, new) == "flip_to_long"


def test_classify_change_no_prior_state_to_long_is_flip_to_long() -> None:
    """First-ever recompute with no prior state is treated as cash → long.
    Phase B cron should normally suppress this (first compute = silent), but
    the classifier should still bucket it sensibly if called."""
    assert classify_change(None, {"position": "long", "ticker": "QQQ"}) == "flip_to_long"


def test_classify_change_basket_holdings_change_is_rotation() -> None:
    prev = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "SLV", "weight": 0.5}]}
    new = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "PLAT", "weight": 0.5}]}
    assert classify_change(prev, new) == "rotation"


def test_classify_change_basket_weights_change_is_rebalance() -> None:
    prev = {"holdings": [{"ticker": "GLD", "weight": 0.5}, {"ticker": "SLV", "weight": 0.5}]}
    new = {"holdings": [{"ticker": "GLD", "weight": 0.7}, {"ticker": "SLV", "weight": 0.3}]}
    assert classify_change(prev, new) == "rebalance"


# ── compute_current_signal (engine-backed, synthetic prices) ────────────────
#
# These tests mock `_load_prices` at the class level so `compute_current_signal`
# (which constructs its own BacktestEngine) picks up the patched method. Sync
# test functions are intentional — `compute_current_signal` itself wraps the
# async engine call in `asyncio.run()`, which conflicts with pytest-asyncio's
# already-running loop.


def _trending_close(start: str, days: int, direction: str = "up") -> pd.DataFrame:
    """Synthetic monotonic price series so MA filter has a deterministic signal.

    direction='up'   → close > MA on final bar (long signal)
    direction='down' → close < MA on final bar (cash signal)
    """
    dates = pd.date_range(start, periods=days, freq="B")
    if direction == "up":
        prices = np.linspace(100.0, 200.0, days)
    else:
        prices = np.linspace(200.0, 100.0, days)
    return pd.DataFrame({"adjusted_close": prices, "high": prices * 1.01}, index=dates)


def _load_prices_for(universe: list[str], frames: dict[str, pd.DataFrame], bench_sym: str):
    """Build the (universe_frames, benchmark_frame) tuple `_load_prices` returns."""
    universe_frames = {sym: frames[sym] for sym in universe if sym in frames}
    return universe_frames, frames[bench_sym]


def _base_strategy(**overrides) -> StrategyJSON:
    base = dict(
        strategy_name="Signal Compute Test",
        strategy_type="moving_average_filter",
        universe=["SYM1"],
        benchmark="SYM1",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 12, 30),
        initial_capital=100_000,
        rebalance_frequency="monthly",
        transaction_cost_bps=0,
        slippage_bps=0,
        rules=[StrategyRule(lookback_days=20)],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(),
    )
    base.update(overrides)
    return StrategyJSON(**base)


def test_compute_current_signal_ma_filter_returns_long_on_uptrend() -> None:
    """Spec §12: MA filter cash→long detection. Monotonic uptrend keeps price
    above the 20-day MA on the final bar, so the signal is `position: long`."""
    frames = {"SYM1": _trending_close("2024-01-02", days=180, direction="up")}
    strategy = _base_strategy(universe=["SYM1"], benchmark="SYM1")
    db = MagicMock()

    with patch.object(
        BacktestEngine,
        "_load_prices",
        new=AsyncMock(return_value=_load_prices_for(["SYM1"], frames, "SYM1")),
    ):
        result = compute_current_signal(db, strategy, as_of=date(2024, 12, 30))

    assert result["signal"] == {"position": "long", "ticker": "SYM1"}
    assert result["display"] == "Hold SYM1"
    assert "SYM1" in result["prices"]


def test_compute_current_signal_ma_filter_returns_cash_on_downtrend() -> None:
    """Spec §12: MA filter long→cash detection. Monotonic downtrend keeps price
    below the 20-day MA on the final bar, so the signal is `position: cash`."""
    frames = {"SYM1": _trending_close("2024-01-02", days=180, direction="down")}
    strategy = _base_strategy(universe=["SYM1"], benchmark="SYM1")
    db = MagicMock()

    with patch.object(
        BacktestEngine,
        "_load_prices",
        new=AsyncMock(return_value=_load_prices_for(["SYM1"], frames, "SYM1")),
    ):
        result = compute_current_signal(db, strategy, as_of=date(2024, 12, 30))

    assert result["signal"] == {"position": "cash"}
    assert result["display"] == "In cash"


def test_compute_current_signal_rotation_returns_basket() -> None:
    """Spec §12: momentum-rotation basket emerges as a `holdings` payload, with
    the display string starting with `Top N:`. Three random-walk symbols are
    used so the engine ranks them deterministically (seed fixed)."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2023-01-02", periods=400, freq="B")
    frames = {}
    for i, sym in enumerate(["SYM1", "SYM2", "SYM3"]):
        rng_sym = np.random.default_rng(42 + i * 17)
        returns = rng_sym.normal(0.0008 + i * 0.0002, 0.015, size=400)
        prices = 100.0 * np.cumprod(1 + returns)
        frames[sym] = pd.DataFrame(
            {"adjusted_close": prices, "high": prices * 1.01}, index=dates
        )
    strategy = _base_strategy(
        strategy_type="cross_sectional_momentum",
        universe=["SYM1", "SYM2", "SYM3"],
        benchmark="SYM1",
        start_date=date(2023, 1, 2),
        rules=[StrategyRule(formation_period_days=63, skip_period_days=5, top_n=2)],
    )
    db = MagicMock()

    with patch.object(
        BacktestEngine,
        "_load_prices",
        new=AsyncMock(return_value=_load_prices_for(["SYM1", "SYM2", "SYM3"], frames, "SYM1")),
    ):
        result = compute_current_signal(db, strategy, as_of=date(2024, 6, 28))

    assert "holdings" in result["signal"]
    holdings = result["signal"]["holdings"]
    assert 1 <= len(holdings) <= 3, "rotation basket should hold at least one ticker"
    for h in holdings:
        assert set(h.keys()) == {"ticker", "weight"}
        assert h["ticker"] in {"SYM1", "SYM2", "SYM3"}
    assert result["display"].startswith("Top ")


def test_compute_current_signal_raises_for_fundamental_strategy() -> None:
    """Spec §13 + design note: fundamental strategy types (value_composite etc.)
    are not supported in v0 — the cron's per-strategy try/except logs + skips
    them. This test pins the NotImplementedError contract."""
    strategy = _base_strategy(
        strategy_type="value_composite",
        universe=["SYM1", "SYM2"],
        benchmark="SYM1",
    )
    db = MagicMock()

    with pytest.raises(NotImplementedError, match="value_composite"):
        compute_current_signal(db, strategy, as_of=date(2024, 12, 30))
