from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.schemas.market_data import WarmupResponse
from app.services.price_data_service import PriceDataService


class DataQualityService:
    def __init__(self) -> None:
        self.price_data = PriceDataService()

    async def warmup(
        self,
        db: Session,
        symbols: list[str],
        lookback_days: int = 252,
    ) -> WarmupResponse:
        queued: list[str] = []
        already_fresh: list[str] = []
        errors: dict[str, str] = {}

        required_from = date.today() - timedelta(days=lookback_days + 10)

        for sym in symbols:
            try:
                cache = self.price_data.cache_svc
                latest = cache.get_latest_date(db, sym)
                earliest = cache.get_earliest_date(db, sym)
                not_stale = not cache.is_stale(latest, date.today())
                has_lookback = earliest is not None and earliest <= required_from

                if not_stale and has_lookback:
                    already_fresh.append(sym)
                else:
                    await cache.ensure_history(db, sym, required_from)
                    queued.append(sym)
            except Exception as exc:
                errors[sym] = str(exc)

        return WarmupResponse(queued=queued, already_fresh=already_fresh, errors=errors)
