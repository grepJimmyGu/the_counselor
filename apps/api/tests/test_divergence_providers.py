"""PRD-22b — divergence detector + provider unit tests.

Divergences between price and an oscillator are hard to coax out of smooth
synthetic OHLCV, so the core detector (`_pivot_indices`, `_divergence_signal`)
is tested DIRECTLY with hand-built price + indicator series where the pivots
and their values are known exactly. The providers then get a wiring +
encoding check (bullish emit {0,+1}, bearish emit {0,-1}).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.services.backtester.technical_signal_providers import (
    MacdBearishDivergenceSignalProvider,
    MacdBullishDivergenceSignalProvider,
    ObvDivergenceBearishSignalProvider,
    ObvDivergenceBullishSignalProvider,
    RsiBearishDivergenceSignalProvider,
    RsiBullishDivergenceSignalProvider,
    RsiHiddenBullishDivergenceSignalProvider,
    _divergence_signal,
    _pivot_indices,
    get_technical_providers,
)
from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

_NEW_IDS = [
    "macd_bullish_divergence", "macd_bearish_divergence",
    "rsi_bullish_divergence", "rsi_bearish_divergence", "rsi_hidden_bullish_div",
    "obv_divergence_bullish", "obv_divergence_bearish",
]


def _s(vals: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="D")
    return pd.Series(vals, index=idx, dtype=float)


# Two price troughs at idx 4 and 11 (a strict local min over ±3 bars each).
_PRICE_TROUGHS = [100, 95, 90, 85, 80, 85, 90, 92, 90, 86, 82, 78, 82, 86, 90, 92, 94]
# Two price peaks at idx 4 and 11.
_PRICE_PEAKS = [80, 85, 90, 95, 100, 95, 90, 88, 90, 94, 98, 102, 98, 94, 90, 88, 86]


# ── pivot detector ───────────────────────────────────────────────────────────


def test_pivot_indices_finds_strict_local_extrema() -> None:
    assert _pivot_indices(np.array(_PRICE_TROUGHS, dtype=float), 3, want_min=True) == [4, 11]
    assert _pivot_indices(np.array(_PRICE_PEAKS, dtype=float), 3, want_min=False) == [4, 11]


# ── divergence signal (hand-built price + indicator) ─────────────────────────


def test_regular_bullish_divergence_fires_plus_one() -> None:
    # price: lower low (80 → 78). indicator: HIGHER low (20 → 32).
    price = _s(_PRICE_TROUGHS)               # trough[11]=78 < trough[4]=80
    ind = _s([50, 45, 35, 28, 20, 30, 42, 48, 44, 40, 38, 32, 40, 46, 50, 52, 54])
    out = _divergence_signal(price, ind, 3, troughs=True, price_lower=True, ind_lower=False, sign=1)
    assert out.iloc[14] == 1.0      # confirmed `order` bars after the 2nd pivot
    assert out.iloc[13] == 0.0
    assert set(out.unique()) <= {0.0, 1.0}


def test_regular_bearish_divergence_fires_minus_one() -> None:
    # price: higher high (100 → 102). indicator: LOWER high (80 → 70).
    price = _s(_PRICE_PEAKS)
    ind = _s([30, 40, 55, 68, 80, 68, 55, 52, 55, 60, 65, 70, 62, 55, 50, 48, 46])
    out = _divergence_signal(price, ind, 3, troughs=False, price_lower=False, ind_lower=True, sign=-1)
    assert out.iloc[14] == -1.0
    assert set(out.unique()) <= {-1.0, 0.0}


def test_hidden_bullish_divergence_fires_plus_one() -> None:
    # price: HIGHER low (82 → 84). indicator: LOWER low (20 → 15).
    price = _s([100, 95, 90, 86, 82, 86, 90, 92, 90, 88, 86, 84, 88, 92, 96, 98, 100])
    ind = _s([50, 45, 35, 28, 20, 30, 42, 48, 44, 30, 22, 15, 25, 35, 45, 50, 55])
    out = _divergence_signal(price, ind, 3, troughs=True, price_lower=False, ind_lower=True, sign=1)
    assert (out == 1.0).any()


def test_no_divergence_when_price_and_indicator_agree() -> None:
    # price lower low AND indicator lower low → no bullish divergence.
    price = _s(_PRICE_TROUGHS)
    ind = _s([50, 45, 35, 28, 20, 30, 42, 48, 44, 30, 22, 15, 25, 35, 45, 50, 55])
    out = _divergence_signal(price, ind, 3, troughs=True, price_lower=True, ind_lower=False, sign=1)
    assert (out == 0.0).all()


# ── provider wiring + encoding ───────────────────────────────────────────────


def _seg(a: float, b: float, n: int) -> list[float]:
    return list(np.linspace(a, b, n))[1:]


def _frame(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": 1_000_000.0}, index=idx)


# Steep drop to a first low, bounce, then a gentler deeper low → RSI/MACD print
# a higher low against price's lower low (a regular bullish divergence).
_BULL_DIV_PRICE = (
    [100.0] + _seg(100, 80, 9) + _seg(80, 96, 10) + _seg(96, 78, 22) + _seg(78, 90, 10)
)


def test_rsi_and_macd_bullish_divergence_providers_fire() -> None:
    frame = _frame(_BULL_DIV_PRICE)
    rsi = RsiBullishDivergenceSignalProvider(order=4)._compute(frame)
    macd = MacdBullishDivergenceSignalProvider(order=4)._compute(frame)
    assert (rsi == 1.0).any()
    assert (macd == 1.0).any()


def test_divergence_providers_encode_their_direction() -> None:
    frame = _frame(_BULL_DIV_PRICE)
    for prov in (RsiBullishDivergenceSignalProvider(order=4),
                 MacdBullishDivergenceSignalProvider(order=4),
                 ObvDivergenceBullishSignalProvider(order=4),
                 RsiHiddenBullishDivergenceSignalProvider(order=4)):
        assert set(prov._compute(frame).unique()) <= {0.0, 1.0}
    for prov in (RsiBearishDivergenceSignalProvider(order=4),
                 MacdBearishDivergenceSignalProvider(order=4),
                 ObvDivergenceBearishSignalProvider(order=4)):
        assert set(prov._compute(frame).unique()) <= {-1.0, 0.0}


# ── Integration guards ───────────────────────────────────────────────────────


def test_divergence_primitives_registered_catalogued_and_snapshotted() -> None:
    catalog = {p.id: p for p in SIGNAL_PRIMITIVES}
    registry = get_technical_providers()
    covered = set(snapshot_primitive_ids())
    for pid in _NEW_IDS:
        assert pid in catalog, f"{pid} missing from catalog"
        assert catalog[pid].output_kind.value == "divergence", pid
        assert catalog[pid].provider_impl in registry, f"{pid} has no provider"
        assert pid in covered, f"{pid} not covered by the snapshot warm"
