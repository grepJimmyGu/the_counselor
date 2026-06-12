"""FMP intraday bars — the live-data source for the active-execution monitor
(2026-06-12). FMP serves fresh intraday DURING market hours on our plan,
unlike AV's plain TIME_SERIES_INTRADAY (which lags a session intraday
without the realtime entitlement our key lacks).

Mocks `FMPClient._get` — no network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.fmp_client import FMPClient, FMPError


def _row(date: str, close: float) -> dict:
    return {
        "date": date,
        "open": close - 0.5,
        "low": close - 1.0,
        "high": close + 1.0,
        "close": close,
        "volume": 1000.0,
    }


@pytest.mark.asyncio
async def test_parses_sorts_oldest_to_newest() -> None:
    fmp = FMPClient()
    # FMP returns newest-first.
    fmp._get = AsyncMock(return_value=[
        _row("2026-06-11 15:45:00", 1.2),
        _row("2026-06-11 15:30:00", 1.1),
    ])
    bars = await fmp.fetch_intraday_bars("msft", "15min", "compact")
    assert [b["bar_time"].strftime("%H:%M") for b in bars] == ["15:30", "15:45"]
    assert bars[-1]["close"] == 1.2
    assert bars[-1]["high"] == pytest.approx(2.2)
    assert bars[-1]["low"] == pytest.approx(0.2)
    # Hit the right path; symbol upper-cased.
    fmp._get.assert_awaited_once()
    assert fmp._get.call_args[0][0] == "/historical-chart/15min"
    assert fmp._get.call_args[0][1] == {"symbol": "MSFT"}


@pytest.mark.asyncio
async def test_60min_maps_to_fmp_1hour() -> None:
    fmp = FMPClient()
    fmp._get = AsyncMock(return_value=[_row("2026-06-11 15:00:00", 1.0)])
    await fmp.fetch_intraday_bars("msft", "60min")
    assert fmp._get.call_args[0][0] == "/historical-chart/1hour"


@pytest.mark.asyncio
async def test_compact_caps_to_120_bars() -> None:
    fmp = FMPClient()
    fmp._get = AsyncMock(return_value=[
        _row(f"2026-06-11 {9 + i // 60:02d}:{i % 60:02d}:00", 1.0)
        for i in range(400)
    ])
    bars = await fmp.fetch_intraday_bars("msft", "5min", "compact")
    assert len(bars) == 120


@pytest.mark.asyncio
async def test_invalid_interval_raises() -> None:
    fmp = FMPClient()
    with pytest.raises(FMPError, match="Invalid intraday interval"):
        await fmp.fetch_intraday_bars("msft", "2min")


@pytest.mark.asyncio
async def test_empty_response_raises() -> None:
    fmp = FMPClient()
    fmp._get = AsyncMock(return_value=[])
    with pytest.raises(FMPError, match="No intraday data"):
        await fmp.fetch_intraday_bars("msft", "15min")


@pytest.mark.asyncio
async def test_skips_unparseable_rows() -> None:
    fmp = FMPClient()
    fmp._get = AsyncMock(return_value=[
        _row("2026-06-11 15:45:00", 1.2),
        {"date": "garbage", "open": 1, "low": 1, "high": 1, "close": 1, "volume": 1},
        {"date": "2026-06-11 15:30:00"},  # missing OHLCV keys
    ])
    bars = await fmp.fetch_intraday_bars("msft", "15min")
    assert len(bars) == 1
    assert bars[0]["close"] == 1.2
