from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.symbol import SymbolCache
from app.schemas.market_data import SymbolDetailResponse, SymbolSearchItem
from app.services.alpha_vantage import AlphaVantageClient


class SymbolService:
    def __init__(self, client: AlphaVantageClient) -> None:
        self.client = client

    # How many rows the search returns, and how many it reads per kind of
    # match before ranking them.
    _LIMIT = 10

    async def search(self, db: Session, query: str) -> list[SymbolSearchItem]:
        """Symbols for a search box, best match first.

        Ranked in four tiers, each read with its own small query so a broad
        tier cannot crowd out a better one:

          1. the ticker itself ("ANT" → ANT);
          2. tickers that start with the query, shortest first (ANTE, ANTX);
          3. companies whose name has a word starting with it ("Anthropic");
          4. any other company whose name contains it.

        Until 2026-11-23 this was one unordered query capped at 10 rows that
        also matched the query anywhere inside a name, so "ANT" returned ten
        warrants ("Warr*ant*s") and never ANT itself.
        """
        text = query.strip()
        if not text:
            return []
        ticker = text.upper()
        limit = self._LIMIT

        exact = db.get(SymbolCache, ticker)
        by_prefix = db.execute(
            select(SymbolCache)
            .where(SymbolCache.symbol.ilike(f"{ticker}%"), SymbolCache.symbol != ticker)
            .order_by(func.length(SymbolCache.symbol), SymbolCache.symbol)
            .limit(limit)
        ).scalars().all()
        by_word = db.execute(
            select(SymbolCache)
            .where(or_(SymbolCache.name.ilike(f"{text}%"), SymbolCache.name.ilike(f"% {text}%")))
            .order_by(func.length(SymbolCache.name), SymbolCache.symbol)
            .limit(limit)
        ).scalars().all()
        by_part = db.execute(
            select(SymbolCache)
            .where(SymbolCache.name.ilike(f"%{text}%"))
            .order_by(func.length(SymbolCache.name), SymbolCache.symbol)
            .limit(limit)
        ).scalars().all()

        ranked: list[SymbolCache] = []
        seen: set[str] = set()
        for row in ([exact] if exact else []) + list(by_prefix) + list(by_word) + list(by_part):
            if row.symbol in seen:
                continue
            seen.add(row.symbol)
            ranked.append(row)
            if len(ranked) == limit:
                break

        if ranked:
            return [_to_search_item(row) for row in ranked]

        remote = await self.client.search_symbols(query)
        for match in remote:
            self._upsert(db, match)
        db.commit()
        return [SymbolSearchItem(**m) for m in remote]

    def get_by_symbol(self, db: Session, symbol: str) -> Optional[SymbolCache]:
        return db.get(SymbolCache, symbol.upper())

    def get_detail(self, db: Session, symbol: str) -> Optional[SymbolDetailResponse]:
        row = self.get_by_symbol(db, symbol)
        if row is None:
            return None
        return SymbolDetailResponse(
            symbol=row.symbol,
            name=row.name,
            region=row.region,
            currency=row.currency,
            instrument_type=row.instrument_type,
            exchange=row.exchange,
            timezone=row.timezone,
            alpha_vantage_match_score=row.alpha_vantage_match_score,
            is_active=bool(row.is_active) if row.is_active is not None else True,
            last_seen_at=row.last_seen_at,
            last_validated_at=row.last_validated_at,
        )

    def _upsert(self, db: Session, data: dict) -> SymbolCache:
        now = datetime.utcnow()
        existing = db.get(SymbolCache, data["symbol"])
        if existing:
            for field in ("name", "region", "currency", "instrument_type",
                          "exchange", "timezone", "alpha_vantage_match_score"):
                if data.get(field) is not None:
                    setattr(existing, field, data[field])
            existing.last_seen_at = now
            existing.updated_at = now
            return existing
        row = SymbolCache(
            symbol=data["symbol"],
            name=data.get("name", ""),
            region=data.get("region"),
            currency=data.get("currency"),
            instrument_type=data.get("instrument_type"),
            exchange=data.get("exchange"),
            timezone=data.get("timezone"),
            alpha_vantage_match_score=data.get("alpha_vantage_match_score"),
            is_active=True,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        return row


def _to_search_item(row: SymbolCache) -> SymbolSearchItem:
    return SymbolSearchItem(
        symbol=row.symbol,
        name=row.name,
        region=row.region,
        currency=row.currency,
        instrument_type=row.instrument_type,
        exchange=row.exchange,
        timezone=row.timezone,
        alpha_vantage_match_score=row.alpha_vantage_match_score,
    )
