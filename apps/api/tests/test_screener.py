"""Tests for PRD-07 stock screener service."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.schemas.screener import ScreenerFilters
from app.services.screener_service import ScreenerService


def _make_symbol(symbol: str, name: str, sector: str, market_cap: float, pe_ratio: float | None = None):
    m = MagicMock()
    m.symbol = symbol
    m.name = name
    m.sector = sector
    m.industry = "Software"
    m.exchange = "NASDAQ"
    m.country = "US"
    m.market_cap = market_cap
    m.market_cap_category = "large"
    m.pe_ratio = pe_ratio
    m.dividend_yield = None
    m.beta = 1.2
    m.week_52_high = None
    m.week_52_low = None
    m.is_active = True
    return m


def test_screener_returns_results():
    service = ScreenerService()
    mock_db = MagicMock()

    symbols = [
        _make_symbol("AAPL", "Apple Inc.", "Technology", 2900e9, 30.0),
        _make_symbol("MSFT", "Microsoft", "Technology", 2500e9, 35.0),
    ]

    # Mock scalars().all() for the results query
    mock_db.execute.return_value.scalars.return_value.all.return_value = symbols
    # Mock scalar() for the count query
    mock_db.scalar.return_value = 2

    filters = ScreenerFilters(sector="Technology")
    result = service.screen(mock_db, filters)

    assert result.total == 2
    assert len(result.results) == 2
    assert result.results[0].symbol == "AAPL"


def test_screener_empty_results():
    service = ScreenerService()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    mock_db.scalar.return_value = 0

    filters = ScreenerFilters(sector="NonExistentSector")
    result = service.screen(mock_db, filters)

    assert result.total == 0
    assert result.results == []


def test_screener_filters_applied_correctly():
    service = ScreenerService()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    mock_db.scalar.return_value = 0

    filters = ScreenerFilters(sector="Technology", min_pe=10.0, max_pe=40.0)
    result = service.screen(mock_db, filters)

    assert result.filters_applied.get("sector") == "Technology"
    assert result.filters_applied.get("min_pe") == 10.0
    assert result.filters_applied.get("max_pe") == 40.0
