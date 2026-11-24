"""The company page's 1D and 1W charts (2026-11-24).

Jimmy: the price at the top of a company page is live, but the chart stops at
yesterday's close, so today's move can't be seen. These pin how FMP's bars
become the two new ranges: regular hours only, the right sessions, times in
UTC, and the close each range is measured from.

No network: FMP is a fake.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import market_data
from app.services.fmp_client import FMPError, FMPNoDataError
from app.services.intraday_chart_service import (
    ET,
    IntradayChartService,
    IntradayUnavailable,
    NoIntradayPrices,
    build_chart,
)


def _session(day: date, minutes: int, start_price: float, *, extended: bool = False) -> list[dict]:
    """A day of bars as `fetch_intraday_bars` returns them (naive New York
    wall clock), rising a cent a bar; with `extended`, pre- and after-hours
    bars too, which the chart must drop."""
    rows = []
    t = datetime.combine(day, datetime.min.time()).replace(hour=4 if extended else 9, minute=0 if extended else 30)
    end = t.replace(hour=20 if extended else 16, minute=0)
    price = start_price
    while t < end:
        rows.append({"bar_time": t, "open": price, "high": price, "low": price, "close": price + 0.01, "volume": 1.0})
        price += 0.01
        t += timedelta(minutes=minutes)
    return rows


MON, TUE = date(2026, 11, 23), date(2026, 11, 24)


def test_1d_is_the_latest_regular_session_in_utc_measured_from_the_official_close() -> None:
    raw = _session(MON, 5, 160.0) + _session(TUE, 5, 159.0, extended=True)
    chart = build_chart("NVDA", "1d", raw, {MON: 165.05}, today=TUE)

    assert [s.date for s in chart.sessions] == [TUE]
    bars = chart.sessions[0].bars
    # 9:30 to 15:55, nothing from pre-market or after-hours.
    assert len(bars) == 78
    # 9:30 New York in November is 14:30 UTC.
    assert bars[0].time == datetime(2026, 11, 24, 14, 30, tzinfo=timezone.utc)
    assert bars[-1].time == datetime(2026, 11, 24, 20, 55, tzinfo=timezone.utc)
    assert chart.as_of == datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc)
    # Monday's close as the exchange printed it, not its last 5-minute bar.
    assert chart.previous_close == 165.05
    assert chart.previous_close_date == MON
    assert chart.previous_close_source == "official"
    # Today's close isn't printed yet.
    assert chart.sessions[0].close is None
    assert chart.interval_minutes == 5


def test_summer_sessions_open_at_1330_utc() -> None:
    day = date(2026, 7, 14)
    chart = build_chart("AAPL", "1d", _session(day, 5, 200.0), {}, today=day)
    assert chart.sessions[0].bars[0].time == datetime(2026, 7, 14, 13, 30, tzinfo=timezone.utc)


def test_without_the_official_close_the_day_before_ends_on_its_last_bar() -> None:
    raw = _session(MON, 5, 160.0) + _session(TUE, 5, 159.0)
    chart = build_chart("NVDA", "1d", raw, {}, today=TUE)
    assert chart.previous_close == pytest.approx(160.0 + 77 * 0.01 + 0.01)
    assert chart.previous_close_source == "last_bar"


def test_1w_is_five_sessions_and_finished_days_end_on_their_official_close() -> None:
    days = [date(2026, 11, d) for d in (16, 17, 18, 19, 20, 23, 24)]
    raw = [row for i, d in enumerate(days) for row in _session(d, 30, 150.0 + i)]
    closes = {d: 100.0 + i for i, d in enumerate(days)}
    chart = build_chart("NVDA", "1w", raw, closes, today=TUE)

    assert [s.date for s in chart.sessions] == days[2:]
    assert all(len(s.bars) == 13 for s in chart.sessions)
    assert [s.close for s in chart.sessions] == [102.0, 103.0, 104.0, 105.0, None]
    # Measured from the close of the session before the week: Tuesday the 17th.
    assert chart.previous_close == 101.0 and chart.previous_close_date == date(2026, 11, 17)


def test_a_short_history_shows_what_there_is() -> None:
    # A stock that listed on Monday: one session before today, no close
    # before that.
    raw = _session(MON, 30, 10.0) + _session(TUE, 30, 11.0)
    chart = build_chart("ANT", "1w", raw, {}, today=TUE)
    assert [s.date for s in chart.sessions] == [MON, TUE]
    assert chart.previous_close is None and chart.previous_close_source is None


def test_an_old_official_close_is_not_taken_for_the_day_before() -> None:
    # FMP sent only Tuesday. A close from four days earlier can be the
    # session just before (a holiday weekend); one from a week earlier can't.
    raw = _session(TUE, 5, 159.0)
    assert build_chart("X", "1d", raw, {date(2026, 11, 20): 150.0}, today=TUE).previous_close == 150.0
    assert build_chart("X", "1d", raw, {date(2026, 11, 17): 150.0}, today=TUE).previous_close is None


def test_nothing_in_regular_hours_is_no_prices() -> None:
    raw = [{"bar_time": datetime(2026, 11, 24, 7, 0), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    with pytest.raises(NoIntradayPrices):
        build_chart("X", "1d", raw, {}, today=TUE)


def test_REGRESSION_the_bar_still_in_progress_runs_to_now_not_to_its_end() -> None:
    # Production, 2026-11-24 at 15:07 ET: the 1W chart's newest 30-minute bar
    # was the one starting at 15:00, so the line was drawn to 15:30, the
    # caption said "to 3:30 PM", and the live price was never added because
    # it looked older than the bars.
    tue = [r for r in _session(TUE, 30, 159.0) if r["bar_time"].hour < 15 or r["bar_time"].minute == 0 and r["bar_time"].hour == 15]
    assert tue[-1]["bar_time"] == datetime(2026, 11, 24, 15, 0)
    now = datetime(2026, 11, 24, 15, 7, tzinfo=ET)
    chart = build_chart("NVDA", "1w", _session(MON, 30, 160.0) + tue, {}, today=TUE, now=now)
    assert chart.as_of == datetime(2026, 11, 24, 20, 7, tzinfo=timezone.utc)
    # A finished bar is untouched: after the close, the day ends at 16:00.
    after = build_chart("NVDA", "1w", _session(MON, 30, 160.0), {}, today=TUE, now=now)
    assert after.as_of == datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)


class FakeFMP:
    def __init__(self, bars=None, eod=None, bars_error=None, eod_error=None) -> None:
        self.bars, self.eod = bars or [], eod or []
        self.bars_error, self.eod_error = bars_error, eod_error
        self.bar_calls: list[dict] = []
        self.eod_calls = 0

    async def fetch_intraday_bars(self, symbol, interval="15min", outputsize="compact", from_date=None, to_date=None):
        self.bar_calls.append({"symbol": symbol, "interval": interval, "outputsize": outputsize,
                               "from": from_date, "to": to_date})
        if self.bars_error:
            raise self.bars_error
        return self.bars

    async def get_historical_eod(self, symbol, from_date, to_date):
        self.eod_calls += 1
        if self.eod_error:
            raise self.eod_error
        return self.eod


def _service(fake: FakeFMP) -> IntradayChartService:
    return IntradayChartService(client=fake, now=lambda: datetime(2026, 11, 24, 12, 40, tzinfo=ET))


def test_service_asks_fmp_for_the_right_bars_and_days_and_caches_the_answer() -> None:
    fake = FakeFMP(bars=_session(MON, 30, 160.0) + _session(TUE, 30, 159.0),
                   eod=[{"date": "2026-11-23", "close": 165.05}])
    service = _service(fake)

    async def twice():
        first = await service.chart(" nvda ", "1w")
        second = await service.chart("NVDA", "1w")
        return first, second

    first, second = asyncio.run(twice())
    assert first is second
    assert fake.bar_calls == [{"symbol": "NVDA", "interval": "30min", "outputsize": "full",
                               "from": "2026-11-10", "to": "2026-11-24"}]
    assert fake.eod_calls == 1
    assert first.sessions[-1].date == TUE


def test_service_1d_uses_five_minute_bars_over_a_week() -> None:
    fake = FakeFMP(bars=_session(TUE, 5, 159.0))
    asyncio.run(_service(fake).chart("NVDA", "1d"))
    assert fake.bar_calls[0]["interval"] == "5min"
    assert fake.bar_calls[0]["from"] == "2026-11-17"


def test_an_unknown_symbol_is_no_prices_and_an_outage_is_unavailable() -> None:
    with pytest.raises(NoIntradayPrices):
        asyncio.run(_service(FakeFMP(bars_error=FMPNoDataError("No intraday data"))).chart("ZZZZ", "1d"))
    with pytest.raises(IntradayUnavailable):
        asyncio.run(_service(FakeFMP(bars_error=FMPError("rate limit"))).chart("NVDA", "1d"))


def test_when_the_closes_fail_the_chart_still_draws() -> None:
    fake = FakeFMP(bars=_session(MON, 5, 160.0) + _session(TUE, 5, 159.0), eod_error=FMPError("down"))
    chart = asyncio.run(_service(fake).chart("NVDA", "1d"))
    assert chart.previous_close_source == "last_bar"


def test_an_unknown_range_is_refused() -> None:
    with pytest.raises(ValueError):
        asyncio.run(_service(FakeFMP()).chart("NVDA", "5y"))


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(market_data.router)

    def use(fake: FakeFMP) -> TestClient:
        monkeypatch.setattr(market_data, "intraday_chart_service", _service(fake))
        return TestClient(app)

    return use


def test_route_returns_sessions_bars_and_the_close_they_start_from(api) -> None:
    client = api(FakeFMP(bars=_session(MON, 5, 160.0) + _session(TUE, 5, 159.0),
                         eod=[{"date": "2026-11-23", "close": 165.05}]))
    body = client.get("/api/data/intraday/nvda", params={"range": "1d"}).json()
    assert body["symbol"] == "NVDA" and body["range"] == "1d" and body["interval_minutes"] == 5
    assert body["previous_close"] == 165.05 and body["previous_close_date"] == "2026-11-23"
    assert body["sessions"][0]["date"] == "2026-11-24"
    first = body["sessions"][0]["bars"][0]
    assert datetime.fromisoformat(first["time"].replace("Z", "+00:00")) == datetime(2026, 11, 24, 14, 30, tzinfo=timezone.utc)
    assert set(first) == {"time", "open", "close"}


def test_route_defaults_to_1d_and_refuses_other_ranges(api) -> None:
    client = api(FakeFMP(bars=_session(TUE, 5, 159.0)))
    assert client.get("/api/data/intraday/NVDA").json()["range"] == "1d"
    assert client.get("/api/data/intraday/NVDA", params={"range": "1y"}).status_code == 422


def test_route_errors_say_what_happened(api) -> None:
    missing = api(FakeFMP(bars_error=FMPNoDataError("No intraday data"))).get("/api/data/intraday/ZZZZ")
    assert missing.status_code == 404 and missing.json()["detail"] == "No intraday prices for ZZZZ."
    down = api(FakeFMP(bars_error=FMPError("rate limit"))).get("/api/data/intraday/NVDA")
    assert down.status_code == 502 and down.json()["detail"] == "Couldn't load intraday prices right now."
