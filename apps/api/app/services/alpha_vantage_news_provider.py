from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx

from app.core.config import get_settings
from app.schemas.sentiment import NewsArticle, ProviderStatus


class AlphaVantageNewsProvider:
    name = "alpha_vantage"
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self) -> None:
        self._settings = get_settings()

    def status(self) -> ProviderStatus:
        return ProviderStatus.active if self._settings.alpha_vantage_api_key else ProviderStatus.not_configured

    async def fetch(self, symbol: str, limit: int = 20) -> list[NewsArticle]:
        if not self._settings.alpha_vantage_api_key:
            return []

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol.upper(),
            "limit": min(limit, 50),
            "sort": "LATEST",
            "apikey": self._settings.alpha_vantage_api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self._settings.api_timeout_seconds) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return []

        articles = []
        for item in data.get("feed", [])[:limit]:
            # Find ticker-specific sentiment
            ticker_sentiment: dict = {}
            for ts in item.get("ticker_sentiment", []):
                if ts.get("ticker", "").upper() == symbol.upper():
                    ticker_sentiment = ts
                    break

            published_at: Optional[datetime] = None
            try:
                raw_time = item.get("time_published", "")
                if raw_time:
                    published_at = datetime.strptime(raw_time[:15], "%Y%m%dT%H%M%S")
            except (ValueError, TypeError):
                pass

            relevance = None
            try:
                relevance = float(ticker_sentiment.get("relevance_score", 0))
            except (ValueError, TypeError):
                pass

            sent_score = None
            try:
                sent_score = float(
                    ticker_sentiment.get("ticker_sentiment_score")
                    or item.get("overall_sentiment_score", 0)
                )
            except (ValueError, TypeError):
                pass

            topics = [t.get("topic", "") for t in item.get("topics", []) if t.get("topic")]

            articles.append(NewsArticle(
                provider="alpha_vantage",
                symbol=symbol.upper(),
                title=item.get("title", ""),
                summary=item.get("summary"),
                source_name=item.get("source"),
                url=item.get("url"),
                published_at=published_at,
                topics=topics,
                sentiment_score=sent_score,
                sentiment_label=(
                    ticker_sentiment.get("ticker_sentiment_label")
                    or item.get("overall_sentiment_label")
                ),
                relevance_score=relevance,
            ))

        return articles
