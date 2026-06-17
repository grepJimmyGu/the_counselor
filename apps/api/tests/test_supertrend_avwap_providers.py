"""PRD-22b — Supertrend + Anchored VWAP provider unit tests.

Pure-compute tests on synthetic price frames. Supertrend is a stateful
trailing line (an explicit O(n) carry-forward pass); the AVWAP children are a
trailing volume-weighted window. With `high==low==close` fixtures, ATR reduces
to the EMA of |Δclose| and AVWAP reduces to a volume-weighted SMA — enough to
exercise direction flips and the band side.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    AnchoredVwapSignalProvider,
    DistanceToAnchoredVwapSignalProvider,
    PriceAboveAnchoredVwapSignalProvider,
    SupertrendAbovePriceSignalProvider,
    SupertrendFlipSignalProvider,
    SupertrendSignalProvider,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "supertrend", "supertrend_flip", "supertrend_above_price",
    "anchored_vwap", "distance_to_anchored_vwap", "price_above_anchored_vwap",
]
_UPTREND = [100.0 + i for i in range(30)]
_DOWNTREND = [130.0 - i for i in range(30)]
# down → up → down, so the Supertrend flips in BOTH directions.
_DOWN_UP_DOWN = (
    [120.0 - i for i in range(20)]
    + [100.0 + i * 2 for i in range(20)]
    + [140.0 - i * 2 for i in range(15)]
)


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


# ── Supertrend ───────────────────────────────────────────────────────────────


def test_supertrend_line_sits_below_price_in_an_uptrend_above_in_a_downtrend() -> None:
    up = SupertrendSignalProvider()._compute(_frame(_UPTREND))
    assert up.iloc[-1] < _UPTREND[-1]      # trailing stop below price
    down = SupertrendSignalProvider()._compute(_frame(_DOWNTREND))
    assert down.iloc[-1] > _DOWNTREND[-1]  # line above price


def test_supertrend_flip_fires_both_directions_signed() -> None:
    s = SupertrendFlipSignalProvider()._compute(_frame(_DOWN_UP_DOWN))
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}
    assert (s == 1.0).any()   # a flip up to an up-trend
    assert (s == -1.0).any()  # a flip down to a down-trend


def test_supertrend_above_price_level_tracks_the_downtrend() -> None:
    up = SupertrendAbovePriceSignalProvider()._compute(_frame(_UPTREND))
    assert up.iloc[-1] == 0.0   # up-trend → line below price
    down = SupertrendAbovePriceSignalProvider()._compute(_frame(_DOWNTREND))
    assert down.iloc[-1] == 1.0  # down-trend → line above price


# ── Anchored VWAP ────────────────────────────────────────────────────────────


def test_anchored_vwap_equals_volume_weighted_mean_at_the_last_bar() -> None:
    closes = [100.0 + i for i in range(30)]
    av = AnchoredVwapSignalProvider(anchor_lookback=10)._compute(_frame(closes))
    # equal volume + typical==close → AVWAP is just the trailing mean.
    expected = sum(closes[-10:]) / 10
    assert av.iloc[-1] == pytest.approx(expected)


def test_distance_to_anchored_vwap_is_signed() -> None:
    prov = DistanceToAnchoredVwapSignalProvider(anchor_lookback=10)
    above = prov._compute(_frame([100.0 + i for i in range(30)]))  # rising → above the trailing mean
    assert above.iloc[-1] > 0.0
    below = prov._compute(_frame([130.0 - i for i in range(30)]))  # falling → below
    assert below.iloc[-1] < 0.0


def test_price_above_anchored_vwap_level() -> None:
    prov = PriceAboveAnchoredVwapSignalProvider(anchor_lookback=10)
    assert prov._compute(_frame([100.0 + i for i in range(30)])).iloc[-1] == 1.0
    assert prov._compute(_frame([130.0 - i for i in range(30)])).iloc[-1] == 0.0


# ── Integration guards ───────────────────────────────────────────────────────


def test_new_slice4_primitives_registered_catalogued_and_snapshotted() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"
        assert pid in covered, f"{pid} not covered by the snapshot warm"
