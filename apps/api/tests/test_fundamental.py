"""Tests for PRD-06 fundamental data services."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.fundamental import CompanyProfile, KeyMetrics
from app.services.fundamental_service import FundamentalService, _market_cap_category


# ── Unit tests for market cap category helper ─────────────────────────────────

def test_market_cap_category_mega():
    assert _market_cap_category(250e9) == "mega"

def test_market_cap_category_large():
    assert _market_cap_category(15e9) == "large"

def test_market_cap_category_mid():
    assert _market_cap_category(5e9) == "mid"

def test_market_cap_category_small():
    assert _market_cap_category(500e6) == "small"

def test_market_cap_category_micro():
    assert _market_cap_category(100e6) == "micro"

def test_market_cap_category_none():
    assert _market_cap_category(None) is None


# ── FMPAdapter tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fmp_adapter_get_profile():
    from app.services.adapters.fmp_adapter import FMPAdapter

    mock_raw = {
        "companyName": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "exchangeShortName": "NASDAQ",
        "country": "US",
        "currency": "USD",
        "description": "Apple designs consumer electronics.",
        "ceo": "Tim Cook",
        "fullTimeEmployees": "150000",
        "mktCap": 2900000000000,
        "beta": 1.2,
        "range": "164.08-199.62",
        "isEtf": False,
        "isActivelyTrading": True,
    }

    with patch.object(FMPAdapter, "_get_peers_safe", new_callable=AsyncMock, return_value=["MSFT", "GOOGL"]):
        with patch("app.services.fmp_client.FMPClient.get_profile", new_callable=AsyncMock, return_value=mock_raw):
            adapter = FMPAdapter()
            profile = await adapter.get_profile("AAPL")

    assert profile.symbol == "AAPL"
    assert profile.name == "Apple Inc."
    assert profile.sector == "Technology"
    assert profile.industry == "Consumer Electronics"
    assert profile.week_52_high == 199.62
    assert profile.week_52_low == 164.08
    assert profile.employees == 150000
    assert profile.peers == ["MSFT", "GOOGL"]
    assert profile.data_source == "fmp"


@pytest.mark.asyncio
async def test_fmp_adapter_get_key_metrics():
    from app.services.adapters.fmp_adapter import FMPAdapter

    mock_raw = {
        "peRatioTTM": 31.03,
        "pbRatioTTM": 47.49,
        "priceToSalesRatioTTM": 7.83,
        "roeTTM": 1.45,
        "debtToEquityTTM": 2.16,
        "currentRatioTTM": 0.87,
        "freeCashFlowYieldTTM": 0.036,
        "dividendYieldPercentageTTM": 0.47,
    }

    with patch("app.services.fmp_client.FMPClient.get_key_metrics", new_callable=AsyncMock, return_value=mock_raw):
        adapter = FMPAdapter()
        metrics = await adapter.get_key_metrics("AAPL")

    assert metrics.pe_ratio == pytest.approx(31.03)
    assert metrics.roe == pytest.approx(1.45)
    assert metrics.debt_to_equity == pytest.approx(2.16)
    assert metrics.data_source == "fmp"


# ── FundamentalService fallback tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_fundamental_service_falls_back_to_yfinance_on_rate_limit():
    from app.services.fmp_client import FMPRateLimitError

    mock_profile = CompanyProfile(
        symbol="AAPL", name="Apple Inc.", sector="Technology", data_source="yfinance"
    )

    service = FundamentalService()

    with patch.object(service._fmp, "get_profile", side_effect=FMPRateLimitError("rate limited")):
        with patch.object(service._yf, "get_profile", new_callable=AsyncMock, return_value=mock_profile):
            # Bypass cache by providing a mock db session with no cached row
            mock_db = MagicMock()
            mock_db.scalar.return_value = None
            result = await service.get_profile(mock_db, "AAPL")

    assert result.data_source == "yfinance"
    assert result.symbol == "AAPL"


@pytest.mark.asyncio
async def test_fundamental_service_falls_back_on_not_configured():
    from app.services.fmp_client import FMPNotConfiguredError

    mock_profile = CompanyProfile(
        symbol="MSFT", name="Microsoft", sector="Technology", data_source="yfinance"
    )

    service = FundamentalService()

    with patch.object(service._fmp, "get_profile", side_effect=FMPNotConfiguredError("not configured")):
        with patch.object(service._yf, "get_profile", new_callable=AsyncMock, return_value=mock_profile):
            mock_db = MagicMock()
            mock_db.scalar.return_value = None
            result = await service.get_profile(mock_db, "MSFT")

    assert result.data_source == "yfinance"


# ── FMPClient error tests ──────────────────────────────────────────────────────

def test_fmp_client_raises_not_configured_without_key():
    from app.services.fmp_client import FMPClient, FMPNotConfiguredError

    with patch("app.services.fmp_client.get_settings") as mock_settings:
        mock_settings.return_value.financial_modeling_prep_api_key = ""
        mock_settings.return_value.api_timeout_seconds = 20.0
        client = FMPClient()
        with pytest.raises(FMPNotConfiguredError):
            client._api_key()
