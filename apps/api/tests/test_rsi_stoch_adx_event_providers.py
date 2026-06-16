"""PRD-22b slice 2 — RSI / Stochastic / ADX-DMI event providers.

Pure-compute tests on synthetic price frames (call `_compute(frame)`
directly, no DB or network). Encoding per `_apply_rule_threshold`:
LEVEL = 1 while true; CROSS = +1 up / -1 down / 0; EVENT = fires (1) on
the transition bar; REGIME = discrete code consumed via `equals`.
"""
from __future__ import annotations

import pandas as pd

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    AdxRegimeSignalProvider,
    AdxRisingSignalProvider,
    AdxSignalProvider,
    DiCrossBearishSignalProvider,
    DiCrossBullishSignalProvider,
    RsiOverboughtSignalProvider,
    RsiOversoldSignalProvider,
    StochKDCrossSignalProvider,
    StochOverboughtCrossDownSignalProvider,
    StochOversoldCrossUpSignalProvider,
    _adx_components,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "rsi_oversold", "rsi_overbought", "stoch_k_d_cross",
    "stoch_oversold_cross_up", "stoch_overbought_cross_down",
    "adx_regime", "adx_rising", "di_cross_bullish", "di_cross_bearish",
]


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


_DECLINE = [100.0 - i for i in range(40)]
# A strong up-trend, but with periodic 1-pt pullbacks so RSI's average-loss
# term is non-zero (a *pure* monotonic rise leaves avg_loss = 0 → RSI = NaN).
_RISE = []
_v = 60.0
for _i in range(40):
    _v += -1.0 if _i % 5 == 4 else 3.0
    _RISE.append(_v)
_V = [100.0 - i for i in range(20)] + [80.0 + 2 * i for i in range(20)]   # down then up
_INV_V = [60.0 + i for i in range(20)] + [80.0 - 2 * i for i in range(20)]  # up then down
# A 90↔110 triangle wave: %K/%D oscillate smoothly through the whole range
# and cross at every level (avoids the 0/100 saturation a monotonic ramp
# produces with high==low==close, which leaves %K==%D and kills the cross).
_TRIANGLE = []
_tv = 90.0
_tup = True
for _ in range(60):
    _TRIANGLE.append(_tv)
    _tv += 4.0 if _tup else -4.0
    if _tv >= 110:
        _tup = False
    if _tv <= 90:
        _tup = True
# Choppy (low-ADX) then a clean trend — so ADX actually rises off a low base.
# A *perfectly* linear trend gives a constant DX, hence a flat (never-rising) ADX.
_CHOP_THEN_TREND = (
    [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(20)]
    + [98.0 - 2.0 * i for i in range(20)]
)


# ── RSI levels ───────────────────────────────────────────────────────────────


def test_rsi_oversold_holds_through_a_decline() -> None:
    s = RsiOversoldSignalProvider(period=14)._compute(_frame(_DECLINE))
    assert s.iloc[-1] == 1.0            # RSI pinned low → oversold holds
    over = RsiOverboughtSignalProvider(period=14)._compute(_frame(_DECLINE))
    assert over.iloc[-1] == 0.0         # not overbought in a decline


def test_rsi_overbought_holds_through_a_rally() -> None:
    s = RsiOverboughtSignalProvider(period=14)._compute(_frame(_RISE))
    assert s.iloc[-1] == 1.0
    assert set(s.dropna().unique()) <= {0.0, 1.0}


# ── Stochastic cross / zone-cross ────────────────────────────────────────────


def test_stoch_k_d_cross_is_signed_and_bidirectional() -> None:
    s = StochKDCrossSignalProvider(k_period=5, d_period=3)._compute(_frame(_TRIANGLE))
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}
    assert (s == 1.0).any() and (s == -1.0).any()


def test_stoch_oversold_cross_up_fires_off_the_bottom() -> None:
    s = StochOversoldCrossUpSignalProvider(k_period=5, d_period=3, oversold=30)._compute(_frame(_TRIANGLE))
    assert (s == 1.0).any()
    assert set(s.unique()) <= {0.0, 1.0}


def test_stoch_overbought_cross_down_fires_off_the_top() -> None:
    s = StochOverboughtCrossDownSignalProvider(k_period=5, d_period=3, overbought=70)._compute(_frame(_TRIANGLE))
    assert (s == 1.0).any()
    assert set(s.unique()) <= {0.0, 1.0}


# ── ADX regime / rising / DI crosses ─────────────────────────────────────────


def test_adx_regime_emits_only_valid_codes_and_trends_in_a_strong_move() -> None:
    s = AdxRegimeSignalProvider(period=14)._compute(_frame(_DECLINE))
    assert set(s.dropna().unique()) <= {0.0, 1.0, 2.0}
    assert s.iloc[-1] == 2.0  # a clean sustained move = trending regime


def test_adx_rising_flags_strengthening_trend() -> None:
    s = AdxRisingSignalProvider(period=14, lookback=5)._compute(_frame(_CHOP_THEN_TREND))
    assert (s == 1.0).any()  # ADX climbs as chop gives way to the trend
    assert set(s.dropna().unique()) <= {0.0, 1.0}


def test_di_cross_bullish_fires_plus_one_on_a_turn_up() -> None:
    s = DiCrossBullishSignalProvider(period=5)._compute(_frame(_V))
    assert (s == 1.0).any()
    assert set(s.unique()) <= {0.0, 1.0}


def test_di_cross_bearish_fires_minus_one_on_a_turn_down() -> None:
    s = DiCrossBearishSignalProvider(period=5)._compute(_frame(_INV_V))
    assert (s == -1.0).any()
    assert set(s.unique()) <= {0.0, -1.0}


# ── compose contract: children share the parent's ADX maths ──────────────────


def test_adx_provider_matches_shared_components_helper() -> None:
    frame = _frame(_DECLINE)
    from_provider = AdxSignalProvider(period=14)._compute(frame)
    adx, _, _ = _adx_components(frame, 14)
    assert from_provider.equals(adx)


# ── Integration guards ───────────────────────────────────────────────────────


def test_new_primitives_registered_catalogued_and_snapshotted() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"
        assert pid in covered, f"{pid} not covered by the snapshot warm"
