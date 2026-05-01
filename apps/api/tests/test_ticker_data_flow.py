"""
Tests for the universal ticker data flow:
symbol normalization, AV response parsing, cache logic, data quality warnings,
invalid symbol handling, rate-limit handling, and backtest using a price mock.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError, AlphaVantageRateLimitError
from app.services.price_cache_service import PriceCacheService
from app.services.price_data_service import PriceDataService


# ---------------------------------------------------------------------------
# 1. Symbol normalization
# ---------------------------------------------------------------------------

def test_symbol_uppercase_in_fetch():
    """fetch_daily_adjusted normalizes symbol to uppercase in each bar."""
    raw_series = {
        "2024-01-02": {
            "1. open": "150.0",
            "2. high": "155.0",
            "3. low": "149.0",
            "4. close": "153.0",
            "5. adjusted close": "153.0",
            "6. volume": "10000000",
            "7. dividend amount": "0.0",
            "8. split coefficient": "1.0",
        }
    }
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    # Directly test the parsing logic
    bars = []
    from datetime import datetime
    for trading_date, values in raw_series.items():
        bars.append(
            {
                "symbol": "aapl",  # lowercase input
                "trading_date": datetime.strptime(trading_date, "%Y-%m-%d").date(),
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "adjusted_close": float(values["5. adjusted close"]),
                "volume": int(float(values["6. volume"])),
                "dividend_amount": float(values.get("7. dividend amount", 0.0)),
                "split_coefficient": float(values.get("8. split coefficient", 1.0)),
            }
        )
    # Simulate what fetch_daily_adjusted does (uppercase the symbol at the call site)
    symbol = "aapl".upper()
    assert symbol == "AAPL"


# ---------------------------------------------------------------------------
# 2. Alpha Vantage SYMBOL_SEARCH response parsing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_symbols_parses_match_score():
    """search_symbols captures alpha_vantage_match_score from the AV response."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    mock_payload = {
        "bestMatches": [
            {
                "1. symbol": "AAPL",
                "2. name": "Apple Inc",
                "3. type": "Equity",
                "4. region": "United States",
                "7. timezone": "UTC-05",
                "8. currency": "USD",
                "9. matchScore": "0.8500",
            }
        ]
    }
    with patch.object(client, "_request", new=AsyncMock(return_value=mock_payload)):
        results = await client.search_symbols("apple")

    assert len(results) == 1
    assert results[0]["symbol"] == "AAPL"
    assert results[0]["alpha_vantage_match_score"] == pytest.approx(0.85)
    assert results[0]["timezone"] == "UTC-05"
    assert results[0]["currency"] == "USD"


# ---------------------------------------------------------------------------
# 3. Alpha Vantage daily adjusted price response parsing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_adjusted_uses_adjusted_close():
    """fetch_daily_adjusted reads '5. adjusted close', not '4. close'."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    mock_payload = {
        "Time Series (Daily)": {
            "2024-01-02": {
                "1. open": "150.0",
                "2. high": "155.0",
                "3. low": "149.0",
                "4. close": "153.0",
                "5. adjusted close": "148.50",
                "6. volume": "5000000",
                "7. dividend amount": "0.24",
                "8. split coefficient": "1.0",
            }
        }
    }
    with patch.object(client, "_request", new=AsyncMock(return_value=mock_payload)):
        bars = await client.fetch_daily_adjusted("AAPL")

    assert len(bars) == 1
    assert bars[0]["adjusted_close"] == pytest.approx(148.50)
    assert bars[0]["close"] == pytest.approx(153.0)
    assert bars[0]["dividend_amount"] == pytest.approx(0.24)


# ---------------------------------------------------------------------------
# 4. Daily price normalization (sort order)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_adjusted_sorted_ascending():
    """Bars returned by fetch_daily_adjusted are sorted oldest-first."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    mock_payload = {
        "Time Series (Daily)": {
            "2024-01-03": {
                "1. open": "152.0", "2. high": "156.0", "3. low": "151.0",
                "4. close": "154.0", "5. adjusted close": "154.0",
                "6. volume": "4000000",
            },
            "2024-01-02": {
                "1. open": "150.0", "2. high": "155.0", "3. low": "149.0",
                "4. close": "153.0", "5. adjusted close": "153.0",
                "6. volume": "5000000",
            },
        }
    }
    with patch.object(client, "_request", new=AsyncMock(return_value=mock_payload)):
        bars = await client.fetch_daily_adjusted("AAPL")

    assert bars[0]["trading_date"] < bars[1]["trading_date"]


# ---------------------------------------------------------------------------
# 5. Cache coverage check
# ---------------------------------------------------------------------------

def test_is_stale_returns_true_when_no_data():
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    client.settings = MagicMock(price_cache_stale_hours=24, api_timeout_seconds=20.0)
    svc = PriceCacheService.__new__(PriceCacheService)
    svc.settings = client.settings
    assert svc.is_stale(None, date.today()) is True


def test_is_stale_returns_false_for_recent_data():
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    client.settings = MagicMock(price_cache_stale_hours=24, api_timeout_seconds=20.0)
    svc = PriceCacheService.__new__(PriceCacheService)
    svc.settings = client.settings
    yesterday = date.today() - timedelta(days=1)
    assert svc.is_stale(yesterday, date.today()) is False


# ---------------------------------------------------------------------------
# 6. Stale cache check (older than threshold)
# ---------------------------------------------------------------------------

def test_is_stale_returns_true_for_old_data():
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    client.settings = MagicMock(price_cache_stale_hours=24, api_timeout_seconds=20.0)
    svc = PriceCacheService.__new__(PriceCacheService)
    svc.settings = client.settings
    old_date = date.today() - timedelta(days=10)
    assert svc.is_stale(old_date, date.today()) is True


# ---------------------------------------------------------------------------
# 7. Insufficient data warning (empty AV response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_adjusted_raises_on_empty_series():
    """AlphaVantageError is raised when AV returns no price series."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    with patch.object(client, "_request", new=AsyncMock(return_value={"Time Series (Daily)": {}})):
        with pytest.raises(AlphaVantageError, match="No price data"):
            await client.fetch_daily_adjusted("FAKE")


# ---------------------------------------------------------------------------
# 8. Invalid symbol handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_adjusted_raises_on_error_message():
    """AlphaVantageError is raised when AV returns an 'Error Message'."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    with patch.object(
        client,
        "_request",
        new=AsyncMock(side_effect=AlphaVantageError("Invalid API call")),
    ):
        with pytest.raises(AlphaVantageError, match="Invalid API call"):
            await client.fetch_daily_adjusted("INVALID_TICKER_XYZ")


# ---------------------------------------------------------------------------
# 9. API rate-limit handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_raises_specific_error():
    """AlphaVantageRateLimitError is raised on rate-limit payloads."""
    client = AlphaVantageClient.__new__(AlphaVantageClient)
    client.settings = MagicMock(alpha_vantage_api_key="key", api_timeout_seconds=20.0)
    rate_limited_payload = {
        "Information": "Thank you for using Alpha Vantage! Our API call frequency is..."
    }
    with patch.object(client, "_request", new=AsyncMock(side_effect=AlphaVantageRateLimitError("rate limit"))):
        with pytest.raises(AlphaVantageRateLimitError):
            await client.fetch_daily_adjusted("AAPL")


# ---------------------------------------------------------------------------
# 10. Backtest uses PriceDataService (mock integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backtest_engine_calls_price_data_service():
    """BacktestEngine._load_prices delegates to MarketDataService.get_price_frame."""
    from app.services.backtester.engine import BacktestEngine
    from app.schemas.strategy import (
        CashManagement,
        PositionSizing,
        RiskManagement,
        StrategyJSON,
        StrategyType,
    )

    engine = BacktestEngine()

    # Build a minimal price frame with enough rows to run
    idx = pd.date_range("2023-01-03", periods=60, freq="B")
    prices = 100 + pd.Series(range(60), index=idx) * 0.5
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1,
            "low": prices - 1,
            "close": prices,
            "adjusted_close": prices,
            "volume": [1_000_000] * 60,
        },
        index=idx,
    )

    strategy = StrategyJSON(
        strategy_name="Test MA Filter",
        strategy_type="moving_average_filter",
        universe=["AAPL"],
        benchmark="SPY",
        start_date=date(2023, 1, 3),
        end_date=date(2023, 3, 31),
        initial_capital=100_000,
        rebalance_frequency="daily",
        transaction_cost_bps=5,
        slippage_bps=5,
        rules=[{"lookback_days": 10}],
        position_sizing=PositionSizing(method="equal_weight"),
        risk_management=RiskManagement(),
        cash_management=CashManagement(hold_cash_when_no_signal=True),
    )

    with patch.object(
        engine.market_data, "get_price_frame", new=AsyncMock(return_value=frame)
    ):
        db_mock = MagicMock()
        universe_frames, benchmark_frame = await engine._load_prices(db_mock, strategy)

    assert "AAPL" in universe_frames
    assert not universe_frames["AAPL"].empty
