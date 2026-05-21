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

from app.services.live_quote_service import live_quote_service

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
    fetched_at: float


class LiveQuotesResponse(BaseModel):
    quotes: dict[str, LiveQuoteOut]


@router.get("/quotes", response_model=LiveQuotesResponse)
async def get_live_quotes(
    symbols: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT"),
) -> LiveQuotesResponse:
    """Batch live quotes for the listed symbols. Cached up to TTL_SECONDS."""
    parsed = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    parsed = parsed[:_MAX_SYMBOLS_PER_REQUEST]

    quotes = await live_quote_service.get_quotes(parsed)
    return LiveQuotesResponse(
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
            )
            for sym, q in quotes.items()
        }
    )
