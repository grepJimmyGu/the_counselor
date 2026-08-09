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

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import ParseResult, SearchIntent, SearchParseRequest
from app.services.alpha_vantage import AlphaVantageClient
from app.services.screen_filter_parser import extract_filters, screener_query_params
from app.services.screener_service import ScreenerService
from app.data.standing_universes import standing_universe_ids
from app.services.screen_rule_parser import extract_rules
from app.services.search_dispatch_service import (
    DEFAULT_SCREEN_UNIVERSE,
    FundamentalNarrowing,
    best_company_match,
    build_company_result,
    build_screen_result,
    build_screen_result_from_filters,
    build_screen_result_from_rules,
    classify,
)
from app.services.strategy_parser import parse_strategy_message
from app.services.symbol_service import SymbolService

logger = logging.getLogger("livermore.search")

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
    # Reject an unknown universe rather than silently screening the default —
    # a screen that quietly ran on the wrong universe is worse than an error.
    universe_id = payload.universe_id or DEFAULT_SCREEN_UNIVERSE
    if universe_id not in standing_universe_ids():
        raise HTTPException(
            status_code=422,
            detail=f"Unknown universe '{universe_id}'.",
        )
    # The symbol lookup only DISAMBIGUATES intent — "is this a company name or
    # a screen?" A screen phrase ("RSI below 30") never hits the local symbol
    # cache, so it falls through to Alpha Vantage on every single query; an AV
    # outage, a rate limit, or a missing key then 500s the entire search box
    # rather than the one thing that needed it.
    #
    # Degrading to "no company matched" is the honest reading of a failed
    # lookup, and it's also the correct one for a screen: `classify` treats an
    # empty match list as "not a company", which is what a phrase like this is.
    # A ticker query still resolves, because those DO hit the local cache.
    try:
        matches = await _symbol_service.search(db, query)
    except Exception:
        logger.warning("symbol lookup failed for %r; classifying without it", query)
        matches = []
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
            screener_params=screener_query_params(filters),
        )

    # TECHNICAL half. Try the deterministic extractor FIRST: the LLM strategy
    # parser is built to produce a complete backtestable strategy, so it asks
    # for a universe / lookback / thresholds and returns NO rules instead of
    # extracting the conditions it was given — measured in production on
    # "oversold above 200 day MA". A screen needs none of those fields.
    rules, readings = extract_rules(query)
    if rules:
        return build_screen_result_from_rules(
            query, rules, readings, fundamental, universe_id=universe_id
        )

    # Fundamental-only query ("p/e under 15", "dividend yield above 4%"): the
    # filters ARE the whole screen. Without this the request fell through to
    # the LLM below, which asked "Which strategy type should I use?" and
    # discarded the symbols we just matched.
    if fundamental is not None:
        return build_screen_result_from_filters(query, fundamental)

    # Nothing recognised — fall back to the LLM parser, which still handles
    # phrasings the vocabulary doesn't cover. Release the pooled conn first
    # (trap #13); every DB read above is already materialised.
    db.close()
    parsed = await parse_strategy_message(query)
    return build_screen_result(
        query, parsed, fundamental=fundamental, universe_id=universe_id
    )
