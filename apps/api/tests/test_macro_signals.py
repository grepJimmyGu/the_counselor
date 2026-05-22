"""Phase 1c — macro_signals_service tests.

Covers:
  * _trend_from_series direction classification (up / down / flat)
  * _build_rates_signal happy path with mocked AV TREASURY_YIELD
  * _build_inflation_signal happy path with mocked AV CPI (YoY% derivation)
  * Public get_macro_signals() returns 4 signals in the expected order
  * Fallback to _full_mock_* when AV raises
  * 24h cache: second call returns the same object identity
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import macro_signals_service as svc
from app.services.alpha_vantage import AlphaVantageError


# ── _trend_from_series ───────────────────────────────────────────────────────


def test_trend_up_when_latest_greater_than_median():
    direction, label = svc._trend_from_series([1.0, 1.1, 1.2, 1.3, 2.0])
    assert direction == "up"
    assert label == "Rising"


def test_trend_down_when_latest_less_than_median():
    direction, label = svc._trend_from_series([3.0, 2.9, 2.8, 2.7, 1.0])
    assert direction == "down"
    assert label == "Cooling"


def test_trend_flat_when_change_within_threshold():
    # latest = 1.001, median(prior) = 1.0 — 0.1% change, threshold 0.5%
    direction, label = svc._trend_from_series(
        [1.0, 1.0, 1.0, 1.0, 1.001], threshold=0.005
    )
    assert direction == "flat"
    assert label == "Stable"


def test_trend_flat_when_series_too_short():
    direction, label = svc._trend_from_series([4.30])
    assert direction == "flat"
    assert label == "Stable"


def test_trend_flat_when_prior_median_is_zero():
    # latest = 0.5, median(prior) = 0 — guarded against div-by-zero
    direction, label = svc._trend_from_series([0.0, 0.0, 0.0, 0.5])
    assert direction == "flat"


# ── _build_rates_signal ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_rates_signal_real_path():
    """AV returns 14 months of monthly 10Y data → real signal returned."""
    # 14 months so we get all three windows populated.
    fake_data = [
        {"date": f"2025-{m:02d}-01", "value": f"{4.0 + 0.05 * m:.2f}"}
        for m in range(1, 15)
    ]
    av = AsyncMock()
    av.fetch_treasury_yield = AsyncMock(return_value=fake_data)

    sig = await svc._build_rates_signal(av)

    assert sig.category == "Rates"
    assert sig.source == "alpha_vantage"
    # Latest is the 14th entry: 4.0 + 0.05 * 14 = 4.70
    assert sig.latestLabel == "10Y Yield: 4.70%"
    assert len(sig.series1Y) == 12
    assert len(sig.series1M) == 8  # flat-repeat of last value
    assert sig.series1M[-1] == 4.70
    # Series chronologically increasing → direction should be "up"
    assert sig.trendDirection == "up"
    assert sig.trendLabel == "Rising"


@pytest.mark.asyncio
async def test_build_rates_signal_drops_dots_and_nulls():
    """AV sometimes returns sentinel '.' values; service must skip them."""
    fake_data = [
        {"date": "2025-01-01", "value": "4.10"},
        {"date": "2025-02-01", "value": "."},     # sentinel
        {"date": "2025-03-01", "value": None},     # null
        {"date": "2025-04-01", "value": "4.30"},
    ]
    av = AsyncMock()
    av.fetch_treasury_yield = AsyncMock(return_value=fake_data)

    sig = await svc._build_rates_signal(av)
    # Only the two real values made it through.
    assert sig.series1M[-1] == 4.30


# ── _build_inflation_signal ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_inflation_signal_computes_yoy():
    """AV CPI is an INDEX series; service must derive YoY% per month."""
    # 24 months of monthly CPI index values, climbing from 300 → 311.5
    # YoY% over the last 12 entries = ((311.5 - 305.5) / 305.5) * 100 ≈ 1.96%.
    fake_data = [
        {"date": f"2024-{((i - 1) % 12) + 1:02d}-01", "value": f"{300 + 0.5 * i:.2f}"}
        for i in range(1, 25)
    ]
    av = AsyncMock()
    av.fetch_cpi = AsyncMock(return_value=fake_data)

    sig = await svc._build_inflation_signal(av)

    assert sig.category == "Inflation"
    assert sig.source == "alpha_vantage"
    assert sig.latestLabel.startswith("CPI YoY: ")
    # The YoY% should be ~2.0%, NOT the raw index 311.5.
    assert "1." in sig.latestLabel or "2." in sig.latestLabel
    assert "311" not in sig.latestLabel


# ── Public API: get_macro_signals ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_macro_signals_returns_four_signals_in_order():
    """Service always returns exactly 4 signals: Growth / Inflation / Rates / Stress."""
    svc.invalidate_cache()
    # Mock both real-data calls so we don't hit AV.
    fake_treasury = [
        {"date": f"2025-{m:02d}-01", "value": f"{4.0 + 0.01 * m:.2f}"}
        for m in range(1, 15)
    ]
    fake_cpi = [
        {"date": f"2024-{((i - 1) % 12) + 1:02d}-01", "value": f"{300 + 0.4 * i:.2f}"}
        for i in range(1, 25)
    ]

    with patch.object(
        svc.AlphaVantageClient, "fetch_treasury_yield",
        new=AsyncMock(return_value=fake_treasury),
    ), patch.object(
        svc.AlphaVantageClient, "fetch_cpi",
        new=AsyncMock(return_value=fake_cpi),
    ):
        signals = await svc.get_macro_signals()

    assert len(signals) == 4
    assert [s.category for s in signals] == [
        "Growth", "Inflation", "Rates", "Stress",
    ]
    # Real signals
    assert signals[1].source == "alpha_vantage"  # Inflation
    assert signals[2].source == "alpha_vantage"  # Rates
    # Mocked (pending FRED)
    assert signals[0].source == "mock_pending_fred"  # Growth
    assert signals[3].source == "mock_pending_fred"  # Stress


@pytest.mark.asyncio
async def test_get_macro_signals_falls_back_when_av_errors():
    """If AV raises, the service substitutes the full-mock signal so the
    page never errors."""
    svc.invalidate_cache()
    with patch.object(
        svc.AlphaVantageClient, "fetch_treasury_yield",
        new=AsyncMock(side_effect=AlphaVantageError("rate limit")),
    ), patch.object(
        svc.AlphaVantageClient, "fetch_cpi",
        new=AsyncMock(side_effect=AlphaVantageError("rate limit")),
    ):
        signals = await svc.get_macro_signals()

    assert len(signals) == 4
    assert signals[1].source == "mock_av_failed"
    assert signals[2].source == "mock_av_failed"


@pytest.mark.asyncio
async def test_get_macro_signals_cache_round_trip():
    """Second invocation within TTL returns the same list (cached)."""
    svc.invalidate_cache()
    fake_treasury = [
        {"date": f"2025-{m:02d}-01", "value": "4.30"}
        for m in range(1, 15)
    ]
    fake_cpi = [
        {"date": f"2024-{((i - 1) % 12) + 1:02d}-01", "value": f"{300 + 0.3 * i:.2f}"}
        for i in range(1, 25)
    ]

    with patch.object(
        svc.AlphaVantageClient, "fetch_treasury_yield",
        new=AsyncMock(return_value=fake_treasury),
    ) as t_mock, patch.object(
        svc.AlphaVantageClient, "fetch_cpi",
        new=AsyncMock(return_value=fake_cpi),
    ) as c_mock:
        first = await svc.get_macro_signals()
        second = await svc.get_macro_signals()

    # Both calls returned the same payload (same Python identity)
    assert first is second
    # Real-data fetchers were called exactly once across the two service calls
    assert t_mock.call_count == 1
    assert c_mock.call_count == 1


def test_invalidate_cache_clears_module_state():
    """`invalidate_cache()` clears the module-level cache singleton."""
    svc._CACHE = (svc.datetime.utcnow(), [])
    svc.invalidate_cache()
    assert svc._CACHE is None
