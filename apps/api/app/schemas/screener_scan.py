"""Market Screener scan/count request + response schemas (PRD-23a §3.5).

Distinct from `screener.py` (the `/api/screener` preset filters). These back
the reading-driven `/api/screen` endpoints: a composed reading over a universe
-> the matched basket.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.strategy import StrategyRule


class ScreenScanRequest(BaseModel):
    # One of: "symbols" | "watchlist" | "portfolio" | "sp500" | "sector_<key>".
    universe_id: str = Field(..., description="The universe tier to screen.")
    # The composed reading — the same custom_build rule shape the composer
    # produces. Folded left-to-right via each rule's logic_with_prior.
    rules: List[StrategyRule] = Field(default_factory=list)
    # Supplies the membership for the client-supplied tiers (entered symbols /
    # watchlist / portfolio). Ignored for sp500 / sector.
    symbols: Optional[List[str]] = None


class ScreenScanResponse(BaseModel):
    matched: List[str]
    # symbol -> satisfied rule readings ("why this matched").
    readings: Dict[str, List[str]]
    as_of_date: Optional[date]
    universe_size: int
    matched_count: int
    # Rule primitives not covered by the daily snapshot (can't match yet).
    unsupported_primitives: List[str] = Field(default_factory=list)


class ScreenCountResponse(BaseModel):
    """The live match-count funnel — `matched_count` only, no symbol list, so
    it stays a sub-100ms read as the user tunes their reading."""

    matched_count: int
    universe_size: int
    as_of_date: Optional[date]
    unsupported_primitives: List[str] = Field(default_factory=list)
