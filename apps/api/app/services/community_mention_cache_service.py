from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.sentiment import CommunityMention
from app.services.internal_community_provider import InternalCommunityProvider
from app.services.reddit_community_provider import RedditCommunityProvider
from app.services.x_community_provider import XCommunityProvider

_CACHE_TTL_MINUTES = 15


class CommunityMentionCacheService:
    def __init__(self) -> None:
        self._providers = [
            RedditCommunityProvider(),
            XCommunityProvider(),
            InternalCommunityProvider(),
        ]

    async def get_mentions(
        self, symbol: str, db: Session, limit: int = 30
    ) -> list[CommunityMention]:
        cutoff = datetime.utcnow() - timedelta(minutes=_CACHE_TTL_MINUTES)
        rows = db.execute(
            text(
                "SELECT provider, platform, symbol, title, text, author, community_name,"
                " url, published_at, upvotes, comments, sentiment_score, sentiment_label"
                " FROM community_mentions WHERE symbol = :sym AND created_at > :cutoff"
                " ORDER BY published_at DESC LIMIT :lim"
            ),
            {"sym": symbol.upper(), "cutoff": cutoff, "lim": limit},
        ).fetchall()

        if rows:
            return [_row_to_mention(r) for r in rows]

        mentions: list[CommunityMention] = []
        for provider in self._providers:
            try:
                fetched = await provider.fetch(symbol, limit=limit)
                mentions.extend(fetched)
            except Exception:
                pass

        _upsert_mentions(mentions, db)
        return mentions[:limit]


def _row_to_mention(row: object) -> CommunityMention:
    r = row._mapping  # type: ignore[attr-defined]
    published_at = r["published_at"]
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at)
        except Exception:
            published_at = None
    return CommunityMention(
        provider=r["provider"],
        platform=r["platform"],
        symbol=r["symbol"],
        title=r.get("title"),
        text=r.get("text") or "",
        author=r.get("author"),
        community_name=r.get("community_name"),
        url=r.get("url"),
        published_at=published_at,
        upvotes=r.get("upvotes"),
        comments=r.get("comments"),
        sentiment_score=r.get("sentiment_score"),
        sentiment_label=r.get("sentiment_label"),
    )


def _upsert_mentions(mentions: list[CommunityMention], db: Session) -> None:
    for m in mentions:
        url_key = m.url or f"{m.provider}::{m.platform}::{(m.text or '')[:80]}"
        try:
            db.execute(
                text(
                    "INSERT INTO community_mentions"
                    " (provider, platform, symbol, title, text, author, community_name,"
                    "  url, published_at, upvotes, comments,"
                    "  sentiment_score, sentiment_label)"
                    " VALUES (:provider, :platform, :symbol, :title, :text, :author,"
                    "  :community_name, :url, :published_at, :upvotes, :comments,"
                    "  :sentiment_score, :sentiment_label)"
                    " ON CONFLICT (provider, url) DO NOTHING"
                ),
                {
                    "provider": m.provider,
                    "platform": m.platform,
                    "symbol": m.symbol.upper(),
                    "title": m.title,
                    "text": m.text,
                    "author": m.author,
                    "community_name": m.community_name,
                    "url": url_key,
                    "published_at": m.published_at,
                    "upvotes": m.upvotes,
                    "comments": m.comments,
                    "sentiment_score": m.sentiment_score,
                    "sentiment_label": m.sentiment_label,
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
