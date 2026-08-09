"""Fundamentals for an explicit symbol list.

`screen()` answers "which names match these filters". The results page needs
the other question — "what are the numbers for THESE names" — because its
symbol list comes from a technical scan, so there are no filters to re-run.
Re-deriving them could also return a *different* set than the one on screen,
which is the failure this endpoint exists to avoid.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.migrations import run_startup_migrations
from app.db.session import Base, get_db
from app.models.symbol import SymbolCache


@pytest.fixture()
def client():
    # Self-contained engine on StaticPool so the seed session and the route's
    # get_db session share one in-memory DB — the pattern from
    # test_screen_endpoints.py. The shared `db` fixture isn't enough here
    # because TestClient runs the app lifespan against its own engine.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    run_startup_migrations(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    db = SessionLocal()
    db.add_all(
        [
            SymbolCache(symbol="AAPL", name="Apple Inc.", pe_ratio=35.6,
                        dividend_yield=0.0034, beta=1.2, market_cap=4.6e12, is_active=True),
            SymbolCache(symbol="MSFT", name="Microsoft", pe_ratio=27.76,
                        dividend_yield=0.0071, beta=0.9, market_cap=3.8e12, is_active=True),
            SymbolCache(symbol="JPM", name="JPMorgan", pe_ratio=15.27,
                        dividend_yield=0.0168, beta=1.1, market_cap=8.0e11, is_active=True),
        ]
    )
    db.commit()
    db.close()
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_returns_fundamentals_for_the_given_names(client) -> None:
    r = client.get("/api/screener/by-symbols?symbols=AAPL,JPM")
    assert r.status_code == 200
    body = r.json()
    assert [x["symbol"] for x in body["results"]] == ["AAPL", "JPM"]
    assert body["results"][0]["pe_ratio"] == 35.6
    assert body["results"][1]["dividend_yield"] == 0.0168


def test_order_follows_the_caller_not_the_database(client) -> None:
    """The table may be ranked by something the DB knows nothing about — a
    technical value, or a live price. Reordering here would silently undo
    whatever sort the user applied."""
    r = client.get("/api/screener/by-symbols?symbols=JPM,AAPL,MSFT")
    assert [x["symbol"] for x in r.json()["results"]] == ["JPM", "AAPL", "MSFT"]


def test_an_unknown_ticker_is_omitted_not_a_blank_row(client) -> None:
    r = client.get("/api/screener/by-symbols?symbols=AAPL,NOSUCHTICKER")
    body = r.json()
    assert [x["symbol"] for x in body["results"]] == ["AAPL"]
    assert body["total"] == 1


def test_case_and_whitespace_are_tolerated(client) -> None:
    r = client.get("/api/screener/by-symbols?symbols=  aapl , msft ")
    assert [x["symbol"] for x in r.json()["results"]] == ["AAPL", "MSFT"]


def test_empty_list_is_empty_not_the_whole_universe(client) -> None:
    """The dangerous default: an empty filter set in `screen()` returns
    everything. Here it must return nothing."""
    r = client.get("/api/screener/by-symbols?symbols=")
    assert r.json()["results"] == []


def test_the_list_is_capped(client) -> None:
    many = ",".join(f"S{i}" for i in range(500)) + ",AAPL"
    r = client.get(f"/api/screener/by-symbols?symbols={many}")
    # AAPL sits past the cap, so it must NOT come back — proving the cap is
    # applied to the request rather than to the response.
    assert r.status_code == 200
    assert [x["symbol"] for x in r.json()["results"]] == []
