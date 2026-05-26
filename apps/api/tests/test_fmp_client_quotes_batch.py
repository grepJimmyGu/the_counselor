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


async def test_get_quotes_batch_uses_quote_endpoint() -> None:
    """Batch fetch uses /stable/quote with comma-separated symbol param."""
    client = FMPClient()
    client._get = AsyncMock(return_value=[_payload("AAPL"), _payload("MSFT")])

    result = await client.get_quotes_batch(["aapl", "msft"])

    assert [row["symbol"] for row in result] == ["AAPL", "MSFT"]
    client._get.assert_awaited_once_with(
        "/quote",
        {"symbol": "AAPL,MSFT"},
    )


async def test_get_quotes_batch_handles_mixed_asset_types() -> None:
    """/stable/quote returns stocks, ETFs, and indices uniformly — no separate fallbacks."""
    client = FMPClient()
    client._get = AsyncMock(return_value=[_payload("AAPL"), _payload("XLK"), _payload("XLE")])

    result = await client.get_quotes_batch(["AAPL", "XLK", "XLE"])

    assert [row["symbol"] for row in result] == ["AAPL", "XLK", "XLE"]
    client._get.assert_awaited_once_with(
        "/quote",
        {"symbol": "AAPL,XLK,XLE"},
    )


async def test_get_quotes_batch_chunks_large_symbol_lists() -> None:
    """500 symbols are split into chunks of 100 and fetched concurrently."""
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        symbols = params["symbol"].split(",")
        return [_payload(symbol) for symbol in symbols]

    client._get = AsyncMock(side_effect=fake_get)
    symbols = [f"S{i:03d}" for i in range(205)]

    result = await client.get_quotes_batch(symbols)

    assert len(result) == 205
    assert client._get.await_args_list == [
        call("/quote", {"symbol": ",".join(symbols[:100])}),
        call("/quote", {"symbol": ",".join(symbols[100:200])}),
        call("/quote", {"symbol": ",".join(symbols[200:205])}),
    ]


async def test_get_quotes_batch_skips_symbols_not_returned_by_fmp() -> None:
    """Symbols FMP doesn't recognise are silently omitted (not an error)."""
    client = FMPClient()
    client._get = AsyncMock(return_value=[])

    symbols = [f"S{i:03d}" for i in range(30)]
    result = await client.get_quotes_batch(symbols)

    assert result == []
