"""Unified smart-search dispatcher (PRD-27, extended by PRD-29).

POST /api/search/parse — one box, three outcomes: COMPANY (symbol_service),
SCREEN, or AMBIGUOUS.

A SCREEN may mix both halves of a sentence:
  - FUNDAMENTAL ("small caps", "P/E under 15", "healthcare") — extracted
    deterministically by `screen_filter_parser`, resolved to a symbol list with
    local SQL, and handed to the scan as the universe.
  - TECHNICAL ("oversold", "above the 200-day") — the existing
    `parse_strategy_message` rules, run over that narrowed universe.

Resolving the fundamental half FIRST is what makes "small caps that are
oversold" one query instead of two surfaces. The fundamental pass is
deliberately deterministic: this endpoint is public and unauthenticated, and a
second LLM call would double the cost and abuse surface.

Autocomplete reuses the existing `GET /api/symbols/search`. Releases the DB
session before the slow LLM parse (backend trap #13 — don't hold a pooled conn
across a network await); every DB read is materialised into plain values first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import ParseResult, SearchIntent, SearchParseRequest
from app.services.alpha_vantage import AlphaVantageClient
from app.services.screen_filter_parser import extract_filters
from app.services.screener_service import ScreenerService
from app.services.search_dispatch_service import (
    FundamentalNarrowing,
    best_company_match,
    build_company_result,
    build_screen_result,
    classify,
)
from app.services.strategy_parser import parse_strategy_message
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/search", tags=["search"])

# Module-level, mirroring app/api/routes/market_data.py's symbol_service.
_symbol_service = SymbolService(AlphaVantageClient())
_screener = ScreenerService()

# Ceiling on the pre-narrowed universe handed to the technical scan. Generous
# enough that ordinary queries are never cut, low enough that a bare
# "large caps" can't hand thousands of symbols to the scanner. When it bites,
# the result discloses it.
_UNIVERSE_CAP = 1500


@router.post("/parse", response_model=ParseResult)
async def parse_search(
    payload: SearchParseRequest,
    db: Session = Depends(get_db),
) -> ParseResult:
    query = payload.query.strip()
    matches = await _symbol_service.search(db, query)
    intent = classify(query, matches)

    if intent == SearchIntent.COMPANY:
        return build_company_result(query, best_company_match(query, matches))

    # SCREEN. Resolve the FUNDAMENTAL half first (cheap, local SQL) so the
    # technical scan can run over the survivors instead of the whole index —
    # this is what makes "small caps that are oversold" a single query.
    # Deterministic, so no extra LLM call on this public endpoint.
    filters, applied = extract_filters(query)
    fundamental = None
    if filters is not None:
        symbols, total = _screener.matching_symbols(db, filters, cap=_UNIVERSE_CAP)
        fundamental = FundamentalNarrowing(
            symbols=symbols,
            applied=applied,
            total=total,
            truncated_from=total if total > len(symbols) else None,
        )

    # Release the pooled conn before the (slow) LLM parse — trap #13. Every DB
    # read above is already materialised into plain values.
    db.close()
    parsed = await parse_strategy_message(query)
    return build_screen_result(query, parsed, fundamental=fundamental)
