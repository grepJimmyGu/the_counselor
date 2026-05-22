"""Unit tests for `market_pulse_narrative_service.generate_narrative`.

Covers the three exit branches:
  1. LLM disabled → returns None
  2. LLM succeeds → returns MarketNarrative
  3. LLM raises → returns None (never blocks the page)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from app.services.market_pulse_narrative_service import (
    MarketNarrative,
    generate_narrative,
)


@dataclass
class _FakeIndex:
    symbol: str
    name: str
    price: Optional[float]
    perf_1d: Optional[float]


@dataclass
class _FakeMacro:
    symbol: str
    label: str
    price: Optional[float]
    perf_1d: Optional[float]


@dataclass
class _FakeSector:
    symbol: str
    name: str
    perf_1d: Optional[float]
    cmf_20: Optional[float]


@dataclass
class _FakeSnapshot:
    indices: list[_FakeIndex]
    macro: list[_FakeMacro]
    sectors: list[_FakeSector]


def _snapshot() -> _FakeSnapshot:
    return _FakeSnapshot(
        indices=[
            _FakeIndex("SPY", "S&P 500", 532.10, 0.0030),
            _FakeIndex("QQQ", "Nasdaq", 462.45, 0.0120),
        ],
        macro=[
            _FakeMacro("TLT", "Long Bonds", 92.30, -0.0050),
            _FakeMacro("VXX", "Volatility", 18.40, -0.0220),
        ],
        sectors=[
            _FakeSector("XLK", "Technology", 0.0140, 0.18),
            _FakeSector("XLE", "Energy", -0.0080, -0.12),
        ],
    )


def test_generate_narrative_returns_none_when_llm_disabled():
    """LLM_PROVIDER unset → service returns None; frontend uses
    deterministic fallback."""
    with patch(
        "app.services.market_pulse_narrative_service.get_llm_gateway"
    ) as mock_gw:
        mock_gw.return_value.is_enabled = False
        result = asyncio.run(generate_narrative(_snapshot()))
    assert result is None


def test_generate_narrative_returns_payload_on_llm_success():
    """LLM gateway returns a valid MarketNarrative → service passes
    through."""
    expected = MarketNarrative(
        headline=(
            "Tech led Wednesday — Nasdaq +1.2% on NVDA strength. "
            "Energy lagged (-0.8%) as oil retraced."
        ),
        sector_rotation="Tech leading; Energy lagging — growth-on rotation.",
        watch_items=["10Y approaching 4.55%", "Tech RS vs SPY at 60d high"],
    )
    with patch(
        "app.services.market_pulse_narrative_service.get_llm_gateway"
    ) as mock_gw:
        gw = mock_gw.return_value
        gw.is_enabled = True
        gw.settings.llm_model = "gpt-4o-mini"
        gw.generate_structured = AsyncMock(return_value=expected)

        result = asyncio.run(generate_narrative(_snapshot()))

    assert result is expected
    gw.generate_structured.assert_awaited_once()


def test_generate_narrative_returns_none_when_llm_raises():
    """Any exception (LLMAdapterError, schema validation, network) →
    None. Never blocks the page."""
    with patch(
        "app.services.market_pulse_narrative_service.get_llm_gateway"
    ) as mock_gw:
        gw = mock_gw.return_value
        gw.is_enabled = True
        gw.settings.llm_model = "gpt-4o-mini"
        gw.generate_structured = AsyncMock(side_effect=RuntimeError("boom"))

        result = asyncio.run(generate_narrative(_snapshot()))

    assert result is None


def test_generate_narrative_accepts_dataclass_and_dict():
    """Snapshot argument can be a dataclass OR a dict OR a Pydantic model;
    the service marshals all three into the prompt."""
    expected = MarketNarrative(
        headline="A " * 12,  # 24 chars, passes min_length=20
        sector_rotation="X" * 30,
        watch_items=[],
    )

    with patch(
        "app.services.market_pulse_narrative_service.get_llm_gateway"
    ) as mock_gw:
        gw = mock_gw.return_value
        gw.is_enabled = True
        gw.settings.llm_model = "gpt-4o-mini"
        gw.generate_structured = AsyncMock(return_value=expected)

        # Dataclass
        r1 = asyncio.run(generate_narrative(_snapshot()))
        # Dict (dataclass-shaped)
        r2 = asyncio.run(
            generate_narrative(
                {
                    "indices": [
                        {"symbol": "SPY", "name": "S&P 500", "price": 532, "perf_1d": 0.003}
                    ],
                    "macro": [],
                    "sectors": [],
                }
            )
        )

    assert r1 is expected
    assert r2 is expected


def test_generate_narrative_unsupported_type_raises():
    """Strings / ints / None should raise TypeError — wiring bug, not a
    silent fallback."""
    with patch(
        "app.services.market_pulse_narrative_service.get_llm_gateway"
    ) as mock_gw:
        mock_gw.return_value.is_enabled = True
        mock_gw.return_value.settings.llm_model = "gpt-4o-mini"

        with pytest.raises(TypeError):
            asyncio.run(generate_narrative("not a snapshot"))
