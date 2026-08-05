"""Unified smart-search dispatch schema (PRD-27).

One box, three outcomes:
  - COMPANY   — a ticker / company name → the company page (symbol_service).
  - SCREEN    — free text → the existing LLM parser → the parsed *technical*
                rules, ready to run over a standing universe as a scan.
  - AMBIGUOUS — a token that's both a ticker AND reads like a screen → options.

STRATEGY is reserved: a screen result promotes to a strategy via PRD-26, so v1
does not need a separate build-intent branch. Pure-fundamental phrases
("small cap", "P/E < 15") are the deferred fundamental-filter slice — v1 runs
the technical rules the parser extracts and says so in `note`.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchIntent(str, Enum):
    COMPANY = "company"
    SCREEN = "screen"
    STRATEGY = "strategy"  # reserved — screens promote to strategies (PRD-26)
    AMBIGUOUS = "ambiguous"


class SearchScreen(BaseModel):
    """Feeds ScreenScanRequest: a universe + composer-shaped rules.

    PRD-29 mixed query: when the sentence also carries FUNDAMENTAL constraints
    ("small caps that are oversold"), the universe is pre-narrowed by SQL and
    `universe_id` becomes the client tier `"symbols"` with the survivors in
    `symbols` — the scan then runs the technical rules over exactly those.
    Purely technical queries keep a standing universe id and empty `symbols`.
    """

    universe_id: str
    rules: List[dict] = Field(default_factory=list)
    # Present only for the pre-narrowed (mixed) case.
    symbols: List[str] = Field(default_factory=list)
    # Plain-English echo of the fundamental constraints understood, so the UI
    # can show WHICH part of the sentence became a filter.
    fundamental_filters: List[str] = Field(default_factory=list)
    # Set when the fundamental match exceeded the universe cap — the caller
    # must disclose it rather than present a truncated screen as complete.
    universe_truncated_from: Optional[int] = None


class SearchOption(BaseModel):
    intent: SearchIntent
    label: str
    symbol: Optional[str] = None


class SearchParseRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=400)


class ParseResult(BaseModel):
    intent: SearchIntent
    query: str
    # COMPANY
    symbol: Optional[str] = None
    company_name: Optional[str] = None
    # SCREEN
    screen: Optional[SearchScreen] = None
    strategy_json: Optional[dict] = None  # full parsed strategy (composer / promote)
    # AMBIGUOUS
    options: List[SearchOption] = Field(default_factory=list)
    # Transparency: approximation / dropped-filter / universe note.
    note: Optional[str] = None
    confidence: float = 0.0
