from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.symbol import SymbolCache
from app.schemas.market_data import SymbolDetailResponse, SymbolSearchItem
from app.services.alpha_vantage import AlphaVantageClient


class SymbolService:
    def __init__(self, client: AlphaVantageClient) -> None:
        self.client = client

    async def search(self, db: Session, query: str) -> list[SymbolSearchItem]:
        query_upper = query.upper()
        local = db.execute(
            select(SymbolCache)
            .where(
                or_(
                    SymbolCache.symbol.ilike(f"{query_upper}%"),
                    SymbolCache.name.ilike(f"%{query}%"),
                )
            )
            .limit(10)
        ).scalars().all()

        if local:
            return [_to_search_item(row) for row in local]

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
