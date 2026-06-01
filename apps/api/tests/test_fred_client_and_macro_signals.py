"""Tests for FREDClient + macro_signals_service FRED integration.

No live FRED calls — every test mocks `FREDClient.fetch_series` or the
underlying httpx.AsyncClient. Two layers:

  1. FREDClient unit tests — HTTP shape, error handling, value cleanup.
  2. macro_signals_service integration — the two new builders
     (`_build_growth_signal`, `_build_stress_signal`) on mocked FRED
     payloads + fallback behaviour when FRED raises.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.fred_client import FREDClient, FREDError
from app.services.macro_signals_service import (
    MacroSignal,
    _build_growth_signal,
    _build_stress_signal,
    get_macro_signals,
    invalidate_cache,
)


# ── FREDClient unit tests ────────────────────────────────────────────────────


def _make_fred_client_with_key(key: str = "test-key") -> FREDClient:
    """Return a client whose settings.fred_api_key is set to `key`."""
    client = FREDClient.__new__(FREDClient)
    client.settings = MagicMock()
    client.settings.fred_api_key = key
    client.settings.api_timeout_seconds = 20.0
    return client


def test_fred_client_missing_key_raises():
    client = _make_fred_client_with_key("")
    with pytest.raises(FREDError, match="not configured"):
        asyncio.run(client.fetch_series("CFNAI"))


def test_fred_client_cleans_value_sentinels():
    """FRED reports missing data as `.`. The client filters those out."""
    client = _make_fred_client_with_key()
    raw_observations = [
        {"date": "2026-01-01", "value": "0.12"},
        {"date": "2026-02-01", "value": "."},        # missing
        {"date": "2026-03-01", "value": "-0.45"},
        {"date": "2026-04-01", "value": ""},         # empty
        {"date": "2026-05-01", "value": "NaN"},      # explicit NaN
        {"date": "2026-06-01", "value": "0.08"},
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"observations": raw_observations}

    mock_async_client = MagicMock()
    mock_async_client.get = AsyncMock(return_value=mock_response)
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.fred_client.httpx.AsyncClient", return_value=mock_async_client):
        result = asyncio.run(client.fetch_series("CFNAI"))

    assert len(result) == 3
    assert result[0] == {"date": date(2026, 1, 1), "value": 0.12}
    assert result[1] == {"date": date(2026, 3, 1), "value": -0.45}
    assert result[2] == {"date": date(2026, 6, 1), "value": 0.08}


def test_fred_client_400_surfaces_body():
    """A bad series_id or expired key returns HTTP 400; client raises
    with the response body so the log is actionable."""
    client = _make_fred_client_with_key()
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request. The series does not exist."

    mock_async_client = MagicMock()
    mock_async_client.get = AsyncMock(return_value=mock_response)
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.fred_client.httpx.AsyncClient", return_value=mock_async_client):
        with pytest.raises(FREDError, match="HTTP 400"):
            asyncio.run(client.fetch_series("INVALID_SERIES"))


def test_fred_client_empty_observations_raises():
    """A 200 with empty `observations` array is treated as a failure
    (caller falls back to mock)."""
    client = _make_fred_client_with_key()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"observations": []}

    mock_async_client = MagicMock()
    mock_async_client.get = AsyncMock(return_value=mock_response)
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.fred_client.httpx.AsyncClient", return_value=mock_async_client):
        with pytest.raises(FREDError, match="no observations"):
            asyncio.run(client.fetch_series("CFNAI"))


# ── macro_signals_service: _build_growth_signal ─────────────────────────────


def test_growth_signal_positive_cfnai_labels_expanding():
    """CFNAI of +0.34 with rising trend → label "Improving", takeaway about
    above-trend expansion."""
    fred = MagicMock(spec=FREDClient)
    # 40 months of slowly improving values, last point +0.34.
    values = [-0.15 + i * 0.012 for i in range(40)]
    fred.fetch_series = AsyncMock(
        return_value=[{"date": date(2023, 1, 1), "value": v} for v in values]
    )

    signal = asyncio.run(_build_growth_signal(fred))

    assert signal.category == "Growth"
    assert signal.source == "fred"
    assert "CFNAI" in signal.latestLabel
    assert signal.latestLabel.startswith("CFNAI: +")  # positive sign formatting
    assert len(signal.series5Y) >= 36
    assert len(signal.series1Y) == 12
    assert signal.series5Y[-1] > 0  # last value is the positive end of the ramp
    assert signal.takeaway in (
        "Economy expanding above trend",
        "Economy holding above trend",
    )


def test_growth_signal_negative_cfnai_labels_slowing():
    """CFNAI below -0.3 with downtrend → "Slowing" label, contraction
    takeaway."""
    fred = MagicMock(spec=FREDClient)
    # Sliding into negative territory: last point ~-0.45.
    values = [0.2 - i * 0.015 for i in range(40)]
    fred.fetch_series = AsyncMock(
        return_value=[{"date": date(2023, 1, 1), "value": v} for v in values]
    )

    signal = asyncio.run(_build_growth_signal(fred))

    assert signal.source == "fred"
    assert signal.trendLabel == "Slowing"
    assert "below trend" in signal.takeaway.lower() or "slowdown" in signal.takeaway.lower()


def test_growth_signal_empty_fred_response_raises():
    """When FRED returns nothing useful, the builder raises so the caller
    falls back to the mock."""
    fred = MagicMock(spec=FREDClient)
    fred.fetch_series = AsyncMock(return_value=[])
    with pytest.raises(FREDError):
        asyncio.run(_build_growth_signal(fred))


# ── macro_signals_service: _build_stress_signal ─────────────────────────────


def test_stress_signal_low_spread_labels_risk_on():
    """HY OAS below 4% → "risk-on" takeaway."""
    fred = MagicMock(spec=FREDClient)
    # 90 daily observations spanning ~3 months across calendar months.
    # Last value 3.4% — comfortably risk-on.
    obs = []
    for i in range(90):
        obs.append({
            "date": date(2026, 1, 1).replace(day=min(i % 28 + 1, 28)),
            "value": 3.4 + 0.01 * (i % 5),
        })
    fred.fetch_series = AsyncMock(return_value=obs)

    signal = asyncio.run(_build_stress_signal(fred))

    assert signal.category == "Stress"
    assert signal.source == "fred"
    assert "HY Spread" in signal.latestLabel
    assert "%" in signal.latestLabel
    assert signal.takeaway == "Credit risk contained"


def test_stress_signal_elevated_spread_labels_stressed():
    """HY OAS above 6% → "Stressed" label, risk-off takeaway."""
    fred = MagicMock(spec=FREDClient)
    # Spreads marching from 5% up to 7.5% over time.
    obs = []
    for i in range(60):
        obs.append({
            "date": date(2025, 1, 1).replace(day=min(i % 28 + 1, 28)),
            "value": 5.0 + i * 0.05,
        })
    # Push the final monthly downsample value above 6.0 deliberately.
    obs.append({"date": date(2026, 5, 28), "value": 7.5})
    fred.fetch_series = AsyncMock(return_value=obs)

    signal = asyncio.run(_build_stress_signal(fred))

    assert signal.source == "fred"
    assert signal.trendLabel == "Stressed"
    assert "risk-off" in signal.takeaway.lower() or "stress" in signal.takeaway.lower()


def test_stress_signal_downsamples_daily_to_monthly():
    """Daily series of varying values should downsample to ONE value per
    calendar month (the last value of each month wins)."""
    fred = MagicMock(spec=FREDClient)
    obs = [
        # Three observations in Jan 2026; last (3.5) should win.
        {"date": date(2026, 1, 3),  "value": 3.0},
        {"date": date(2026, 1, 20), "value": 3.2},
        {"date": date(2026, 1, 31), "value": 3.5},
        # Two in Feb; last (3.7) should win.
        {"date": date(2026, 2, 5),  "value": 3.6},
        {"date": date(2026, 2, 28), "value": 3.7},
        # One in March.
        {"date": date(2026, 3, 15), "value": 3.8},
    ]
    fred.fetch_series = AsyncMock(return_value=obs)

    signal = asyncio.run(_build_stress_signal(fred))

    # Three calendar months → three monthly points in series5Y (trimmed
    # to 36, which we have fewer than).
    assert signal.series5Y == [3.5, 3.7, 3.8]
    assert signal.series1Y == [3.5, 3.7, 3.8]
    assert signal.latestLabel == "HY Spread: 3.80%"


# ── get_macro_signals end-to-end with both real + fallback paths ────────────


def test_get_macro_signals_fred_failure_falls_back_to_mock_growth_and_stress():
    """If FRED is unset / unreachable, Growth + Stress should fall back to
    their respective mocks WITHOUT poisoning the AV-backed signals."""
    invalidate_cache()

    # Mock all 4 builders so the test is hermetic.
    async def _raises_fred(*_args, **_kwargs):
        raise FREDError("FRED unreachable in test")

    async def _fake_inflation(*_args, **_kwargs):
        return MacroSignal(
            category="Inflation",
            latestLabel="CPI YoY: 3.4%",
            trendDirection="down",
            trendLabel="Cooling",
            takeaway="Supports future rate cuts",
            explanation="test",
            series6M=[3.4] * 8,
            series1Y=[3.4] * 12,
            series5Y=[3.4] * 36,
            source="alpha_vantage",
        )

    async def _fake_rates(*_args, **_kwargs):
        return MacroSignal(
            category="Rates",
            latestLabel="10Y Yield: 4.30%",
            trendDirection="up",
            trendLabel="Rising",
            takeaway="Headwind for growth stocks",
            explanation="test",
            series6M=[4.3] * 8,
            series1Y=[4.3] * 12,
            series5Y=[4.3] * 36,
            source="alpha_vantage",
        )

    with patch("app.services.macro_signals_service._build_growth_signal", _raises_fred), \
         patch("app.services.macro_signals_service._build_inflation_signal", _fake_inflation), \
         patch("app.services.macro_signals_service._build_rates_signal", _fake_rates), \
         patch("app.services.macro_signals_service._build_stress_signal", _raises_fred):
        signals = asyncio.run(get_macro_signals())

    assert len(signals) == 4
    by_cat = {s.category: s for s in signals}
    # FRED-backed pills fell back to mock
    assert by_cat["Growth"].source == "mock_pending_fred"
    assert by_cat["Stress"].source == "mock_pending_fred"
    # AV-backed pills came through
    assert by_cat["Inflation"].source == "alpha_vantage"
    assert by_cat["Rates"].source == "alpha_vantage"


def test_get_macro_signals_fred_success_uses_real_growth_and_stress():
    """When both FRED builders succeed, Growth and Stress sources are 'fred'."""
    invalidate_cache()

    async def _fake_growth(*_args, **_kwargs):
        return MacroSignal(
            category="Growth", latestLabel="CFNAI: +0.20", trendDirection="up",
            trendLabel="Improving", takeaway="Economy expanding above trend",
            explanation="test", series6M=[0.2] * 8, series1Y=[0.2] * 12,
            series5Y=[0.2] * 36, source="fred",
        )

    async def _fake_stress(*_args, **_kwargs):
        return MacroSignal(
            category="Stress", latestLabel="HY Spread: 3.40%", trendDirection="flat",
            trendLabel="Stable", takeaway="Credit risk contained",
            explanation="test", series6M=[3.4] * 8, series1Y=[3.4] * 12,
            series5Y=[3.4] * 36, source="fred",
        )

    async def _fake_inflation(*_args, **_kwargs):
        return MacroSignal(
            category="Inflation", latestLabel="x", trendDirection="flat",
            trendLabel="Stable", takeaway="x", explanation="x",
            series6M=[1.0] * 8, series1Y=[1.0] * 12, series5Y=[1.0] * 36,
            source="alpha_vantage",
        )

    async def _fake_rates(*_args, **_kwargs):
        return MacroSignal(
            category="Rates", latestLabel="x", trendDirection="flat",
            trendLabel="Stable", takeaway="x", explanation="x",
            series6M=[1.0] * 8, series1Y=[1.0] * 12, series5Y=[1.0] * 36,
            source="alpha_vantage",
        )

    with patch("app.services.macro_signals_service._build_growth_signal", _fake_growth), \
         patch("app.services.macro_signals_service._build_inflation_signal", _fake_inflation), \
         patch("app.services.macro_signals_service._build_rates_signal", _fake_rates), \
         patch("app.services.macro_signals_service._build_stress_signal", _fake_stress):
        signals = asyncio.run(get_macro_signals())

    by_cat = {s.category: s for s in signals}
    assert by_cat["Growth"].source == "fred"
    assert by_cat["Stress"].source == "fred"
    assert by_cat["Growth"].latestLabel == "CFNAI: +0.20"
    assert by_cat["Stress"].latestLabel == "HY Spread: 3.40%"
