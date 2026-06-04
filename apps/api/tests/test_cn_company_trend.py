"""Regression test for GET /api/cn/company/{symbol}/trend.

**2026-06-04 production bug.** `CompanyTrendService.get_trend()` stores
`latest_date` as a `datetime.date` on its `TrendData` dataclass. The
response schema `TrendSection.latest_date` is `Optional[str]`. The CN
handler `return td` leaned on FastAPI's response_model coercion, which
under Pydantic v2's strict response validation rejects `date` against
a `str` field — every A-share trend call 500'd with
`ResponseValidationError: Input should be a valid string`.

**Fix.** `cn_company_trend` now constructs `TrendSection` explicitly
with `latest_date=td.latest_date.isoformat()`, mirroring the US handler
in `apps/api/app/api/routes/company_overview.py:69`. This pins the
post-fix invariant so the regression can't silently come back.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.api.routes.cn_company import cn_company_trend
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


def test_cn_trend_returns_string_latest_date(db) -> None:
    """`.SZ` A-share trend response must carry `latest_date` as an ISO
    string, not a `datetime.date`. Pre-fix this was the dataclass field
    type and FastAPI's response validation 500'd the request."""
    _seed_bars(db, "300747.SZ", count=30)

    result = cn_company_trend(symbol="300747.SZ", db=db)

    assert isinstance(result, TrendSection)
    assert isinstance(result.latest_date, str), (
        f"latest_date must be a string for the Optional[str] response "
        f"field; got {type(result.latest_date).__name__}"
    )
    assert _ISO_DATE.match(result.latest_date), (
        f"latest_date must be ISO YYYY-MM-DD; got {result.latest_date!r}"
    )


def test_cn_trend_handles_ss_suffix(db) -> None:
    """`.SS` (Shanghai) symbols must follow the same response contract
    — both A-share suffixes hit the same handler."""
    _seed_bars(db, "688200.SS", count=30)

    result = cn_company_trend(symbol="688200.SS", db=db)

    assert isinstance(result, TrendSection)
    assert isinstance(result.latest_date, str)
    assert _ISO_DATE.match(result.latest_date)
