"""PRD-22b — MA + MACD event/cross/level provider unit tests.

Pure-compute tests on synthetic price frames (mirrors test_52w_extrema_providers.py
— call `_compute(frame)` directly, no DB or network). These primitives
decompose the MA/MACD families' canonical *consumption patterns* into the
signed series `_apply_rule_threshold` expects:

    CROSS  → +1 on the up-cross bar, −1 on the down-cross bar, 0 elsewhere
    EVENT  → non-zero on the transition bar (fires), 0 elsewhere
    LEVEL  → 1.0 while the condition holds, 0.0 otherwise
"""
from __future__ import annotations

import pandas as pd

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    DeathCrossSignalProvider,
    GoldenCrossSignalProvider,
    MacdHistogramFlipSignalProvider,
    MacdSignalCrossSignalProvider,
    MacdZeroLineCrossSignalProvider,
    MaSlopePositiveSignalProvider,
    PriceAboveMaSignalProvider,
    PriceMaCrossDownSignalProvider,
    PriceMaCrossUpSignalProvider,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "price_above_ma", "price_ma_cross_up", "price_ma_cross_down",
    "golden_cross", "death_cross", "ma_slope_positive",
    "macd_signal_cross", "macd_histogram_flip", "macd_zero_line_cross",
]


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close,
         "volume": 1_000_000.0},
        index=idx,
    )


def _triangle(periods: int = 12, amplitude: float = 8.0, base: float = 100.0) -> list[float]:
    """A symmetric up/down/up/down saw-tooth — long enough that the default
    MACD EMAs flip sign in both directions, so the cross/flip series contain
    both a +1 and a −1."""
    out: list[float] = []
    val = base
    rising = True
    for _ in range(6):
        for _ in range(periods):
            val += amplitude if rising else -amplitude
            out.append(val)
        rising = not rising
    return out


# ── LEVEL: price above MA (holds while true) ─────────────────────────────────


def test_price_above_ma_is_one_while_above_zero_while_below() -> None:
    # Plateau at 100 (close == MA → not strictly above), then a jump to 120
    # (above) then a drop to 80 (below).
    closes = [100.0] * 5 + [120.0, 80.0]
    s = PriceAboveMaSignalProvider(period=3)._compute(_frame(closes))
    assert s.iloc[-2] == 1.0  # 120 > 3-bar MA
    assert s.iloc[-1] == 0.0  # 80 < 3-bar MA


def test_ma_slope_positive_one_when_rising_zero_when_falling() -> None:
    rising = MaSlopePositiveSignalProvider(period=2, lookback=2)._compute(
        _frame([10.0, 10.0, 12.0, 14.0, 16.0]))
    assert rising.iloc[-1] == 1.0
    falling = MaSlopePositiveSignalProvider(period=2, lookback=2)._compute(
        _frame([16.0, 16.0, 14.0, 12.0, 10.0]))
    assert falling.iloc[-1] == 0.0


# ── CROSS: price vs MA (+1 up / −1 down, on the transition bar only) ──────────


def test_price_ma_cross_up_emits_plus_one_on_the_cross_bar() -> None:
    closes = [10.0, 10.0, 10.0, 10.0, 9.0, 12.0]  # last bar pops above the MA
    s = PriceMaCrossUpSignalProvider(period=3)._compute(_frame(closes))
    assert s.iloc[-1] == 1.0
    assert set(s.unique()) <= {0.0, 1.0}  # never negative


def test_price_ma_cross_down_emits_minus_one_on_the_cross_bar() -> None:
    closes = [10.0, 10.0, 10.0, 10.0, 11.0, 8.0]  # last bar drops below the MA
    s = PriceMaCrossDownSignalProvider(period=3)._compute(_frame(closes))
    assert s.iloc[-1] == -1.0
    assert set(s.unique()) <= {0.0, -1.0}  # never positive


# ── CROSS: golden / death (MA-vs-MA, signed by direction) ────────────────────


def test_golden_cross_emits_plus_one_when_fast_crosses_above_slow() -> None:
    # Down then sharp up → fast MA(2) crosses above slow MA(4).
    closes = [20.0, 19.0, 18.0, 17.0, 18.0, 20.0, 23.0]
    s = GoldenCrossSignalProvider(fast_period=2, slow_period=4)._compute(_frame(closes))
    assert (s == 1.0).any()           # the golden cross fired
    assert set(s.unique()) <= {0.0, 1.0}  # golden cross never emits −1


def test_death_cross_emits_minus_one_when_fast_crosses_below_slow() -> None:
    # Up then sharp down → fast MA(2) crosses below slow MA(4).
    closes = [17.0, 18.0, 19.0, 20.0, 19.0, 17.0, 14.0]
    s = DeathCrossSignalProvider(fast_period=2, slow_period=4)._compute(_frame(closes))
    assert (s == -1.0).any()          # the death cross fired
    assert set(s.unique()) <= {0.0, -1.0}  # death cross never emits +1


# ── MACD cross / flip / zero-line ────────────────────────────────────────────


def test_macd_signal_cross_is_signed_and_bidirectional() -> None:
    s = MacdSignalCrossSignalProvider(
        fast_period=3, slow_period=6, signal_period=2)._compute(_frame(_triangle()))
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}
    assert (s == 1.0).any() and (s == -1.0).any()  # both directions occur


def test_macd_histogram_flip_is_elementwise_identical_to_signal_cross() -> None:
    # A histogram sign-change IS the signal-line cross (histogram =
    # macd_line − signal_line, so hist > 0 ⟺ macd_line > signal_line).
    # The two primitives compute the SAME signed series — they differ only
    # in output_kind (EVENT `fires` vs CROSS direction-picker). This test
    # codifies that intentional identity; if the editorial gate later wants
    # an inflection-based histogram flip, this assertion is the trip-wire.
    frame = _frame(_triangle())
    cross = MacdSignalCrossSignalProvider(
        fast_period=3, slow_period=6, signal_period=2)._compute(frame)
    flip = MacdHistogramFlipSignalProvider(
        fast_period=3, slow_period=6, signal_period=2)._compute(frame)
    assert flip.equals(cross)


def test_macd_zero_line_cross_fires_when_macd_line_crosses_zero() -> None:
    # Long fall then long rise → the MACD line (fast EMA − slow EMA) goes
    # negative then positive, crossing zero upward.
    closes = [100.0 - i for i in range(30)] + [70.0 + 2 * i for i in range(30)]
    s = MacdZeroLineCrossSignalProvider(
        fast_period=3, slow_period=6, signal_period=2)._compute(_frame(closes))
    assert set(s.unique()) <= {-1.0, 0.0, 1.0}
    assert (s == 1.0).any()  # the upward zero-line cross fired


# ── Integration guards: catalog ↔ registry ↔ snapshot coverage ───────────────


def test_new_primitives_are_registered_and_catalogued() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"


def test_new_primitives_join_the_daily_snapshot() -> None:
    # All nine are local TechnicalSignalProviders, so they must auto-join the
    # nightly screener snapshot warm (and thus become screenable).
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in covered, f"{pid} not covered by the snapshot warm"
