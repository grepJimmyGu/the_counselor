from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.sentiment import NewsArticle
from app.services.alpha_vantage_news_provider import AlphaVantageNewsProvider

_CACHE_TTL_MINUTES = 15


class NewsArticleCacheService:
    def __init__(self) -> None:
        self._providers = [AlphaVantageNewsProvider()]

    async def get_articles(
        self, symbol: str, db: Session, limit: int = 20
    ) -> list[NewsArticle]:
        cutoff = datetime.utcnow() - timedelta(minutes=_CACHE_TTL_MINUTES)
        rows = db.execute(
            text(
                "SELECT provider, symbol, title, summary, source_name, url, published_at,"
                " topics, ticker_sentiment_score, ticker_sentiment_label, relevance_score"
                " FROM news_articles WHERE symbol = :sym AND created_at > :cutoff"
                " ORDER BY published_at DESC LIMIT :lim"
            ),
            {"sym": symbol.upper(), "cutoff": cutoff, "lim": limit},
        ).fetchall()

        if rows:
            return [_row_to_article(r) for r in rows]

        articles: list[NewsArticle] = []
        for provider in self._providers:
            try:
                fetched = await provider.fetch(symbol, limit=limit)
                articles.extend(fetched)
            except Exception:
                pass

        _upsert_articles(articles, db)
        return articles[:limit]


def _row_to_article(row: object) -> NewsArticle:
    r = row._mapping  # type: ignore[attr-defined]
    topics = r["topics"]
    if isinstance(topics, str):
        try:
            topics = json.loads(topics)
        except Exception:
            topics = []
    published_at = r["published_at"]
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at)
        except Exception:
            published_at = None
    return NewsArticle(
        provider=r["provider"],
        symbol=r["symbol"],
        title=r["title"],
        summary=r.get("summary"),
        source_name=r.get("source_name"),
        url=r.get("url"),
        published_at=published_at,
        topics=topics or [],
        sentiment_score=r.get("ticker_sentiment_score"),
        sentiment_label=r.get("ticker_sentiment_label"),
        relevance_score=r.get("relevance_score"),
    )


def _upsert_articles(articles: list[NewsArticle], db: Session) -> None:
    for a in articles:
        url_key = a.url or f"{a.provider}::{a.title[:80]}"
        try:
            db.execute(
                text(
                    "INSERT INTO news_articles"
                    " (provider, symbol, title, summary, source_name, url, published_at,"
                    "  topics, ticker_sentiment_score, ticker_sentiment_label, relevance_score)"
                    " VALUES (:provider, :symbol, :title, :summary, :source_name, :url,"
                    "  :published_at, :topics, :sentiment_score, :sentiment_label, :relevance)"
                    " ON CONFLICT (provider, url) DO NOTHING"
                ),
                {
                    "provider": a.provider,
                    "symbol": a.symbol.upper(),
                    "title": a.title,
                    "summary": a.summary,
                    "source_name": a.source_name,
                    "url": url_key,
                    "published_at": a.published_at,
                    "topics": json.dumps(a.topics),
                    "sentiment_score": a.sentiment_score,
                    "sentiment_label": a.sentiment_label,
                    "relevance": a.relevance_score,
                },
            )
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    try:
        db.commit()
    except Exception:
        db.rollback()
