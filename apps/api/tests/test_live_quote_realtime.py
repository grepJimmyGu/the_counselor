"""Real-time quote source + per-caller freshness for LiveQuoteService.

Pins the behaviours that make the Alpha Vantage source safe to switch on:

  - AV's answer to a key that is NOT entitled is HTTP 200 with artificial
    sample data. That must never become a price — by its `message`, and
    independently by the age of each row.
  - Any AV failure costs nothing but the FMP fallback.
  - Off by default: with `live_quote_provider` unset, AV is never called.
  - /api/live/quotes can ask for fresher quotes without changing what the
    500-symbol Market Pulse callers get.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import live_quotes as route
from app.services import live_quote_service as svc
from app.services.alpha_vantage_quotes import MAX_QUOTE_AGE_DAYS, parse_bulk_quotes
from app.services.live_quote_service import (
    MIN_MAX_AGE_SECONDS,
    TTL_SECONDS,
    LiveQuoteService,
)

# What https://www.alphavantage.co/query?function=REALTIME_BULK_QUOTES returned
# for the public `demo` key on 2026-11-16 (two of its three rows). This is the
# payload an un-entitled production key would receive.
DEMO_KEY_RESPONSE = {
    "endpoint": "Realtime Bulk Quotes",
    "message": (
        "This is a premium endpoint. ***THE SAMPLE DATA SCHEMA BELOW IS ARTIFICIAL "
        "AND FOR ILLUSTRATION PURPOSES ONLY***. To access the actual data, please "
        "subscribe to any premium plan that mentions 'Realtime US Market Data' in "
        "its description at https://www.alphavantage.co/premium/ for your personal "
        "non-professional use. For professional/commercial use, please contact "
        "support at support@alphavantage.co."
    ),
    "data": [
        {
            "symbol": "MSFT", "timestamp": "2024-10-18 19:59:55.291", "open": "417.61",
            "high": "419.649", "low": "416.2601", "close": "418.16", "volume": "17145307",
            "previous_close": "416.72", "change": "1.44", "change_percent": "0.3456",
            "extended_hours_quote": "418.1", "extended_hours_change": "-0.06",
            "extended_hours_change_percent": "-0.01435",
        },
        {
            "symbol": "AAPL", "timestamp": "2024-10-18 19:59:50.451", "open": "236.0",
            "high": "236.05", "low": "234.02", "close": "235.0", "volume": "46431470",
            "previous_close": "232.15", "change": "2.85", "change_percent": "1.2277",
            "extended_hours_quote": "234.83", "extended_hours_change": "-0.17",
            "extended_hours_change_percent": "-0.07234",
        },
    ],
}

NOW = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)


def _entitled(rows: list) -> dict:
    return {"endpoint": "Realtime Bulk Quotes", "data": rows}


def _row(symbol: str, close: str = "352.78", stamp: str = "2026-11-16 14:59:58.120") -> dict:
    return {
        "symbol": symbol, "timestamp": stamp, "open": "355.0", "high": "356.2",
        "low": "350.1", "close": close, "volume": "41234567", "previous_close": "356.27",
        "change": "-3.49", "change_percent": "-0.9796",
    }


# ── the parser: what counts as a real quote ──────────────────────────────────


def test_sample_data_for_an_unentitled_key_is_never_a_quote() -> None:
    assert parse_bulk_quotes(DEMO_KEY_RESPONSE, now=NOW) == []


def test_old_rows_are_refused_even_without_the_warning_message() -> None:
    """The age guard must not depend on the wording of AV's message."""
    silent = {"data": DEMO_KEY_RESPONSE["data"]}
    assert parse_bulk_quotes(silent, now=NOW) == []


def test_a_current_row_is_normalised() -> None:
    [quote] = parse_bulk_quotes(_entitled([_row("aapl")]), now=NOW)
    assert quote["symbol"] == "AAPL"
    assert quote["price"] == 352.78
    assert quote["change"] == -3.49
    assert quote["change_percent"] == -0.9796
    assert quote["day_high"] == 356.2
    assert quote["day_low"] == 350.1
    assert quote["volume"] == 41234567
    # 14:59:58 US/Eastern on a November day is 19:59:58 UTC.
    assert datetime.fromtimestamp(quote["as_of"], tz=timezone.utc) == datetime(
        2026, 11, 16, 19, 59, 58, 120000, tzinfo=timezone.utc
    )


def test_only_the_stale_rows_of_a_mixed_response_are_dropped() -> None:
    week_old = f"2026-11-{16 - MAX_QUOTE_AGE_DAYS - 1:02d} 15:00:00.000"
    quotes = parse_bulk_quotes(_entitled([_row("AAPL"), _row("MSFT", stamp=week_old)]), now=NOW)
    assert [q["symbol"] for q in quotes] == ["AAPL"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"Information": "Thank you for using Alpha Vantage! Our standard API rate limit is ..."},
        {"Error Message": "Invalid API call."},
        {"data": "not a list"},
        _entitled([{"symbol": "AAPL", "close": "0", "timestamp": "2026-11-16 14:00:00"}]),
        _entitled([{"symbol": "AAPL", "close": "abc", "timestamp": "2026-11-16 14:00:00"}]),
        _entitled([{"symbol": "AAPL", "close": "10.0"}]),  # no timestamp: age unknown
        _entitled(["junk"]),
    ],
)
def test_malformed_and_error_responses_yield_nothing(payload) -> None:
    assert parse_bulk_quotes(payload, now=NOW) == []


# ── the service: AV first, FMP behind it ─────────────────────────────────────


def _fmp_payload(symbol: str, price: float = 100.0) -> dict:
    return {
        "symbol": symbol, "price": price, "change": 1.5, "changesPercentage": 1.5,
        "dayHigh": price + 1, "dayLow": price - 1, "volume": 1_000_000, "marketCap": 1e12,
        "name": f"{symbol} Inc.", "exchange": "NASDAQ", "timestamp": 1794856798,
    }


def _av_quote(symbol: str, price: float = 352.78) -> dict:
    return {
        "symbol": symbol, "price": price, "change": -3.49, "change_percent": -0.98,
        "day_high": price + 2, "day_low": price - 2, "volume": 4.1e7, "as_of": 1794859198.0,
    }


@pytest.fixture
def fmp() -> AsyncMock:
    mock = AsyncMock()
    mock.get_quotes_batch = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def av() -> AsyncMock:
    mock = AsyncMock()
    mock.get_bulk_quotes = AsyncMock(return_value=[])
    return mock


def _service(fmp: AsyncMock, av: AsyncMock, provider: str = "alpha_vantage") -> LiveQuoteService:
    return LiveQuoteService(fmp=fmp, alpha_vantage=av, provider=provider)


def test_alpha_vantage_is_off_unless_configured(fmp: AsyncMock, av: AsyncMock) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL")]
    # No override: the provider comes from settings, whose default is "fmp".
    service = LiveQuoteService(fmp=fmp, alpha_vantage=av)
    result = asyncio.run(service.get_quotes(["AAPL"]))
    assert result["AAPL"].source == "fmp"
    av.get_bulk_quotes.assert_not_awaited()


def test_alpha_vantage_answers_and_fmp_is_not_called(fmp: AsyncMock, av: AsyncMock) -> None:
    av.get_bulk_quotes.return_value = [_av_quote("AAPL"), _av_quote("MSFT", 517.99)]
    result = asyncio.run(_service(fmp, av).get_quotes(["AAPL", "MSFT"]))
    assert {s: q.source for s, q in result.items()} == {"AAPL": "alpha_vantage", "MSFT": "alpha_vantage"}
    assert result["AAPL"].price == 352.78
    assert result["AAPL"].as_of == 1794859198.0
    assert result["AAPL"].checked_at == pytest.approx(time.time(), abs=5)
    fmp.get_quotes_batch.assert_not_awaited()


def test_fmp_fills_only_what_alpha_vantage_left_out(fmp: AsyncMock, av: AsyncMock) -> None:
    av.get_bulk_quotes.return_value = [_av_quote("AAPL")]
    fmp.get_quotes_batch.return_value = [_fmp_payload("BRK.B", 480.0)]
    result = asyncio.run(_service(fmp, av).get_quotes(["AAPL", "BRK.B"]))
    assert result["AAPL"].source == "alpha_vantage"
    assert result["BRK.B"].source == "fmp"
    fmp.get_quotes_batch.assert_awaited_once_with(["BRK.B"])


def test_an_unentitled_key_degrades_to_fmp(fmp: AsyncMock, av: AsyncMock) -> None:
    """What `parse_bulk_quotes` returns for sample data is [], so every
    symbol falls through to FMP and the user sees real prices."""
    av.get_bulk_quotes.return_value = parse_bulk_quotes(DEMO_KEY_RESPONSE, now=NOW)
    fmp.get_quotes_batch.return_value = [_fmp_payload("MSFT", 517.99), _fmp_payload("AAPL", 352.78)]
    result = asyncio.run(_service(fmp, av).get_quotes(["MSFT", "AAPL"]))
    assert result["MSFT"].price == 517.99  # not the 418.16 in the sample data
    assert result["AAPL"].price == 352.78
    assert {q.source for q in result.values()} == {"fmp"}


def test_an_alpha_vantage_failure_costs_only_the_fallback(fmp: AsyncMock, av: AsyncMock) -> None:
    av.get_bulk_quotes.side_effect = RuntimeError("503 from upstream")
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL", 200.0)]
    result = asyncio.run(_service(fmp, av).get_quotes(["AAPL"]))
    assert result["AAPL"].price == 200.0
    assert result["AAPL"].source == "fmp"


def test_symbols_nobody_asked_for_are_not_cached(fmp: AsyncMock, av: AsyncMock) -> None:
    av.get_bulk_quotes.return_value = [_av_quote("AAPL"), _av_quote("TSLA", 1.0)]
    service = _service(fmp, av)
    asyncio.run(service.get_quotes(["AAPL"]))
    av.get_bulk_quotes.reset_mock()
    av.get_bulk_quotes.return_value = [_av_quote("TSLA", 379.74)]
    result = asyncio.run(service.get_quotes(["TSLA"]))
    # TSLA was fetched now, not served from the stray row.
    av.get_bulk_quotes.assert_awaited_once()
    assert result["TSLA"].price == 379.74


def test_large_requests_stay_on_fmp(fmp: AsyncMock, av: AsyncMock) -> None:
    symbols = [f"S{i}" for i in range(101)]
    fmp.get_quotes_batch.return_value = [_fmp_payload(s) for s in symbols]
    result = asyncio.run(_service(fmp, av).get_quotes(symbols))
    assert len(result) == 101
    av.get_bulk_quotes.assert_not_awaited()


def test_company_fields_survive_an_alpha_vantage_refresh(fmp: AsyncMock, av: AsyncMock) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL", 350.0)]
    service = _service(fmp, av, provider="fmp")
    asyncio.run(service.get_quotes(["AAPL"]))

    service._provider_override = "alpha_vantage"
    service._cache["AAPL"] = svc.LiveQuote(
        **{**service._cache["AAPL"].__dict__, "fetched_at": time.monotonic() - TTL_SECONDS - 1}
    )
    av.get_bulk_quotes.return_value = [_av_quote("AAPL", 352.78)]
    refreshed = asyncio.run(service.get_quotes(["AAPL"]))["AAPL"]
    assert refreshed.price == 352.78
    assert refreshed.name == "AAPL Inc."
    assert refreshed.market_cap == 1e12
    assert refreshed.exchange == "NASDAQ"


def test_fmp_quotes_carry_the_trade_time_and_a_wall_clock(fmp: AsyncMock, av: AsyncMock) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL")]
    quote = asyncio.run(_service(fmp, av, provider="fmp").get_quotes(["AAPL"]))["AAPL"]
    assert quote.as_of == 1794856798
    assert quote.checked_at == pytest.approx(time.time(), abs=5)


# ── freshness per caller ─────────────────────────────────────────────────────


def _age(service: LiveQuoteService, symbol: str, seconds: float) -> None:
    quote = service._cache[symbol]
    service._cache[symbol] = svc.LiveQuote(
        **{**quote.__dict__, "fetched_at": time.monotonic() - seconds}
    )


def test_a_caller_can_ask_for_fresher_than_the_default(fmp: AsyncMock, av: AsyncMock) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL", 100.0)]
    service = _service(fmp, av, provider="fmp")
    asyncio.run(service.get_quotes(["AAPL"]))
    _age(service, "AAPL", 10)

    # Ten seconds old: fine for the default caller…
    asyncio.run(service.get_quotes(["AAPL"]))
    assert fmp.get_quotes_batch.await_count == 1
    # …stale for one that asked for five.
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL", 101.0)]
    result = asyncio.run(service.get_quotes(["AAPL"], max_age=5))
    assert fmp.get_quotes_batch.await_count == 2
    assert result["AAPL"].price == 101.0


def test_max_age_is_floored_and_cannot_widen_the_default(fmp: AsyncMock, av: AsyncMock) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL")]
    service = _service(fmp, av, provider="fmp")
    asyncio.run(service.get_quotes(["AAPL"]))

    # Asking for "0 seconds" does not make every request a provider call.
    _age(service, "AAPL", MIN_MAX_AGE_SECONDS / 2)
    asyncio.run(service.get_quotes(["AAPL"], max_age=0))
    assert fmp.get_quotes_batch.await_count == 1

    # Asking for an hour does not serve anything older than the default.
    _age(service, "AAPL", TTL_SECONDS + 1)
    asyncio.run(service.get_quotes(["AAPL"], max_age=3600))
    assert fmp.get_quotes_batch.await_count == 2


# ── the route ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "configured, expected",
    [(30.0, 30.0), (5.0, 5.0), (0.0, MIN_MAX_AGE_SECONDS), (600.0, TTL_SECONDS)],
)
def test_route_reports_the_ttl_it_used(monkeypatch, fmp: AsyncMock, av: AsyncMock, configured, expected) -> None:
    fmp.get_quotes_batch.return_value = [_fmp_payload("AAPL", 352.78)]
    service = _service(fmp, av, provider="fmp")
    monkeypatch.setattr(route, "live_quote_service", service)
    monkeypatch.setattr(route, "get_settings", lambda: SimpleNamespace(live_quote_ttl_seconds=configured))

    response = asyncio.run(route.get_live_quotes(symbols=" aapl ,"))

    assert response.ttl_seconds == expected
    quote = response.quotes["AAPL"]
    assert quote.price == 352.78
    assert quote.source == "fmp"
    assert quote.as_of == 1794856798
    assert quote.checked_at == pytest.approx(time.time(), abs=5)


# ── the HTTP client ──────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeHTTP:
    """Stands in for httpx.AsyncClient and records each GET."""

    calls: list = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeHTTP":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str, params: dict) -> _FakeResponse:
        type(self).calls.append((url, dict(params)))
        symbols = params["symbol"].split(",")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return _FakeResponse(_entitled([_row(s, stamp=stamp) for s in symbols]))


def _client(monkeypatch, **settings):
    from app.services import alpha_vantage_quotes as module

    _FakeHTTP.calls = []
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeHTTP)
    base = {"alpha_vantage_api_key": "k", "alpha_vantage_quote_entitlement": "", "api_timeout_seconds": 5.0}
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(**{**base, **settings}))
    return module.AlphaVantageQuoteClient()


def test_client_asks_the_documented_endpoint_in_chunks_of_100(monkeypatch) -> None:
    client = _client(monkeypatch)
    symbols = [f"S{i}" for i in range(150)] + ["s0"]  # a duplicate, differently cased
    quotes = asyncio.run(client.get_bulk_quotes(symbols))

    assert len(quotes) == 150
    assert [len(params["symbol"].split(",")) for _, params in _FakeHTTP.calls] == [100, 50]
    url, params = _FakeHTTP.calls[0]
    assert url == "https://www.alphavantage.co/query"
    assert params["function"] == "REALTIME_BULK_QUOTES"
    assert params["apikey"] == "k"
    # Left to the plan unless configured.
    assert "entitlement" not in params


def test_client_sends_the_entitlement_only_when_configured(monkeypatch) -> None:
    client = _client(monkeypatch, alpha_vantage_quote_entitlement="realtime")
    asyncio.run(client.get_bulk_quotes(["AAPL"]))
    assert _FakeHTTP.calls[0][1]["entitlement"] == "realtime"


def test_client_makes_no_request_without_a_key(monkeypatch) -> None:
    client = _client(monkeypatch, alpha_vantage_api_key="")
    assert asyncio.run(client.get_bulk_quotes(["AAPL"])) == []
    assert _FakeHTTP.calls == []


# ── with the shared queue (rebased onto #379, 2026-11-20) ────────────────────
#
# #379 replaced the per-symbol locks with one queue: everything callers are
# missing rides on one provider call at a time. These pin that the two
# features this file is about still hold on that design.


def test_overlapping_callers_share_one_alpha_vantage_call(fmp: AsyncMock, av: AsyncMock) -> None:
    symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"]
    batches: list = []

    async def bulk(batch: list) -> list:
        batches.append(list(batch))
        await asyncio.sleep(0.01)
        # BRK.B is the kind of symbol AV leaves out; here it is META.
        return [_av_quote(s) for s in batch if s != "META"]

    av.get_bulk_quotes.side_effect = bulk
    fmp.get_quotes_batch.side_effect = lambda batch: [_fmp_payload(s) for s in batch]
    service = _service(fmp, av)

    async def twenty_callers():
        return await asyncio.gather(*(service.get_quotes(symbols[i % 3:i % 3 + 4]) for i in range(20)))

    results = asyncio.run(twenty_callers())
    for i, result in enumerate(results):
        assert set(result) == set(symbols[i % 3:i % 3 + 4])
    # Each symbol asked of Alpha Vantage once, in at most two calls...
    assert len(batches) <= 2
    assert sorted(s for batch in batches for s in batch) == sorted(symbols)
    # ...and FMP only for the one it left out.
    assert [call.args[0] for call in fmp.get_quotes_batch.await_args_list] == [["META"]]
    assert results[2]["META"].source == "fmp" and results[0]["AAPL"].source == "alpha_vantage"


def test_a_batch_too_large_for_alpha_vantage_goes_to_fmp(fmp: AsyncMock, av: AsyncMock) -> None:
    """Market Pulse asks for ~500 symbols. With the queue, the size that
    decides is the batch's: everything waiting when the call goes out."""
    symbols = ["S%03d" % n for n in range(101)]
    fmp.get_quotes_batch.side_effect = lambda batch: [_fmp_payload(s) for s in batch]
    result = asyncio.run(_service(fmp, av).get_quotes(symbols))
    assert len(result) == 101
    av.get_bulk_quotes.assert_not_awaited()


def test_a_caller_wanting_fresher_quotes_does_not_refetch_for_everyone(fmp: AsyncMock, av: AsyncMock) -> None:
    """`max_age` decides what THIS caller treats as stale. A 10-second-old
    quote is refetched for the caller who asked for 5 and served from cache
    to the caller on the 30-second default."""
    fmp.get_quotes_batch.side_effect = lambda batch: [_fmp_payload(s) for s in batch]
    service = _service(fmp, av, provider="fmp")
    asyncio.run(service.get_quotes(["AAPL"]))
    quote = service._cache["AAPL"]
    service._cache["AAPL"] = svc.LiveQuote(**{**quote.__dict__, "fetched_at": time.monotonic() - 10})
    fmp.get_quotes_batch.reset_mock()

    asyncio.run(service.get_quotes(["AAPL"]))
    assert fmp.get_quotes_batch.await_count == 0
    asyncio.run(service.get_quotes(["AAPL"], max_age=5))
    assert fmp.get_quotes_batch.await_count == 1


def test_an_alpha_vantage_failure_still_answers_everyone_waiting(fmp: AsyncMock, av: AsyncMock) -> None:
    av.get_bulk_quotes.side_effect = RuntimeError("quota")
    fmp.get_quotes_batch.side_effect = lambda batch: [_fmp_payload(s) for s in batch]
    service = _service(fmp, av)

    async def three_callers():
        return await asyncio.gather(*(service.get_quotes(["AAPL", "MSFT"]) for _ in range(3)))

    for result in asyncio.run(three_callers()):
        assert {q.source for q in result.values()} == {"fmp"}
    assert fmp.get_quotes_batch.await_count == 1
