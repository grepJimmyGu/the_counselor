from __future__ import annotations

from unittest.mock import AsyncMock, call

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


async def test_get_quotes_batch_uses_path_based_quote_endpoint() -> None:
    """Primary path is /stable/quote/SYM1,SYM2,... — the fmpsdk convention."""
    client = FMPClient()
    client._get = AsyncMock(return_value=[_raw_quote("AAPL"), _raw_quote("MSFT")])

    result = await client.get_quotes_batch(["aapl", "msft"])

    assert [r["symbol"] for r in result] == ["AAPL", "MSFT"]
    client._get.assert_awaited_once_with("/quote/AAPL,MSFT", {})


async def test_get_quotes_batch_chunks_at_100_concurrent() -> None:
    """500 symbols split into 5 chunks of 100, fired concurrently via gather."""
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        syms = path.replace("/quote/", "").split(",")
        return [_raw_quote(s) for s in syms]

    client._get = AsyncMock(side_effect=fake_get)
    symbols = [f"S{i:03d}" for i in range(500)]

    result = await client.get_quotes_batch(symbols)

    assert len(result) == 500
    assert client._get.await_count == 5
    expected_chunks = [
        call(f"/quote/{','.join(symbols[i:i + 100])}", {})
        for i in range(0, 500, 100)
    ]
    assert client._get.await_args_list == expected_chunks


async def test_get_quotes_batch_falls_back_to_individual_for_missing() -> None:
    """If the path-batch returns partial data, missing symbols fall back to get_quote."""
    client = FMPClient()
    client._get = AsyncMock(return_value=[_raw_quote("AAPL")])  # batch returns only AAPL
    client.get_quote = AsyncMock(side_effect=lambda sym: _raw_quote(sym))

    result = await client.get_quotes_batch(["AAPL", "MSFT", "TSLA"])

    symbols = {r["symbol"] for r in result}
    assert symbols == {"AAPL", "MSFT", "TSLA"}
    # Path-batch fired once for the chunk; individual fallback for the 2 missing.
    assert client._get.await_count == 1
    assert client.get_quote.await_count == 2
    fallback_syms = {c.args[0] for c in client.get_quote.await_args_list}
    assert fallback_syms == {"MSFT", "TSLA"}


async def test_get_quotes_batch_handles_complete_batch_failure() -> None:
    """If path-batch raises for all chunks, every symbol falls back to get_quote."""
    client = FMPClient()
    client._get = AsyncMock(side_effect=RuntimeError("FMP 500"))
    client.get_quote = AsyncMock(side_effect=lambda sym: _raw_quote(sym))

    result = await client.get_quotes_batch(["AAPL", "MSFT"])

    assert {r["symbol"] for r in result} == {"AAPL", "MSFT"}
    assert client.get_quote.await_count == 2


async def test_get_quotes_batch_deduplicates_symbols() -> None:
    client = FMPClient()
    client._get = AsyncMock(return_value=[_raw_quote("AAPL")])

    await client.get_quotes_batch(["AAPL", "aapl", "AAPL"])

    assert client._get.await_count == 1
    client._get.assert_awaited_once_with("/quote/AAPL", {})


async def test_get_quotes_batch_normalizes_brk_dot_b_to_brk_dash_b() -> None:
    """BRK.B (caller convention) → BRK-B for FMP; response remapped back to BRK.B."""
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        # Confirm we sent the FMP-style hyphenated symbol
        assert "BRK-B" in path
        assert "BRK.B" not in path
        return [{"symbol": "BRK-B", "price": 483.57, "change": -2.81, "changesPercentage": -0.58}]

    client._get = AsyncMock(side_effect=fake_get)

    result = await client.get_quotes_batch(["BRK.B"])

    assert len(result) == 1
    # Response symbol should be remapped back to caller's dot convention
    assert result[0]["symbol"] == "BRK.B"


async def test_get_quote_normalizes_brk_dot_b_to_brk_dash_b() -> None:
    """Single get_quote applies the same dot→hyphen translation for class shares."""
    client = FMPClient()

    async def fake_get(path: str, params: dict):
        assert params["symbol"] == "BRK-B"
        return [{"symbol": "BRK-B", "price": 483.57}]

    client._get = AsyncMock(side_effect=fake_get)

    result = await client.get_quote("BRK.B")

    assert result is not None
    assert result["symbol"] == "BRK.B"
    assert result["price"] == 483.57


async def test_get_quotes_batch_empty_input() -> None:
    client = FMPClient()
    client._get = AsyncMock()
    client.get_quote = AsyncMock()

    result = await client.get_quotes_batch([])

    assert result == []
    client._get.assert_not_awaited()
    client.get_quote.assert_not_awaited()
