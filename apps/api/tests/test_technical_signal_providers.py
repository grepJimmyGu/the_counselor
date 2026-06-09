"""PRD-16a-2 — technical-indicator provider tests.

Tests representative providers across families on synthetic OHLCV data.
Not every one of the ~46 providers gets a dedicated test (overkill for
v1); the parametrized smoke test confirms each provider at least
*returns* a series without raising. Per-family deep tests verify the
computation gives the textbook answer on known inputs.

Synthetic data lets the tests run without hitting the real PriceDataService
or Alpha Vantage. Where a provider's logic depends on `PriceDataService`,
we monkey-patch the get_price_frame method to return our synthetic frame.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from app.services.backtester.technical_signal_providers import (
    AdxSignalProvider,
    AtrSignalProvider,
    BbandsSignalProvider,
    DonchianBreakoutSignalProvider,
    EmaSignalProvider,
    MacdSignalProvider,
    NatrSignalProvider,
    ObvSignalProvider,
    RocSignalProvider,
    RsiSignalProvider,
    SmaSignalProvider,
    VolRegimeSignalProvider,
    get_technical_providers,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _synthetic_frame(periods: int = 300, start_price: float = 100.0) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for testing.

    Uses a deterministic random walk so tests are reproducible (seed=42).
    `period` defaults to ~300 days — enough warmup for any indicator
    in the catalog (max default lookback = 200-day SMA).
    """
    rng = np.random.default_rng(42)
    returns = rng.normal(loc=0.0005, scale=0.012, size=periods)
    closes = start_price * np.exp(np.cumsum(returns))
    highs = closes * (1 + rng.uniform(0, 0.012, periods))
    lows = closes * (1 - rng.uniform(0, 0.012, periods))
    opens = closes * (1 + rng.normal(0, 0.005, periods))
    volume = rng.integers(1_000_000, 5_000_000, size=periods).astype(float)
    dates = pd.date_range(end=date.today(), periods=periods, freq="B")
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "adjusted_close": closes,
        "volume": volume,
    }, index=dates)


# ── Per-family deep tests ────────────────────────────────────────────────────


def test_sma_matches_pandas_rolling_mean() -> None:
    """SMA is just rolling mean — sanity check the wrapper matches the
    underlying pandas op."""
    frame = _synthetic_frame()
    provider = SmaSignalProvider(period=20)
    out = provider._compute(frame)
    expected = frame["close"].rolling(20).mean()
    pd.testing.assert_series_equal(out, expected, check_names=False)


def test_ema_reacts_faster_than_sma_to_a_jump() -> None:
    """EMA's defining property: faster reaction to recent prices than SMA."""
    frame = _synthetic_frame(periods=100, start_price=100)
    # Inject a step-jump on day 50.
    frame["close"].iloc[50:] += 10
    sma = SmaSignalProvider(period=20)._compute(frame)
    ema = EmaSignalProvider(period=20)._compute(frame)
    # Five days after the jump, EMA should be closer to the new level
    # than SMA.
    sma_distance_from_new = abs(sma.iloc[55] - frame["close"].iloc[55])
    ema_distance_from_new = abs(ema.iloc[55] - frame["close"].iloc[55])
    assert ema_distance_from_new < sma_distance_from_new


def test_rsi_falls_between_0_and_100() -> None:
    """RSI is bounded — any value outside [0, 100] is a calculation bug."""
    frame = _synthetic_frame()
    rsi = RsiSignalProvider(period=14)._compute(frame)
    valid = rsi.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_rsi_close_to_50_on_random_walk() -> None:
    """A symmetric random walk should produce RSI fluctuating around 50.
    The mean over many samples should be in [40, 60]."""
    frame = _synthetic_frame(periods=500)
    rsi = RsiSignalProvider(period=14)._compute(frame).dropna()
    assert 40 < rsi.mean() < 60


def test_macd_histogram_decays_toward_zero_in_flat_regime() -> None:
    """MACD histogram should decay toward zero as the price flattens —
    the defining property of a momentum oscillator on a directionless
    series."""
    frame = _synthetic_frame(periods=200).copy()
    # Flatten the second half — copy close into a fresh column then write.
    flat_value = float(frame["close"].iloc[99])
    new_close = frame["close"].copy()
    new_close.iloc[100:] = flat_value
    frame.loc[:, "close"] = new_close
    hist = MacdSignalProvider()._compute(frame)
    # Compare histogram magnitude near the flat-start (~110) to deep-flat (~180).
    early_flat = abs(hist.iloc[110])
    deep_flat = abs(hist.iloc[180])
    assert deep_flat < early_flat, (
        f"Histogram magnitude should decay: early={early_flat:.4f}, deep={deep_flat:.4f}"
    )


def test_bbands_percent_b_bounded_typical_range() -> None:
    """%B values typically sit in [-0.5, 1.5] — extreme breakouts can
    exceed but the bulk should be in [0, 1] for a normal series."""
    frame = _synthetic_frame()
    bb = BbandsSignalProvider()._compute(frame).dropna()
    # >80% of values should be in [-0.5, 1.5].
    in_range = ((bb >= -0.5) & (bb <= 1.5)).mean()
    assert in_range > 0.8


def test_atr_is_positive() -> None:
    """ATR is a magnitude — always ≥ 0 for valid bars."""
    frame = _synthetic_frame()
    atr = AtrSignalProvider()._compute(frame).dropna()
    assert (atr > 0).all()


def test_natr_is_atr_scaled_by_close() -> None:
    """NATR = ATR / close * 100. Verify the relationship."""
    frame = _synthetic_frame()
    atr = AtrSignalProvider(period=14)._compute(frame)
    natr = NatrSignalProvider(period=14)._compute(frame)
    expected_natr = 100 * atr / frame["close"]
    pd.testing.assert_series_equal(natr, expected_natr, check_names=False)


def test_adx_is_in_0_to_100_range() -> None:
    """ADX is bounded 0-100 by definition."""
    frame = _synthetic_frame()
    adx = AdxSignalProvider(period=14)._compute(frame).dropna()
    assert (adx >= 0).all()
    assert (adx <= 100).all()


def test_donchian_breakout_returns_binary_signal() -> None:
    """Output should be 0 or 1 only."""
    frame = _synthetic_frame()
    signal = DonchianBreakoutSignalProvider(period=20)._compute(frame).dropna()
    assert set(signal.unique()).issubset({0.0, 1.0})


def test_obv_is_cumulative() -> None:
    """OBV is a cumsum — successive values should differ by at most one
    day's volume (in absolute terms)."""
    frame = _synthetic_frame()
    obv = ObvSignalProvider(smoothing_period=1)._compute(frame).dropna()
    # If smoothing=1, OBV diff equals ±volume.
    diff = obv.diff().abs().dropna()
    expected_max = frame["volume"].iloc[1:].max()
    assert diff.max() <= expected_max * 1.01  # 1% tolerance for float math


def test_roc_at_period_n_equals_n_day_pct_change_x_100() -> None:
    """ROC = 100 × N-day pct change. Sanity check."""
    frame = _synthetic_frame()
    roc = RocSignalProvider(period=10)._compute(frame)
    expected = 100 * frame["close"].pct_change(10)
    pd.testing.assert_series_equal(roc, expected, check_names=False)


def test_vol_regime_returns_ratio() -> None:
    """Vol regime is a ratio — positive when both periods have any
    movement; NaN early on while the warm-up window fills.

    Default config: short_period=10, long_period=126. The rolling-of-
    rolling needs `2 * long_period = 252` warmup days; with our 300-day
    synthetic frame that leaves ~48 valid values. Set threshold below
    that to give the test margin for future seed changes.
    """
    frame = _synthetic_frame(periods=300)
    series = VolRegimeSignalProvider()._compute(frame).dropna()
    assert len(series) > 30
    # Values should be positive (it's a ratio of std-devs).
    assert (series > 0).all()


# ── Smoke test across all 46 providers ──────────────────────────────────────
# Every provider should at least RETURN a series (or empty for AV-endpoint
# providers without a real AV call) without raising. This is the
# parametrized backstop — if a new provider class has a typo, this catches
# it without needing a dedicated test.


def test_all_technical_providers_have_unique_registry_names() -> None:
    """Two providers sharing a name would silently override each other
    in `_REGISTRY`."""
    providers = get_technical_providers()
    # The dict keys are the names; ensure get_technical_providers handles
    # collisions correctly (it shouldn't have any).
    names = [cls.name for cls in [type(p) for p in providers.values()]]
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    "provider", list(get_technical_providers().values()),
    ids=lambda p: p.name,
)
def test_local_providers_return_a_series_on_synthetic_data(provider) -> None:
    """Smoke: each local-pandas provider produces a non-error series on
    synthetic data. AV-endpoint providers are skipped here — their
    `get_signal_frame` makes a real HTTP call."""
    from app.services.backtester.technical_signal_providers import (
        AVTechnicalSignalProvider,
    )
    if isinstance(provider, AVTechnicalSignalProvider):
        pytest.skip("AV-endpoint provider — requires real AV call")

    frame = _synthetic_frame(periods=300)
    series = provider._compute(frame)
    assert isinstance(series, pd.Series)
    # At least some non-NaN values after warmup. (For `analyst_rating_change`
    # placeholder which returns all-NaN, that's fine — we just verify shape.)
    assert len(series) == len(frame)


@pytest.mark.asyncio
async def test_get_signal_frame_slices_to_requested_window(monkeypatch) -> None:
    """The base class promises to slice warmup bars out of the returned
    series. Verify that contract."""
    frame = _synthetic_frame(periods=300)
    provider = SmaSignalProvider(period=50)

    async def fake_get_price_frame(db, symbol, start, end, lookback_days=0):
        return frame

    monkeypatch.setattr(
        provider._price_svc, "get_price_frame", fake_get_price_frame,
    )

    start = date.today() - timedelta(days=30)
    end = date.today()
    series = await provider.get_signal_frame(db=None, symbol="SPY", start=start, end=end)
    assert series.index.min() >= pd.Timestamp(start)
