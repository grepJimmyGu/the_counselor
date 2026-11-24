"""Price history: one refresh shared by everyone, and only the years asked for.

Measured in production on 2026-11-20:

  six watchlist loads at once, four symbols more than three days behind
      39 s for each, and the health check held up for 3 s
  /api/data/daily/AMD
      1.2 MB, 6,802 rows back to 1999, for a chart that reads five years

Cause of the first: `ensure_display_fresh` downloaded a symbol's whole
history inside every request that found it behind, so six requests made the
same four downloads six times, and a symbol that could not be brought up to
date (the morning after a long weekend) was retried on every request.
Cause of the second: the endpoint declared `start` and never used it.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import List

import pytest
from sqlalchemy.orm import Session

from app.models.price_bar import PriceBar
from app.services import market_data
from app.services.market_data import MarketDataService


def _bar(symbol: str, day: date, close: float = 10.0) -> PriceBar:
    return PriceBar(symbol=symbol, trading_date=day, open=close, high=close, low=close, close=close,
                    adjusted_close=close, volume=1, dividend_amount=0.0, split_coefficient=1.0,
                    source="test", fetched_at=datetime.utcnow())


@pytest.fixture(autouse=True)
def _forget_attempts():
    market_data._display_refresh_attempts.clear()
    yield
    market_data._display_refresh_attempts.clear()


@pytest.fixture
def service(monkeypatch):
    svc = MarketDataService()
    refreshes: List[str] = []

    async def fake_ensure_history(db, symbol, required_from, required_through=None, force=False):
        refreshes.append(symbol)
        await asyncio.sleep(0.01)

    monkeypatch.setattr(svc._price_data.cache_svc, "ensure_history", fake_ensure_history)
    svc.refreshes = refreshes  # type: ignore[attr-defined]
    return svc


async def test_six_requests_for_a_symbol_that_is_behind_refresh_it_once(service, db: Session) -> None:
    db.add(_bar("XOM", date.today() - timedelta(days=10)))
    db.commit()
    await asyncio.gather(*(service.ensure_display_fresh(db, "xom") for _ in range(6)))
    assert service.refreshes == ["XOM"]


async def test_a_symbol_that_stays_behind_is_not_refreshed_again_for_ten_minutes(service, db: Session, monkeypatch) -> None:
    """The morning after a long weekend every symbol is 'more than three days
    behind' until the close, and no download can change that."""
    db.add(_bar("XOM", date.today() - timedelta(days=4)))
    db.commit()
    now = {"t": 100.0}
    # The module's own clock, not time.monotonic: the event loop runs on that.
    monkeypatch.setattr(market_data, "_now", lambda: now["t"])

    await service.ensure_display_fresh(db, "XOM")
    await service.ensure_display_fresh(db, "XOM")
    now["t"] += 599
    await service.ensure_display_fresh(db, "XOM")
    assert service.refreshes == ["XOM"]

    now["t"] += 2
    await service.ensure_display_fresh(db, "XOM")
    assert service.refreshes == ["XOM", "XOM"]


async def test_a_symbol_that_is_up_to_date_is_never_refreshed(service, db: Session) -> None:
    db.add(_bar("AAPL", date.today() - timedelta(days=3)))
    db.commit()
    await service.ensure_display_fresh(db, "AAPL")
    assert service.refreshes == []


async def test_a_symbol_with_no_history_is_refreshed(service, db: Session) -> None:
    await service.ensure_display_fresh(db, "NEWCO")
    assert service.refreshes == ["NEWCO"]


async def test_a_failed_refresh_still_serves_what_is_cached(service, db: Session, monkeypatch) -> None:
    async def broken(*_args, **_kwargs):
        raise RuntimeError("Alpha Vantage is down")

    monkeypatch.setattr(service._price_data.cache_svc, "ensure_history", broken)
    await service.ensure_display_fresh(db, "XOM")  # does not raise


async def test_different_symbols_refresh_side_by_side(service, db: Session) -> None:
    await asyncio.gather(*(service.ensure_display_fresh(db, s) for s in ("V", "UNH", "XOM", "WMT")))
    assert sorted(service.refreshes) == ["UNH", "V", "WMT", "XOM"]


# ── /api/data/daily/{symbol}?start= ──────────────────────────────────────────

async def test_daily_bars_can_start_from_a_date(service, db: Session) -> None:
    today = date.today()
    for years_back in (10, 6, 4, 1, 0):
        db.add(_bar("AMD", today - timedelta(days=365 * years_back), close=float(years_back)))
    db.commit()

    everything = await service.get_cached_bars(db, "amd", today)
    assert len(everything) == 5  # no start: all of it, as before

    recent = await service.get_cached_bars(db, "AMD", today, start_date=today - timedelta(days=365 * 5))
    assert [bar.close for bar in recent] == [4.0, 1.0, 0.0]  # oldest first
    assert recent[0].trading_date >= today - timedelta(days=365 * 5)


def test_the_daily_route_passes_start_through(db: Session, monkeypatch) -> None:
    from app.api.routes import market_data as routes

    seen = {}

    async def fake(db_, symbol, end_date, start_date=None):
        seen.update(symbol=symbol, end=end_date, start=start_date)
        return []

    monkeypatch.setattr(routes.market_data_service, "get_cached_bars", fake)
    asyncio.run(routes.get_daily_prices("amd", start=date(2021, 1, 4), end=None, db=db))
    assert seen["symbol"] == "AMD" and seen["start"] == date(2021, 1, 4)
