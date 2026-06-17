"""PRD-22b — Bollinger Band event/regime provider unit tests.

Pure-compute tests on synthetic price frames (call `_compute(frame)` directly).
These decompose the Bollinger family's consumption patterns into the signed
series `_apply_rule_threshold` expects (REGIME code via `equals`, EVENT fires,
VALUE scalar). %B itself is already shipped as the `bbands` primitive, so it is
not re-added here.

Fixture note (the recurring lesson): Bollinger bands are *self-inflating* — the
current bar is in its own rolling window, so a smooth trend never closes above
its own +2σ band. A band-*tag* needs a single outlier after a flat base; a
band-*walk* needs a steeply accelerating tail. Fixtures below are tuned to
exercise the logic, not to look realistic.
"""
from __future__ import annotations

import pandas as pd

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    BbBandwidthSignalProvider,
    BbSqueezeFireSignalProvider,
    BbSqueezeSignalProvider,
    BbTagLowerSignalProvider,
    BbTagUpperSignalProvider,
    BbWalkUpperSignalProvider,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "bb_bandwidth", "bb_squeeze", "bb_squeeze_fire",
    "bb_walk_upper", "bb_tag_upper", "bb_tag_lower",
]
# Flat base, then a cubic acceleration steep enough to outrun the rising band.
_CUBIC_WALK = [100.0] * 20 + [100.0 + (i + 1) ** 3 * 0.8 for i in range(8)]


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


# ── VALUE: bandwidth ─────────────────────────────────────────────────────────


def test_bb_bandwidth_is_zero_on_a_flat_series_positive_on_a_volatile_one() -> None:
    flat = BbBandwidthSignalProvider(period=20)._compute(_frame([100.0] * 25))
    assert flat.iloc[-1] == 0.0  # no dispersion → zero-width bands
    vol = BbBandwidthSignalProvider(period=20)._compute(
        _frame([90.0, 110.0] * 13))
    assert vol.iloc[-1] > 0.0


def test_bb_bandwidth_widens_with_dispersion() -> None:
    tight = BbBandwidthSignalProvider(period=10)._compute(
        _frame([100.0, 101.0] * 13)).iloc[-1]
    wide = BbBandwidthSignalProvider(period=10)._compute(
        _frame([80.0, 120.0] * 13)).iloc[-1]
    assert wide > tight


# ── REGIME: squeeze ──────────────────────────────────────────────────────────


def test_bb_squeeze_on_when_compressed_off_when_wide() -> None:
    on = BbSqueezeSignalProvider(period=20)._compute(_frame([100.0] * 25))
    assert on.iloc[-1] == 1.0
    off = BbSqueezeSignalProvider(period=20)._compute(_frame([90.0, 110.0] * 13))
    assert off.iloc[-1] == 0.0


def test_bb_squeeze_warmup_bars_carry_no_regime() -> None:
    s = BbSqueezeSignalProvider(period=20)._compute(_frame([100.0] * 25))
    assert pd.isna(s.iloc[0])  # first bars have no bandwidth yet → NaN, not 0


# ── EVENT: squeeze fire (direction-aware) ────────────────────────────────────


def test_bb_squeeze_fire_emits_plus_one_on_an_upside_release() -> None:
    # 25 flat bars (squeeze active), then a jump that closes above the band.
    s = BbSqueezeFireSignalProvider(period=20)._compute(_frame([100.0] * 25 + [105.0]))
    assert s.iloc[-1] == 1.0
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}


def test_bb_squeeze_fire_emits_minus_one_on_a_downside_release() -> None:
    s = BbSqueezeFireSignalProvider(period=20)._compute(_frame([100.0] * 25 + [95.0]))
    assert s.iloc[-1] == -1.0


# ── EVENT: band walk + band tags ─────────────────────────────────────────────


def test_bb_walk_upper_fires_after_n_consecutive_closes_above_the_band() -> None:
    s = BbWalkUpperSignalProvider(period=20, consecutive=3)._compute(_frame(_CUBIC_WALK))
    assert (s == 1.0).any()
    assert set(s.unique()) <= {0.0, 1.0}


def test_bb_tag_upper_fires_on_a_close_above_the_upper_band() -> None:
    s = BbTagUpperSignalProvider(period=20)._compute(_frame([100.0] * 25 + [105.0]))
    assert s.iloc[-1] == 1.0


def test_bb_tag_lower_fires_on_a_close_below_the_lower_band() -> None:
    s = BbTagLowerSignalProvider(period=20)._compute(_frame([100.0] * 25 + [95.0]))
    assert s.iloc[-1] == 1.0


# ── Integration guards ───────────────────────────────────────────────────────


def test_new_bollinger_primitives_registered_catalogued_and_snapshotted() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"
        assert catalog[pid].composes == ["bbands"], f"{pid} should compose on bbands"
        assert pid in covered, f"{pid} not covered by the snapshot warm"
