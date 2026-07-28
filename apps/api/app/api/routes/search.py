"""Unified smart-search dispatcher (PRD-27).

POST /api/search/parse — one box → COMPANY (symbol_service) | SCREEN
(parse_strategy_message → technical rules over a standing universe) | AMBIGUOUS.

Autocomplete reuses the existing `GET /api/symbols/search`. Public (an
entry-mode surface reachable before sign-in); releases the DB session before
the slow LLM parse (backend trap #13 — don't hold a pooled conn across a
network await).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import ParseResult, SearchIntent, SearchParseRequest
from app.services.alpha_vantage import AlphaVantageClient
from app.services.search_dispatch_service import (
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

    # SCREEN — release the pooled DB conn before the (slow) LLM parse (trap #13).
    db.close()
    parsed = await parse_strategy_message(query)
    return build_screen_result(query, parsed)
