"""Market-wide news feed (home block 4's ticker).

Every other news surface is per-symbol (`/api/sentiment/{symbol}/news`). This
is the whole market in one call — AV's `NEWS_SENTIMENT` accepts `topics` as
well as `tickers`, which is what makes an always-on ticker affordable: one
upstream request for every visitor, not one per symbol.

Cached in-process for 15 minutes. The endpoint is anonymous and sits on the
home page, so without a cache each page load would be an upstream call and the
AV quota would be gone by lunchtime. 15 minutes is well inside how fast this
feed actually moves, and the response carries `as_of` so the UI can say when it
last refreshed rather than implying live.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.schemas.sentiment import NewsArticle
from app.services.alpha_vantage_news_provider import fetch_market_news

router = APIRouter(prefix="/api/news", tags=["news"])

_CACHE_TTL_SECONDS = 15 * 60
# (fetched_at_monotonic, articles). Module-level and deliberately not an
# asyncio primitive — a plain tuple can't bind to an event loop, so this is
# safe to touch from a warmup thread as well as a request (backend trap #22).
_cache: Optional[Tuple[float, List[NewsArticle]]] = None


class MarketNewsResponse(BaseModel):
    articles: List[NewsArticle]
    #: Seconds since the upstream fetch. The UI shows freshness rather than
    #: pretending the feed is live.
    age_seconds: int
    cached: bool


@router.get("/market", response_model=MarketNewsResponse)
async def get_market_news(
    limit: int = Query(20, ge=1, le=50),
) -> MarketNewsResponse:
    global _cache

    now = time.monotonic()
    if _cache is not None and (now - _cache[0]) < _CACHE_TTL_SECONDS:
        fetched_at, articles = _cache
        return MarketNewsResponse(
            articles=articles[:limit],
            age_seconds=int(now - fetched_at),
            cached=True,
        )

    articles = await fetch_market_news(limit=50)
    if not articles:
        # Serve stale rather than empty — a ticker that blanks on one failed
        # upstream call is worse than one showing 20-minute-old headlines.
        if _cache is not None:
            fetched_at, cached_articles = _cache
            return MarketNewsResponse(
                articles=cached_articles[:limit],
                age_seconds=int(now - fetched_at),
                cached=True,
            )
        return MarketNewsResponse(articles=[], age_seconds=0, cached=False)

    _cache = (now, articles)
    return MarketNewsResponse(articles=articles[:limit], age_seconds=0, cached=False)
