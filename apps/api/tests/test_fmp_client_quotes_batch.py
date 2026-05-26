from __future__ import annotations

from unittest.mock import AsyncMock, call

from app.services.fmp_client import FMPClient


def _payload(symbol: str) -> dict:
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


async def test_get_quotes_batch_uses_stock_batch_endpoint() -> None:
    client = FMPClient()
    client._get = AsyncMock(return_value=[_payload("AAPL"), _payload("MSFT")])

    result = await client.get_quotes_batch(["aapl", "msft"])

    assert [row["symbol"] for row in result] == ["AAPL", "MSFT"]
    client._get.assert_awaited_once_with(
        "/batch-quote",
        {"symbols": "AAPL,MSFT"},
    )


async def test_get_quotes_batch_uses_etf_batch_for_stock_batch_misses() -> None:
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        if path == "/batch-quote":
            return [_payload("AAPL")]
        if path == "/batch-etf-quotes":
            return [_payload("XLK"), _payload("XLE")]
        return []

    client._get = AsyncMock(side_effect=fake_get)

    result = await client.get_quotes_batch(["AAPL", "XLK", "XLE"])

    assert [row["symbol"] for row in result] == ["AAPL", "XLK", "XLE"]
    assert client._get.await_args_list == [
        call("/batch-quote", {"symbols": "AAPL,XLK,XLE"}),
        call("/batch-etf-quotes", {"symbols": "XLK,XLE"}),
    ]


async def test_get_quotes_batch_chunks_large_symbol_lists() -> None:
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        symbols = params["symbols"].split(",")
        return [_payload(symbol) for symbol in symbols]

    client._get = AsyncMock(side_effect=fake_get)
    symbols = [f"S{i:03d}" for i in range(205)]

    result = await client.get_quotes_batch(symbols)

    assert len(result) == 205
    assert client._get.await_args_list == [
        call("/batch-quote", {"symbols": ",".join(symbols[:100])}),
        call("/batch-quote", {"symbols": ",".join(symbols[100:200])}),
        call("/batch-quote", {"symbols": ",".join(symbols[200:205])}),
    ]


async def test_get_quotes_batch_skips_large_individual_fallbacks() -> None:
    client = FMPClient()
    client._get = AsyncMock(return_value=[])
    client.get_quote = AsyncMock(return_value=None)

    symbols = [f"S{i:03d}" for i in range(30)]
    result = await client.get_quotes_batch(symbols)

    assert result == []
    assert client.get_quote.await_count == 0
