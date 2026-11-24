"""Live stock quote endpoint.

Single batch endpoint backing the frontend `useLiveQuotes` hook. Reads from
the in-process `live_quote_service` cache; only triggers an FMP fetch on
miss or stale.

GET /api/live/quotes?symbols=AAPL,MSFT,NVDA
  → { "quotes": { "AAPL": {...}, "MSFT": {...}, "NVDA": {...} } }

Symbols absent from the result mean FMP didn't return them (bad ticker,
data outage). Caller treats them as "no data right now."

No auth required — public market data. Rate-limited only by the cache:
the FMP call rate is bounded by TTL × unique-symbol churn, not request
volume.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.live_quote_service import (
    MIN_MAX_AGE_SECONDS,
    TTL_SECONDS,
    live_quote_service,
)

router = APIRouter(prefix="/api/live", tags=["live-quotes"])

# Sanity cap so a malformed query can't trigger a 500-ticker batch.
_MAX_SYMBOLS_PER_REQUEST = 100


class LiveQuoteOut(BaseModel):
    symbol: str
    price: float
    change: float
    change_percent: float
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    name: Optional[str] = None
    exchange: Optional[str] = None
    # A monotonic cache clock, not a time of day — kept because existing
    # clients read it. Use `checked_at` / `as_of` for anything a person sees.
    fetched_at: float
    # Epoch seconds. `checked_at`: when the server fetched this quote.
    # `as_of`: when the quote itself is from (the last trade), if known.
    checked_at: Optional[float] = None
    as_of: Optional[float] = None
    source: Optional[str] = None


class LiveQuotesResponse(BaseModel):
    quotes: dict[str, LiveQuoteOut]
    # How old a quote in this response can be. Polling faster than this
    # returns the same cached values, so it is also the right poll interval.
    ttl_seconds: float = TTL_SECONDS


@router.get("/quotes", response_model=LiveQuotesResponse)
async def get_live_quotes(
    symbols: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT"),
) -> LiveQuotesResponse:
    """Batch live quotes for the listed symbols. Cached up to TTL_SECONDS."""
    parsed = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    parsed = parsed[:_MAX_SYMBOLS_PER_REQUEST]

    ttl = min(TTL_SECONDS, max(MIN_MAX_AGE_SECONDS, get_settings().live_quote_ttl_seconds))
    quotes = await live_quote_service.get_quotes(parsed, max_age=ttl)
    return LiveQuotesResponse(
        ttl_seconds=ttl,
        quotes={
            sym: LiveQuoteOut(
                symbol=q.symbol,
                price=q.price,
                change=q.change,
                change_percent=q.change_percent,
                day_high=q.day_high,
                day_low=q.day_low,
                volume=q.volume,
                market_cap=q.market_cap,
                name=q.name,
                exchange=q.exchange,
                fetched_at=q.fetched_at,
                checked_at=q.checked_at,
                as_of=q.as_of,
                source=q.source,
            )
            for sym, q in quotes.items()
        }
    )
