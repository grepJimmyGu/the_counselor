"""PRD-22b — 52-week-extrema provider unit tests.

Pure-compute tests on synthetic price frames (mirrors the pattern in
test_technical_signal_providers.py — call `_compute(frame)` directly, no DB
or network). Formulas per PRD-22b §3.3.

The `min_periods=20` guard in each provider means a synthetic frame needs
≥20 warmup bars before the rolling window yields a value — every fixture
front-loads a flat plateau to satisfy that.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.backtester.technical_signal_providers import (
    DaysSince52wHighProvider,
    DistanceTo52wHighProvider,
    DistanceTo52wLowProvider,
    Price52wHighBreakoutProvider,
    Price52wHighRatioProvider,
    Price52wLowBreakdownProvider,
    PriceIn52wHighZoneProvider,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


# ── DISTANCE ─────────────────────────────────────────────────────────────────


def test_distance_to_52w_high_is_zero_at_a_fresh_high() -> None:
    # Monotonic rise → every bar is a new high → distance 0 at the last bar.
    s = DistanceTo52wHighProvider(lookback=252)._compute(_frame([100 + i for i in range(40)]))
    assert s.iloc[-1] == pytest.approx(0.0)


def test_distance_to_52w_high_is_negative_below_the_high() -> None:
    # Plateau at 200 (the window high), then a pullback to 150 → 25% below.
    closes = [200.0] * 25 + [150.0]
    s = DistanceTo52wHighProvider(lookback=252)._compute(_frame(closes))
    assert s.iloc[-1] == pytest.approx(-25.0)


def test_distance_to_52w_low_is_positive_above_the_low() -> None:
    # Low of 50 in the window; last close 75 → +50% above the low.
    closes = [100.0] * 25 + [50.0, 75.0]
    s = DistanceTo52wLowProvider(lookback=252)._compute(_frame(closes))
    assert s.iloc[-1] == pytest.approx(50.0)


# ── VALUE ────────────────────────────────────────────────────────────────────


def test_price_52w_high_ratio_is_close_over_high() -> None:
    closes = [200.0] * 25 + [150.0]  # high=200, last=150 → 0.75
    s = Price52wHighRatioProvider(lookback=252)._compute(_frame(closes))
    assert s.iloc[-1] == pytest.approx(0.75)


def test_days_since_52w_high_counts_bars_from_the_peak() -> None:
    closes = [100.0] * 25 + [110.0, 108.0, 106.0]  # peak at the 110 bar
    s = DaysSince52wHighProvider(lookback=252)._compute(_frame(closes))
    assert s.iloc[-3] == 0.0  # the 110 bar is the high
    assert s.iloc[-2] == 1.0
    assert s.iloc[-1] == 2.0


# ── EVENT (fires once, on the transition bar) ────────────────────────────────


def test_52w_high_breakout_fires_only_on_the_transition_bar() -> None:
    # Plateau at 100, then 101 (breakout), then keep rising — event only at 101.
    closes = [100.0] * 25 + [101.0, 102.0, 103.0]
    s = Price52wHighBreakoutProvider(lookback=252)._compute(_frame(closes))
    assert s.tolist()[-4:] == [0.0, 1.0, 0.0, 0.0]


def test_52w_low_breakdown_fires_only_on_the_transition_bar() -> None:
    closes = [100.0] * 25 + [99.0, 98.0, 97.0]
    s = Price52wLowBreakdownProvider(lookback=252)._compute(_frame(closes))
    assert s.tolist()[-4:] == [0.0, 1.0, 0.0, 0.0]


# ── LEVEL (the 2-25%-below-high setup zone) ──────────────────────────────────


def test_price_in_52w_high_zone_default_2_to_25_pct() -> None:
    # Last five bars sit 1 / 5 / 15 / 30 / 50% below a fixed 100 high.
    closes = [100.0] * 25 + [99.0, 95.0, 85.0, 70.0, 50.0]
    s = PriceIn52wHighZoneProvider(min_pct=2, max_pct=25, lookback=252)._compute(_frame(closes))
    # 1% below → outside (inside the 2% edge); 5%,15% inside; 30%,50% outside.
    assert s.tolist()[-5:] == [0.0, 1.0, 1.0, 0.0, 0.0]


def test_price_in_52w_high_zone_respects_custom_bounds() -> None:
    closes = [100.0] * 25 + [99.0, 95.0, 85.0, 70.0, 50.0]
    # Widen the band to 0.5-40% → now 1%, 5%, 15%, 30% inside; 50% outside.
    s = PriceIn52wHighZoneProvider(min_pct=0.5, max_pct=40, lookback=252)._compute(_frame(closes))
    assert s.tolist()[-5:] == [1.0, 1.0, 1.0, 1.0, 0.0]
