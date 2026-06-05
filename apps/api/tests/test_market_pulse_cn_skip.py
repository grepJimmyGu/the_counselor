"""Regression tests for the CN Market Pulse FMP-overlay skip.

**2026-06-05 perf fix.** `get_live_pulse("CN", db)` was issuing serial
`live_quote_service.get_quotes(...)` calls against the full CN universe,
but FMP doesn't carry `.SZ` / `.SS` tickers — every call returned empty
/ 404 after a network round-trip. That added 15-25s of pure latency to
every CN cold-cache request (the full cold path measured 78-110s in
production).

**Fix.** `get_live_pulse` now early-returns for `market == "CN"`,
caching the EOD `get_pulse()` snapshot directly into `_LIVE_CACHE` so
subsequent calls hit the 1.75s warm path instead of repeating wasted
overlay work.

These tests pin the post-fix invariants:
  - CN: no FMP HTTP call fires
  - CN: response is cached so the next call returns the same object
  - US: regression bar — overlay still fires (the fix is CN-only)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_pulse_service import (
    AssetCard,
    IndexCard,
    MacroCard,
    MarketPulseResponse,
    MarketPulseService,
    SectorCard,
    _CACHE,
    _LIVE_CACHE,
)


def _fake_pulse(market: str) -> MarketPulseResponse:
    """Minimal base MarketPulseResponse for stubbing `get_pulse`."""
    return MarketPulseResponse(
        market=market,
        as_of=datetime(2026, 6, 5, 12, 0, 0).isoformat(),
        indices=[
            IndexCard(
                symbol="000001.SS",
                name="SSE Composite",
                price=3200.0,
                perf_1d=0.4,
                perf_5d=1.1,
                sparkline_5d=[3170.0, 3180.0, 3185.0, 3190.0, 3200.0],
                latest_date="2026-06-04",
                is_stale=False,
            ),
        ],
        macro=[],
        sectors=[],
        top_assets=[
            AssetCard(
                symbol="300747.SZ",
                name="Mock A-share",
                sector=None,
                price=50.0,
                perf_1d=0.5,
                cmf_20=0.1,
                market_cap=None,
                latest_date="2026-06-04",
                is_stale=False,
            ),
        ],
        featured_etfs=[],
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    """Each test starts from a clean cache so prior tests don't bleed in."""
    _CACHE.clear()
    _LIVE_CACHE.clear()
    yield
    _CACHE.clear()
    _LIVE_CACHE.clear()


class _FakeDB:
    """Stand-in for `Session` — `get_live_pulse` doesn't touch the DB
    when `get_pulse` is mocked, so we just need any object to pass in."""
    pass


@pytest.mark.asyncio
async def test_cn_get_live_pulse_skips_fmp_overlay() -> None:
    """The fix: no `live_quote_service.get_quotes` call fires for CN."""
    svc = MarketPulseService()
    fake_db = _FakeDB()

    with patch.object(svc, "get_pulse", return_value=_fake_pulse("CN")) as mock_pulse, \
         patch(
             "app.services.market_pulse_service.live_quote_service.get_quotes",
             new_callable=AsyncMock,
         ) as mock_get_quotes:
        result = await svc.get_live_pulse("CN", fake_db)

    assert result.market == "CN"
    mock_pulse.assert_called_once_with("CN", fake_db)
    mock_get_quotes.assert_not_called(), (
        "CN must skip live_quote_service.get_quotes — FMP has no CN data and "
        "the call was adding 15-25s of pure latency. If this assertion fails, "
        "the regression has come back."
    )


@pytest.mark.asyncio
async def test_cn_get_live_pulse_caches_base_response() -> None:
    """Subsequent CN calls within TTL hit `_LIVE_CACHE` — `get_pulse` runs
    once, not twice. This is what converts CN from 80s cold to ~2s warm."""
    svc = MarketPulseService()
    fake_db = _FakeDB()

    with patch.object(svc, "get_pulse", return_value=_fake_pulse("CN")) as mock_pulse, \
         patch(
             "app.services.market_pulse_service.live_quote_service.get_quotes",
             new_callable=AsyncMock,
         ):
        r1 = await svc.get_live_pulse("CN", fake_db)
        r2 = await svc.get_live_pulse("CN", fake_db)

    assert r1 is r2, "second call must return the cached object, not recompute"
    assert mock_pulse.call_count == 1, (
        f"get_pulse should have run once (cache miss → cache hit); ran "
        f"{mock_pulse.call_count} times"
    )
    assert "CN" in _LIVE_CACHE, "CN base response must populate _LIVE_CACHE"


@pytest.mark.asyncio
async def test_us_get_live_pulse_still_calls_fmp_overlay(db) -> None:
    """Regression bar: the CN skip is CN-only — US must still run the
    live quote overlay. If this fails, the if-CN check is over-broad.

    Uses the real `db` fixture because the US path's post-overlay
    `_apply_live_quotes_to_pulse` reaches into `price_bars` (an empty
    DB is fine — cards just don't get enriched, but the FMP call still
    fires)."""
    us_pulse = _fake_pulse("US")
    us_pulse.indices[0].symbol = "SPY"
    us_pulse.top_assets[0].symbol = "AAPL"

    svc = MarketPulseService()

    with patch.object(svc, "get_pulse", return_value=us_pulse), \
         patch(
             "app.services.market_pulse_service.live_quote_service.get_quotes",
             new_callable=AsyncMock,
             return_value={},  # empty quotes dict — overlay path still runs
         ) as mock_get_quotes:
        await svc.get_live_pulse("US", db)

    mock_get_quotes.assert_called_once(), (
        "US must still call live_quote_service.get_quotes — FMP does carry "
        "US symbols and the overlay produces real enrichment. If this fails, "
        "the CN-skip early-return is matching US too."
    )
