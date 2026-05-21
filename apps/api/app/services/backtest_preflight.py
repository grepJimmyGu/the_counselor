"""Shared pre-flight helpers for backtest routes.

Both the authenticated `/api/backtest/run` and the anonymous one-shot
`/api/anonymous/backtest/run` need to:
  1. Validate that every universe symbol is known.
  2. Auto-fetch any uncached symbols' price history before the engine runs.

Previously these helpers lived as private functions inside
`apps/api/app/api/routes/backtest.py`, which meant the anonymous endpoint
silently skipped both checks and produced cryptic engine errors for any
strategy whose universe wasn't already cached (sector rotation across 11
SPDR ETFs was the trigger that surfaced the bug on 2026-05-22).

Singletons live here so both routes share one set of HTTP clients.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.services.alpha_vantage import AlphaVantageClient
from app.services.price_cache_service import PriceCacheService
from app.services.symbol_service import SymbolService

_symbol_service = SymbolService(AlphaVantageClient())
_cache_svc = PriceCacheService(AlphaVantageClient())


async def validate_universe(db: Session, symbols: list[str]) -> list[str]:
    """Return the subset of *symbols* that are not known to the symbol service.

    A symbol is considered valid if either the local symbols cache has it OR
    an Alpha Vantage search returns an exact match.
    """
    invalid: list[str] = []
    for symbol in symbols:
        cached = _symbol_service.get_by_symbol(db, symbol)
        if cached:
            continue
        results = await _symbol_service.search(db, symbol)
        exact = next((r for r in results if r.symbol == symbol), None)
        if not exact:
            invalid.append(symbol)
    return invalid


async def ensure_data_available(
    db: Session,
    symbols: list[str],
    required_from: date,
) -> dict[str, str]:
    """For any symbol with no cached price bars, attempt a fetch.

    Returns a dict of symbol → error message for symbols whose fetch failed.
    Empty dict on success.
    """
    fetch_errors: dict[str, str] = {}
    for symbol in symbols:
        if _cache_svc.get_bar_count(db, symbol) == 0:
            try:
                await _cache_svc.ensure_history(db, symbol, required_from)
            except Exception as exc:
                fetch_errors[symbol] = str(exc)
    return fetch_errors
