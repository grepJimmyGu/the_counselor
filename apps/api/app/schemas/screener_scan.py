"""Market Screener scan/count request + response schemas (PRD-23a §3.5).

Distinct from `screener.py` (the `/api/screener` preset filters). These back
the reading-driven `/api/screen` endpoints: a composed reading over a universe
-> the matched basket.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.strategy import StrategyJSON, StrategyRule

# The fixed universe tiers. `sector_<key>` is validated by prefix below.
_FIXED_UNIVERSE_IDS = frozenset({"symbols", "watchlist", "portfolio", "sp500"})
_SECTOR_PREFIX = "sector_"


class ScreenScanRequest(BaseModel):
    # One of: "symbols" | "watchlist" | "portfolio" | "sp500" | "sector_<key>".
    universe_id: str = Field(..., description="The universe tier to screen.")
    # The composed reading — the same custom_build rule shape the composer
    # produces. Folded left-to-right via each rule's logic_with_prior.
    rules: List[StrategyRule] = Field(default_factory=list)
    # Supplies the membership for the client-supplied tiers (entered symbols /
    # watchlist / portfolio). Ignored for sp500 / sector.
    symbols: Optional[List[str]] = None

    @field_validator("universe_id")
    @classmethod
    def _validate_universe_id(cls, v: str) -> str:
        # Reject bad ids at the request boundary -> 422, instead of letting the
        # resolver's ValueError surface as an unhandled 500 on these
        # anonymous-reachable endpoints.
        if v in _FIXED_UNIVERSE_IDS:
            return v
        if v.startswith(_SECTOR_PREFIX) and len(v) > len(_SECTOR_PREFIX):
            return v
        raise ValueError(
            "universe_id must be one of "
            "symbols|watchlist|portfolio|sp500|sector_<key>"
        )


class ScreenScanResponse(BaseModel):
    matched: List[str]
    # symbol -> satisfied rule readings ("why this matched").
    readings: Dict[str, List[str]]
    as_of_date: Optional[date]
    universe_size: int
    matched_count: int
    # Rule primitives not covered by the daily snapshot (can't match yet).
    unsupported_primitives: List[str] = Field(default_factory=list)
    # Covered primitives whose rule overrides the indicator params — scanned at
    # default periods (an approximation; the rank step uses the real params).
    default_param_primitives: List[str] = Field(default_factory=list)


class ScreenCountResponse(BaseModel):
    """The live match-count funnel — `matched_count` only, no symbol list, so
    it stays a sub-100ms read as the user tunes their reading."""

    matched_count: int
    universe_size: int
    as_of_date: Optional[date]
    unsupported_primitives: List[str] = Field(default_factory=list)
    default_param_primitives: List[str] = Field(default_factory=list)


class ScreenRankRequest(ScreenScanRequest):
    """Scan, then backtest + rank the matched subset. Carries the full reading
    as a StrategyJSON so the rank can backtest each survivor."""

    strategy: StrategyJSON
    top_k: int = Field(50, ge=1, le=200)


class RankedSymbol(BaseModel):
    symbol: str
    total_return: float
    annualized_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    readings: List[str] = Field(default_factory=list)


class ScreenRankResponse(BaseModel):
    ranked: List[RankedSymbol]
    as_of_date: Optional[date]
    matched_count: int
    backtested_count: int
    dropped_count: int
    universe_size: int
    unsupported_primitives: List[str] = Field(default_factory=list)
    default_param_primitives: List[str] = Field(default_factory=list)


class ScreenSaveRequest(BaseModel):
    """Persist + track a standing screen (PRD-23c). Only standing universes
    (sp500 / sector_<key>) are trackable — a single entered symbol is the
    build-from-scratch / active-execution path, not a basket that gains and
    loses members."""

    title: str = Field(..., min_length=3, max_length=120)
    universe_id: str = Field(...)
    rules: List[StrategyRule] = Field(default_factory=list)
    # "daily" (the close-based screen) | "intraday" (mid-session, Quant-only).
    bar_resolution: str = Field("daily")

    @field_validator("universe_id")
    @classmethod
    def _standing_only(cls, v: str) -> str:
        if v == "sp500" or (
            v.startswith(_SECTOR_PREFIX) and len(v) > len(_SECTOR_PREFIX)
        ):
            return v
        raise ValueError(
            "Only standing universes (sp500 | sector_<key>) can be tracked"
        )

    @field_validator("bar_resolution")
    @classmethod
    def _valid_resolution(cls, v: str) -> str:
        if v in ("daily", "intraday"):
            return v
        raise ValueError("bar_resolution must be 'daily' or 'intraday'")


class ScreenSaveResponse(BaseModel):
    saved_strategy_id: str
    # The seeded current basket as of the save (so the UI shows it immediately).
    basket: List[str]
    as_of_date: Optional[date]
    universe_size: int


class ScreenBasketEntry(BaseModel):
    """One membership stint in a screen's basket (PRD-23c dashboard history)."""

    symbol: str
    entered_date: date
    exited_date: Optional[date]
    is_current: bool


class SavedScreenSummary(BaseModel):
    saved_strategy_id: str
    title: str
    universe_id: str
    basket_size: int  # current members (exited_date IS NULL)
    created_at: Optional[str] = None


class SavedScreensListResponse(BaseModel):
    screens: List[SavedScreenSummary]


class SavedScreenDetail(SavedScreenSummary):
    rules: List[StrategyRule]
    basket: List[str]  # current members, symbols only
    history: List[ScreenBasketEntry]  # every stint, newest first
