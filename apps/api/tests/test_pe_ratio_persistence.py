"""A cached P/E must survive a profile refresh.

The regression: `FundamentalService._upsert_symbol` copied `profile.pe_ratio`
onto the row unconditionally, and FMP's *profile* has no P/E at all —
`fmp_adapter` hardcodes `pe_ratio=None` because the value lives in key-metrics.
So every profile refresh nulled the column. `get_summary` merged a real P/E
back in whenever someone opened a company page, and the next refresh wiped it
again. That write-then-clobber loop is why `max_pe=60` matched 0 of 16,832
symbols in production.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.symbol import SymbolCache
from app.schemas.fundamental import CompanyProfile
from app.services.fundamental_service import FundamentalService


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _profile(**over) -> CompanyProfile:
    base = dict(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        market_cap=3_000_000_000_000.0,
        pe_ratio=None,  # what the FMP profile adapter always sends
        dividend_yield=0.0042,
        data_source="fmp",
        as_of_date=date.today(),
    )
    base.update(over)
    return CompanyProfile(**base)


def test_profile_refresh_does_not_null_an_existing_pe(db) -> None:
    svc = FundamentalService()
    db.add(SymbolCache(symbol="AAPL", name="Apple Inc.", pe_ratio=31.4))
    db.commit()

    # A profile refresh — carrying no P/E, as every FMP profile does.
    svc._upsert_symbol(db, _profile())

    assert db.get(SymbolCache, "AAPL").pe_ratio == 31.4


def test_a_real_pe_on_the_profile_still_writes_through(db) -> None:
    """Guarding the null must not block a genuine update (e.g. the yfinance
    adapter, which does populate P/E)."""
    svc = FundamentalService()
    db.add(SymbolCache(symbol="AAPL", name="Apple Inc.", pe_ratio=31.4))
    db.commit()

    svc._upsert_symbol(db, _profile(pe_ratio=28.9))

    assert db.get(SymbolCache, "AAPL").pe_ratio == 28.9


def test_dividend_yield_is_written_as_the_fraction_it_arrives_as(db) -> None:
    svc = FundamentalService()
    svc._upsert_symbol(db, _profile())
    assert db.get(SymbolCache, "AAPL").dividend_yield == 0.0042
