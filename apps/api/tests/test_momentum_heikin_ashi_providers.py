"""PRD-22b — Momentum acceleration + Heikin-Ashi provider unit tests.

Pure-compute tests on synthetic price frames. `momentum_acceleration`
compares per-month return *rates* (not raw cumulative returns), so a steady
trend reads ~0 and acceleration shows as a positive value. Heikin-Ashi candles
need the recursive HA-open pass; with `high==low==close` fixtures HA still
tracks direction cleanly.
"""
from __future__ import annotations

import pandas as pd

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    HeikinAshiColorFlipSignalProvider,
    HeikinAshiConsecutiveSignalProvider,
    HeikinAshiTrendSignalProvider,
    MomentumAccelerationSignalProvider,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "momentum_acceleration", "heikin_ashi_trend",
    "heikin_ashi_consecutive", "heikin_ashi_color_flip",
]
_UP = [100.0 + i for i in range(40)]
_DOWN = [140.0 - i for i in range(40)]
# down → up → down, so Heikin-Ashi flips color in both directions.
_DOWN_UP_DOWN = (
    [120.0 - i for i in range(15)]
    + [105.0 + i * 2 for i in range(15)]
    + [135.0 - i * 2 for i in range(15)]
)


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


# ── VALUE: momentum acceleration ─────────────────────────────────────────────


def test_momentum_acceleration_positive_when_recent_pace_outruns_the_baseline() -> None:
    # Flat for ~6 months, then a 3-month ramp → the recent rate beats the
    # trailing rate → positive acceleration.
    accel = [100.0] * 130 + [100.0 * 1.005 ** i for i in range(63)]
    assert MomentumAccelerationSignalProvider()._compute(_frame(accel)).iloc[-1] > 0


def test_momentum_acceleration_negative_when_momentum_fades() -> None:
    # A ramp that flattens out → recent rate below the trailing rate.
    decel = [100.0 * 1.004 ** i for i in range(130)] + [100.0 * 1.004 ** 129] * 63
    assert MomentumAccelerationSignalProvider()._compute(_frame(decel)).iloc[-1] < 0


# ── Heikin-Ashi ──────────────────────────────────────────────────────────────


def test_heikin_ashi_trend_regime_tracks_direction() -> None:
    assert HeikinAshiTrendSignalProvider()._compute(_frame(_UP)).iloc[-1] == 1.0
    assert HeikinAshiTrendSignalProvider()._compute(_frame(_DOWN)).iloc[-1] == 0.0


def test_heikin_ashi_consecutive_count_is_signed_by_direction() -> None:
    up = HeikinAshiConsecutiveSignalProvider()._compute(_frame(_UP))
    assert up.iloc[-1] > 1  # a long green streak
    down = HeikinAshiConsecutiveSignalProvider()._compute(_frame(_DOWN))
    assert down.iloc[-1] < -1  # a long red streak


def test_heikin_ashi_color_flip_fires_both_directions_signed() -> None:
    s = HeikinAshiColorFlipSignalProvider()._compute(_frame(_DOWN_UP_DOWN))
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}
    assert (s == 1.0).any()   # flip to green (up)
    assert (s == -1.0).any()  # flip to red (down)


# ── Integration guards ───────────────────────────────────────────────────────


def test_new_slice5_primitives_registered_catalogued_and_snapshotted() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"
        assert pid in covered, f"{pid} not covered by the snapshot warm"
