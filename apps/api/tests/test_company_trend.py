"""Regression bar for GET /api/company/{symbol}/trend.

Pairs with `test_cn_company_trend.py`. Both endpoints must return
`latest_date` as an ISO string — the US handler has always converted
explicitly via `latest_date.isoformat()` (`company_overview.py:71`),
so this test is a regression bar to catch schema/handler drift that
would silently break the US side the same way the CN side broke on
2026-06-04.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.api.routes.company_overview import get_company_trend
from app.models.price_bar import PriceBar
from app.schemas.company_overview import TrendSection


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _seed_bars(db, symbol: str, count: int = 30) -> None:
    today = date.today()
    for i in range(count):
        d = today - timedelta(days=count - i)
        db.add(PriceBar(
            symbol=symbol,
            trading_date=d,
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.0 + i,
            adjusted_close=100.0 + i,
            volume=1_000_000,
            dividend_amount=0.0,
            split_coefficient=1.0,
            source="test",
            fetched_at=datetime.utcnow(),
        ))
    db.commit()


def test_us_trend_returns_string_latest_date(db) -> None:
    """US trend response must carry `latest_date` as an ISO string —
    same contract as the CN endpoint, enforced here as a regression bar."""
    _seed_bars(db, "AAPL", count=30)

    result = get_company_trend(symbol="AAPL", _gate=None, db=db)

    assert isinstance(result, TrendSection)
    assert isinstance(result.latest_date, str), (
        f"latest_date must be a string for the Optional[str] response "
        f"field; got {type(result.latest_date).__name__}"
    )
    assert _ISO_DATE.match(result.latest_date), (
        f"latest_date must be ISO YYYY-MM-DD; got {result.latest_date!r}"
    )
