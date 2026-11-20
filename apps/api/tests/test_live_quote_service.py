"""Unit tests for LiveQuoteService.

Each test pins down one of the verifiable goals from the design:
  - cache hits don't touch FMP
  - multiple stale symbols in one call → one FMP fetch (batch)
  - thundering-herd: two concurrent callers for the same stale symbol fire
    only one FMP call (per-symbol Lock + lock-then-recheck pattern)
  - missing-from-FMP symbols are absent from the result, not crashing
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.services.live_quote_service import (
    TTL_SECONDS,
    LiveQuote,
    LiveQuoteService,
    _from_fmp_payload,
)


def _quote_payload(symbol: str, price: float = 100.0) -> dict:
    """Match the FMP /stable/quote response shape."""
    return {
        "symbol": symbol,
        "price": price,
        "change": 1.5,
        "changesPercentage": 1.5,
        "dayHigh": price + 1,
        "dayLow": price - 1,
        "volume": 1_000_000,
        "marketCap": 1e12,
        "name": f"{symbol} Inc.",
        "exchange": "NASDAQ",
    }


@pytest.fixture
def mock_fmp() -> AsyncMock:
    fmp = AsyncMock()
    fmp.get_quotes_batch = AsyncMock(return_value=[])
    return fmp


@pytest.fixture
def service(mock_fmp: AsyncMock) -> LiveQuoteService:
    return LiveQuoteService(fmp=mock_fmp)


# ── cache hit + miss basics ──────────────────────────────────────────────────


def test_first_call_fetches_from_fmp(service: LiveQuoteService, mock_fmp: AsyncMock) -> None:
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 200.0)]
    result = asyncio.run(service.get_quotes(["AAPL"]))

    assert "AAPL" in result
    assert result["AAPL"].price == 200.0
    assert mock_fmp.get_quotes_batch.await_count == 1
    mock_fmp.get_quotes_batch.assert_awaited_with(["AAPL"])


def test_second_call_within_ttl_is_cached(service: LiveQuoteService, mock_fmp: AsyncMock) -> None:
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL")]
    asyncio.run(service.get_quotes(["AAPL"]))
    asyncio.run(service.get_quotes(["AAPL"]))

    # One FMP call total — second was a cache hit.
    assert mock_fmp.get_quotes_batch.await_count == 1


def test_batch_call_fetches_all_stale_in_one_request(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    mock_fmp.get_quotes_batch.return_value = [
        _quote_payload("AAPL", 200),
        _quote_payload("MSFT", 300),
        _quote_payload("GOOGL", 150),
    ]
    result = asyncio.run(service.get_quotes(["AAPL", "MSFT", "GOOGL"]))

    assert set(result.keys()) == {"AAPL", "MSFT", "GOOGL"}
    # One batched call, not three.
    assert mock_fmp.get_quotes_batch.await_count == 1


def test_partial_cache_only_fetches_stale(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    # Pre-populate the cache for AAPL.
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 200)]
    asyncio.run(service.get_quotes(["AAPL"]))

    # Now ask for AAPL + MSFT. Only MSFT should be fetched.
    mock_fmp.get_quotes_batch.reset_mock()
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("MSFT", 300)]
    result = asyncio.run(service.get_quotes(["AAPL", "MSFT"]))

    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert mock_fmp.get_quotes_batch.await_count == 1
    mock_fmp.get_quotes_batch.assert_awaited_with(["MSFT"])


# ── thundering-herd / lock behavior ──────────────────────────────────────────


def test_concurrent_callers_for_same_symbol_share_one_fetch(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    """Two coroutines ask for AAPL simultaneously → only one FMP fetch."""
    fetch_call_count = 0

    async def slow_batch(symbols: list[str]) -> list[dict]:
        nonlocal fetch_call_count
        fetch_call_count += 1
        # Yield to the event loop so the second caller has a chance to start
        # before we return — proves the lock is the gating factor, not just
        # synchronous fast-return.
        await asyncio.sleep(0.01)
        return [_quote_payload(s) for s in symbols]

    mock_fmp.get_quotes_batch.side_effect = slow_batch

    async def two_callers():
        return await asyncio.gather(
            service.get_quotes(["AAPL"]),
            service.get_quotes(["AAPL"]),
        )

    results = asyncio.run(two_callers())

    assert results[0]["AAPL"].price == results[1]["AAPL"].price
    # The lock-then-recheck pattern means the second caller saw the cache
    # populated by the first and skipped its own fetch.
    assert fetch_call_count == 1


def test_ttl_expiry_triggers_refetch(
    service: LiveQuoteService, mock_fmp: AsyncMock, monkeypatch,
) -> None:
    """A cached quote past its TTL is treated as stale on the next call."""
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 200)]
    asyncio.run(service.get_quotes(["AAPL"]))
    assert mock_fmp.get_quotes_batch.await_count == 1

    # Fast-forward time past TTL by mutating the cached entry's timestamp.
    cached = service._cache["AAPL"]
    service._cache["AAPL"] = LiveQuote(
        symbol=cached.symbol,
        price=cached.price,
        change=cached.change,
        change_percent=cached.change_percent,
        day_high=cached.day_high,
        day_low=cached.day_low,
        volume=cached.volume,
        market_cap=cached.market_cap,
        name=cached.name,
        exchange=cached.exchange,
        fetched_at=cached.fetched_at - (TTL_SECONDS + 1),
    )

    mock_fmp.get_quotes_batch.reset_mock()
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 210)]
    result = asyncio.run(service.get_quotes(["AAPL"]))

    assert result["AAPL"].price == 210
    assert mock_fmp.get_quotes_batch.await_count == 1


# ── error / edge cases ──────────────────────────────────────────────────────


def test_empty_input_returns_empty_dict_with_no_fetch(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    result = asyncio.run(service.get_quotes([]))
    assert result == {}
    assert mock_fmp.get_quotes_batch.await_count == 0


def test_symbol_not_returned_by_fmp_is_absent_from_result(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    """If FMP returns AAPL but not BADTICKER, the result has only AAPL."""
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL")]
    result = asyncio.run(service.get_quotes(["AAPL", "BADTICKER"]))

    assert set(result.keys()) == {"AAPL"}


def test_symbols_are_normalized_to_uppercase(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL")]
    result = asyncio.run(service.get_quotes(["aapl"]))

    assert "AAPL" in result
    mock_fmp.get_quotes_batch.assert_awaited_with(["AAPL"])


# ── payload parsing ─────────────────────────────────────────────────────────


def test_from_fmp_payload_handles_missing_optionals() -> None:
    """A minimal payload (only symbol + price) should still parse."""
    quote = _from_fmp_payload({"symbol": "AAPL", "price": 100.0}, fetched_at=time.monotonic())
    assert quote is not None
    assert quote.symbol == "AAPL"
    assert quote.price == 100.0
    assert quote.change == 0.0  # default when missing
    assert quote.volume is None


def test_from_fmp_payload_rejects_missing_price() -> None:
    assert _from_fmp_payload({"symbol": "AAPL"}, fetched_at=time.monotonic()) is None


def test_from_fmp_payload_rejects_missing_symbol() -> None:
    assert _from_fmp_payload({"price": 100.0}, fetched_at=time.monotonic()) is None


# ── many callers at once (2026-11-20) ────────────────────────────────────────
#
# Symptom: 40 simultaneous requests to /api/live/quotes across 12 symbols took
# 6.9 s in production, with the server otherwise idle.
# Cause: the service took one asyncio.Lock per stale symbol and held them all
# across the FMP call, so two callers with any symbol in common ran one after
# the other, each paying a full FMP round trip. Five different symbol sets
# meant five calls end to end.
# Fix: stale symbols go on one queue; one FMP call at a time carries whatever
# is queued; a symbol already asked for is waited on, not asked for again.


def test_overlapping_callers_are_answered_by_two_calls_not_one_each(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "UNH", "XOM", "WMT"]
    batches: list[list[str]] = []
    in_flight = 0
    most_in_flight = 0

    async def slow_batch(batch: list[str]) -> list[dict]:
        nonlocal in_flight, most_in_flight
        batches.append(list(batch))
        in_flight += 1
        most_in_flight = max(most_in_flight, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return [_quote_payload(s) for s in batch]

    mock_fmp.get_quotes_batch.side_effect = slow_batch

    async def forty_callers():
        # Five different lists, each sharing symbols with the others.
        return await asyncio.gather(*(
            service.get_quotes(symbols[i % 5:i % 5 + 8]) for i in range(40)
        ))

    results = asyncio.run(forty_callers())

    for i, result in enumerate(results):
        assert set(result) == set(symbols[i % 5:i % 5 + 8])
    # The old code made five calls here, strictly one after another.
    assert len(batches) <= 2
    # Every symbol went to FMP exactly once.
    sent = [s for batch in batches for s in batch]
    assert sorted(sent) == sorted(symbols)
    # And never two FMP quote calls at the same time (trap 15).
    assert most_in_flight == 1


def test_symbols_asked_for_during_a_call_ride_on_the_next_one(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    batches: list[list[str]] = []

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def batch_call(batch: list[str]) -> list[dict]:
            batches.append(list(batch))
            if len(batches) == 1:
                started.set()
                await release.wait()
            return [_quote_payload(s) for s in batch]

        mock_fmp.get_quotes_batch.side_effect = batch_call
        first = asyncio.ensure_future(service.get_quotes(["AAPL"]))
        await started.wait()
        # While AAPL is out: one caller wants AAPL again, two want new symbols.
        again = asyncio.ensure_future(service.get_quotes(["AAPL"]))
        others = [asyncio.ensure_future(service.get_quotes([s])) for s in ("MSFT", "NVDA")]
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(first, again, *others)

    results = asyncio.run(scenario())
    assert [set(r) for r in results] == [{"AAPL"}, {"AAPL"}, {"MSFT"}, {"NVDA"}]
    assert batches == [["AAPL"], ["MSFT", "NVDA"]]


def test_a_failed_call_reaches_its_callers_and_the_next_request_tries_again(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    mock_fmp.get_quotes_batch.side_effect = RuntimeError("FMP is down")

    async def two_callers():
        return await asyncio.gather(
            service.get_quotes(["AAPL"]), service.get_quotes(["AAPL", "MSFT"]),
            return_exceptions=True,
        )

    results = asyncio.run(two_callers())
    assert all(isinstance(r, RuntimeError) for r in results)

    mock_fmp.get_quotes_batch.side_effect = None
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 201.0)]
    assert asyncio.run(service.get_quotes(["AAPL"]))["AAPL"].price == 201.0


def test_a_caller_that_gives_up_does_not_strand_the_others(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    async def scenario():
        release = asyncio.Event()

        async def batch_call(batch: list[str]) -> list[dict]:
            await release.wait()
            return [_quote_payload(s) for s in batch]

        mock_fmp.get_quotes_batch.side_effect = batch_call
        leaver = asyncio.ensure_future(service.get_quotes(["AAPL"]))
        await asyncio.sleep(0)
        stayer = asyncio.ensure_future(service.get_quotes(["AAPL"]))
        await asyncio.sleep(0)
        leaver.cancel()
        release.set()
        return await stayer

    assert set(asyncio.run(scenario())) == {"AAPL"}


def test_the_service_works_from_a_second_event_loop_after_a_first_used_it(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    """Trap 22, the 2026-06-07 Market Pulse outage: the locks this service
    used to keep were bound to whichever loop touched them first. It keeps
    nothing loop-bound across loops now, so a second loop simply works."""
    async def batch_call(batch: list[str]) -> list[dict]:
        await asyncio.sleep(0)
        return [_quote_payload(s) for s in batch]

    mock_fmp.get_quotes_batch.side_effect = batch_call
    assert set(asyncio.run(service.get_quotes(["AAPL"]))) == {"AAPL"}
    assert set(asyncio.run(service.get_quotes(["MSFT"]))) == {"MSFT"}


def test_cached_returns_the_last_quote_without_fetching(
    service: LiveQuoteService, mock_fmp: AsyncMock,
) -> None:
    assert service.cached("AAPL") is None
    mock_fmp.get_quotes_batch.return_value = [_quote_payload("AAPL", 200.0)]
    asyncio.run(service.get_quotes(["AAPL"]))
    mock_fmp.get_quotes_batch.reset_mock()

    assert service.cached("aapl").price == 200.0
    assert service.cached("AAPL", max_age=0) is None
    assert mock_fmp.get_quotes_batch.await_count == 0
