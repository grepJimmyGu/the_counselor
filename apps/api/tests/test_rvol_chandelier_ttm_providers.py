"""PRD-22b slice 2 — RVOL / Chandelier Exit / TTM Squeeze provider tests.

Pure-compute tests on synthetic frames (call `_compute(frame)` directly,
no DB/network). Formulas per v2 spec §4.5 (RVOL), §4.3 (Chandelier),
§4.1 (TTM Squeeze). ATR is Wilder-smoothed (reused from AtrSignalProvider).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.backtester.technical_signal_providers import (
    ChandelierExitBreachSignalProvider,
    ChandelierExitLongSignalProvider,
    ChandelierExitShortSignalProvider,
    RvolSignalProvider,
    RvolSurgeSignalProvider,
    TtmSqueezeFireSignalProvider,
    TtmSqueezeSignalProvider,
)


def _frame(closes, volumes=None, highs=None, lows=None) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series([float(c) for c in closes], index=idx)
    vol = pd.Series([float(v) for v in (volumes if volumes is not None else [1e6] * n)], index=idx)
    high = pd.Series([float(h) for h in (highs if highs is not None else closes)], index=idx)
    low = pd.Series([float(lo) for lo in (lows if lows is not None else closes)], index=idx)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


# ── RVOL ─────────────────────────────────────────────────────────────────────


def test_rvol_is_volume_over_trailing_average() -> None:
    # 20 bars at 1.0M, then a bar at 2.5M → rvol = 2.5.
    vols = [1_000_000.0] * 20 + [2_500_000.0]
    s = RvolSignalProvider(lookback=20)._compute(_frame([100] * 21, volumes=vols))
    assert s.iloc[-1] == pytest.approx(2.5)


def test_rvol_excludes_today_from_the_average() -> None:
    # The trailing average is shifted by 1 — today's own volume must not be
    # in its own denominator.
    vols = [1_000_000.0] * 20 + [10_000_000.0]
    s = RvolSignalProvider(lookback=20)._compute(_frame([100] * 21, volumes=vols))
    assert s.iloc[-1] == pytest.approx(10.0)  # 10M / 1M, not 10M / (avg incl. self)


def test_rvol_surge_fires_only_on_the_crossing_bar() -> None:
    # Quiet, then two consecutive surge bars — event fires once, on the first.
    vols = [1_000_000.0] * 20 + [3_000_000.0, 3_000_000.0]
    s = RvolSurgeSignalProvider(lookback=20, surge_mult=2.0)._compute(
        _frame([100] * 22, volumes=vols))
    assert s.iloc[-2] == 1.0
    assert s.iloc[-1] == 0.0


# ── Chandelier Exit ──────────────────────────────────────────────────────────


def test_chandelier_long_is_high_minus_atr_multiple() -> None:
    # Flat OHLC (high=low=close=100) → ATR=0 → ce_long == rolling high == 100.
    s = ChandelierExitLongSignalProvider(period=22, atr_mult=3.0)._compute(_frame([100.0] * 40))
    assert s.iloc[-1] == pytest.approx(100.0)


def test_chandelier_short_is_low_plus_atr_multiple() -> None:
    s = ChandelierExitShortSignalProvider(period=22, atr_mult=3.0)._compute(_frame([100.0] * 40))
    assert s.iloc[-1] == pytest.approx(100.0)  # ATR=0 on a flat series


def test_chandelier_long_drops_below_price_when_volatile() -> None:
    # Rising series with real range → ce_long sits a few ATR below the high.
    closes = [100.0 + i for i in range(40)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    s = ChandelierExitLongSignalProvider(period=22, atr_mult=3.0)._compute(
        _frame(closes, highs=highs, lows=lows))
    assert s.iloc[-1] < highs[-1]  # stop is below the recent high
    assert not np.isnan(s.iloc[-1])


def test_chandelier_breach_fires_on_first_close_below_stop() -> None:
    # 30 rising bars (price well above the stop), then a hard gap down that
    # closes below the trailing stop → breach fires once.
    closes = [100.0 + i for i in range(30)] + [70.0, 69.0]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    s = ChandelierExitBreachSignalProvider(period=22, atr_mult=3.0)._compute(
        _frame(closes, highs=highs, lows=lows))
    assert s.iloc[-2] == 1.0   # the gap-down bar breaches
    assert s.iloc[-1] == 0.0   # still below, but no new event


# ── TTM Squeeze ──────────────────────────────────────────────────────────────


def test_ttm_squeeze_on_during_low_volatility() -> None:
    # A tiny-range drift keeps Bollinger inside Keltner → squeeze on.
    closes = [100.0 + 0.01 * (i % 2) for i in range(60)]
    highs = [c + 0.02 for c in closes]
    lows = [c - 0.02 for c in closes]
    s = TtmSqueezeSignalProvider(period=20)._compute(_frame(closes, highs=highs, lows=lows))
    assert s.iloc[-1] == 1.0


def test_ttm_squeeze_off_during_a_steady_trend() -> None:
    # A steady ramp gives high close-dispersion (wide Bollinger) but only a
    # modest per-bar range (narrow Keltner) → BB escapes KC → squeeze off.
    closes = [100.0 + i for i in range(60)]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    s = TtmSqueezeSignalProvider(period=20)._compute(_frame(closes, highs=highs, lows=lows))
    assert s.iloc[-1] == 0.0


def test_ttm_squeeze_fire_marks_the_release_bar() -> None:
    # 40 quiet bars (squeeze on), then a steady strong ramp (squeeze off) →
    # fire is exactly the on→off transition of the regime.
    quiet = [100.0 + 0.01 * (i % 2) for i in range(40)]
    ramp = [100.0 + 2.0 * i for i in range(1, 21)]
    closes = quiet + ramp
    highs = [c + 0.02 for c in quiet] + [c + 0.1 for c in ramp]
    lows = [c - 0.02 for c in quiet] + [c - 0.1 for c in ramp]
    fire = TtmSqueezeFireSignalProvider(period=20)._compute(_frame(closes, highs=highs, lows=lows))
    on = TtmSqueezeSignalProvider(period=20)._compute(_frame(closes, highs=highs, lows=lows))
    # Fire fires exactly where the regime transitions on→off.
    transitions = ((on.shift(1) == 1.0) & (on == 0.0)).astype(float)
    assert fire.equals(transitions)
    assert fire.sum() >= 1.0  # at least one release in the window
