"""PRD-16c-1 — IntradayBarService tests.

Mocks the AV client to avoid hitting the real intraday endpoint. The
test DB is the standard in-memory SQLite from conftest.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.models.intraday_bar import IntradayBar
from app.services.alpha_vantage import AlphaVantageError
from app.services.intraday_bar_service import (
    VALID_RESOLUTIONS,
    IntradayBarService,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _av_bar(bar_time: datetime, close: float = 100.0) -> dict:
    return {
        "bar_time": bar_time,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 10_000.0,
    }


def _make_service(av_bars: list[dict]) -> IntradayBarService:
    """Service with a mocked AV client returning the given bars."""
    client = AsyncMock()
    client.fetch_intraday_bars = AsyncMock(return_value=av_bars)
    return IntradayBarService(client=client)


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_bars_rejects_invalid_resolution(db: Session) -> None:
    svc = _make_service([])
    with pytest.raises(ValueError, match="Invalid resolution"):
        await svc.get_bars(db, "SPY", "1min", datetime.utcnow() - timedelta(hours=1), datetime.utcnow())


@pytest.mark.asyncio
async def test_ensure_recent_bars_rejects_invalid_resolution(db: Session) -> None:
    svc = _make_service([])
    with pytest.raises(ValueError, match="Invalid resolution"):
        await svc.ensure_recent_bars(db, "SPY", "1min")


def test_valid_resolutions_constant_matches_av_supported() -> None:
    assert VALID_RESOLUTIONS == {"5min", "15min", "30min", "60min"}


# ── Fetch + cache behavior ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_bars_fetches_from_av_on_empty_cache(db: Session) -> None:
    now = datetime.utcnow().replace(microsecond=0)
    bars = [
        _av_bar(now - timedelta(minutes=30 + 15 * i), close=100 + i)
        for i in range(5)
    ]
    svc = _make_service(bars)
    result = await svc.get_bars(
        db, "SPY", "15min", now - timedelta(hours=2), now,
    )
    assert not result.empty
    assert len(result) == 5
    # Bars persisted to the cache.
    cached = db.query(IntradayBar).filter(IntradayBar.symbol == "SPY").all()
    assert len(cached) == 5


@pytest.mark.asyncio
async def test_get_bars_returns_empty_when_av_fails_with_empty_cache(
    db: Session,
) -> None:
    client = AsyncMock()
    client.fetch_intraday_bars = AsyncMock(
        side_effect=AlphaVantageError("rate limit"),
    )
    svc = IntradayBarService(client=client)
    result = await svc.get_bars(
        db, "SPY", "15min",
        datetime.utcnow() - timedelta(hours=1), datetime.utcnow(),
    )
    assert result.empty


@pytest.mark.asyncio
async def test_get_bars_returns_stale_cache_when_av_fails(db: Session) -> None:
    """If AV fails but we have cached bars, return them — better stale
    data than empty data."""
    now = datetime.utcnow().replace(microsecond=0)
    db.add_all([
        IntradayBar(
            symbol="SPY", resolution="15min",
            bar_time=now - timedelta(minutes=15 * i),
            open=100, high=101, low=99, close=100 + i, volume=10_000,
        )
        for i in range(1, 6)
    ])
    db.commit()

    client = AsyncMock()
    client.fetch_intraday_bars = AsyncMock(
        side_effect=AlphaVantageError("server down"),
    )
    svc = IntradayBarService(client=client)
    result = await svc.get_bars(
        db, "SPY", "15min", now - timedelta(hours=2), now,
    )
    # The cache had 5 bars; AV failed; we return what we have.
    assert not result.empty
    assert len(result) == 5


@pytest.mark.asyncio
async def test_get_bars_writes_idempotently_no_duplicates(db: Session) -> None:
    """Calling twice with the same data should produce one row per bar,
    not two."""
    now = datetime.utcnow().replace(microsecond=0)
    bars = [_av_bar(now - timedelta(minutes=15 * i)) for i in range(3)]
    svc = _make_service(bars)
    await svc.get_bars(db, "SPY", "15min", now - timedelta(hours=1), now)
    await svc.get_bars(db, "SPY", "15min", now - timedelta(hours=1), now)
    cached = db.query(IntradayBar).filter(IntradayBar.symbol == "SPY").all()
    assert len(cached) == 3


@pytest.mark.asyncio
async def test_get_bars_uppercases_symbol(db: Session) -> None:
    now = datetime.utcnow().replace(microsecond=0)
    svc = _make_service([_av_bar(now - timedelta(minutes=15))])
    await svc.get_bars(db, "nvda", "15min", now - timedelta(hours=1), now)
    cached = db.query(IntradayBar).filter(IntradayBar.symbol == "NVDA").all()
    assert len(cached) == 1


@pytest.mark.asyncio
async def test_get_bars_returns_dataframe_indexed_by_bar_time(db: Session) -> None:
    now = datetime.utcnow().replace(microsecond=0)
    bars = [_av_bar(now - timedelta(minutes=15 * i)) for i in range(3)]
    svc = _make_service(bars)
    result = await svc.get_bars(db, "SPY", "15min", now - timedelta(hours=1), now)
    assert isinstance(result, pd.DataFrame)
    assert isinstance(result.index, pd.DatetimeIndex)
    # Columns match the contract.
    assert set(result.columns) == {"open", "high", "low", "close", "volume"}


# ── Resolution-specific behavior ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_needs_fetch_when_cache_is_stale_for_resolution(db: Session) -> None:
    """If the latest cached bar is older than 2 * resolution minutes
    behind end, we should refetch. Verify by writing a stale cache + a
    fresh AV response and confirming AV was called."""
    now = datetime.utcnow().replace(microsecond=0)
    # Stale cache: 2 hours old for a 5-min resolution → very stale.
    db.add_all([
        IntradayBar(
            symbol="SPY", resolution="5min",
            bar_time=now - timedelta(hours=2 + i * 0.05),
            open=100, high=101, low=99, close=100, volume=10_000,
        )
        for i in range(3)
    ])
    db.commit()

    fresh_bars = [_av_bar(now - timedelta(minutes=5 * i)) for i in range(3)]
    svc = _make_service(fresh_bars)
    await svc.get_bars(db, "SPY", "5min", now - timedelta(hours=3), now)
    # AV called because cache was stale.
    svc._client.fetch_intraday_bars.assert_called_once()


# ── ensure_recent_bars (monitor path) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_recent_bars_always_fetches(db: Session) -> None:
    """Monitor cron path: even with fresh cache, we always re-fetch."""
    now = datetime.utcnow().replace(microsecond=0)
    # Fresh cache.
    db.add_all([
        IntradayBar(
            symbol="SPY", resolution="5min",
            bar_time=now - timedelta(minutes=5 * i),
            open=100, high=101, low=99, close=100, volume=10_000,
        )
        for i in range(1, 4)
    ])
    db.commit()

    fresh = [_av_bar(now - timedelta(minutes=5 * i)) for i in range(3)]
    svc = _make_service(fresh)
    result = await svc.ensure_recent_bars(db, "SPY", "5min", lookback_minutes=60)
    # AV called even though cache exists.
    svc._client.fetch_intraday_bars.assert_called_once()
    assert not result.empty


@pytest.mark.asyncio
async def test_ensure_recent_bars_returns_empty_on_av_failure(db: Session) -> None:
    client = AsyncMock()
    client.fetch_intraday_bars = AsyncMock(
        side_effect=AlphaVantageError("rate limit"),
    )
    svc = IntradayBarService(client=client)
    result = await svc.ensure_recent_bars(db, "SPY", "15min")
    assert result.empty
