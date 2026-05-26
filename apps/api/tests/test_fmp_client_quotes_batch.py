from __future__ import annotations

from unittest.mock import AsyncMock

from app.services.fmp_client import FMPClient


def _raw_quote(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 100.0,
        "change": 1.0,
        "changesPercentage": 1.0,
        "dayHigh": 101.0,
        "dayLow": 99.0,
        "volume": 1_000_000,
        "marketCap": 1_000_000_000.0,
        "name": symbol,
        "exchange": "NASDAQ",
    }


async def test_get_quotes_batch_calls_get_quote_per_symbol() -> None:
    """get_quotes_batch fires one get_quote call per symbol — FMP /stable/quote
    does not support comma-separated multi-symbol queries."""
    client = FMPClient()
    client.get_quote = AsyncMock(side_effect=lambda sym: _raw_quote(sym))

    result = await client.get_quotes_batch(["AAPL", "msft"])

    assert client.get_quote.await_count == 2
    assert {r["symbol"] for r in result} == {"AAPL", "MSFT"}


async def test_get_quotes_batch_deduplicates_symbols() -> None:
    """Duplicate symbols (case-insensitive) are only fetched once."""
    client = FMPClient()
    client.get_quote = AsyncMock(side_effect=lambda sym: _raw_quote(sym))

    await client.get_quotes_batch(["AAPL", "aapl", "AAPL"])

    assert client.get_quote.await_count == 1


async def test_get_quotes_batch_handles_fmp_returning_none() -> None:
    """Symbols where get_quote returns None are silently omitted."""
    client = FMPClient()

    async def fake_get_quote(sym: str):
        if sym == "AAPL":
            return _raw_quote("AAPL")
        return None

    client.get_quote = AsyncMock(side_effect=fake_get_quote)

    result = await client.get_quotes_batch(["AAPL", "BADTICKER"])

    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"


async def test_get_quotes_batch_large_list_fetches_all() -> None:
    """500 symbols are all fetched, bounded by the semaphore."""
    client = FMPClient()
    call_count = 0

    async def fake_get_quote(sym: str):
        nonlocal call_count
        call_count += 1
        return _raw_quote(sym)

    client.get_quote = AsyncMock(side_effect=fake_get_quote)
    symbols = [f"S{i:03d}" for i in range(500)]

    result = await client.get_quotes_batch(symbols)

    assert call_count == 500
    assert len(result) == 500


async def test_get_quotes_batch_empty_input() -> None:
    client = FMPClient()
    client.get_quote = AsyncMock()

    result = await client.get_quotes_batch([])

    assert result == []
    client.get_quote.assert_not_awaited()
