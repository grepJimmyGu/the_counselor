"""`POST /api/search/parse` must survive a failed symbol lookup.

SYMPTOM: every screen query 500s with `AlphaVantageError: ALPHA_VANTAGE_API_KEY
is not configured`. The search box — the product's main entry point — is
completely down. Found 2026-08-09 while bringing the API up locally, but the
same trace fires on any AV outage or rate limit, not just a missing key.

ROOT CAUSE: `parse_search` calls `_symbol_service.search(db, query)` to decide
COMPANY vs SCREEN. That helper checks the local `symbols` cache first and only
calls Alpha Vantage on a miss — and a screen PHRASE ("RSI below 30") never
matches a ticker or a company name, so the cache misses on literally every
screen query and the AV call runs every time. Any failure there propagated out
of the route.

FIX: catch it and classify with an empty match list. That's the honest reading
of a failed lookup and the correct one for a screen — `classify` treats "no
company matched" as "not a company", which a screen phrase isn't. Ticker
queries are unaffected: those hit the local cache and never reach AV.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import search as search_route
from app.db.migrations import run_startup_migrations
from app.db.session import Base, get_db
from app.main import app
from app.services.alpha_vantage import AlphaVantageError


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    run_startup_migrations(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture
def failing_symbol_lookup(monkeypatch):
    async def _boom(_db, _query):
        raise AlphaVantageError("ALPHA_VANTAGE_API_KEY is not configured.")

    monkeypatch.setattr(search_route._symbol_service, "search", _boom)


def test_screen_query_still_parses_when_symbol_lookup_fails(client, failing_symbol_lookup):
    r = client.post(
        "/api/search/parse", json={"query": "RSI below 30", "universe_id": "sp500"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "screen"
    # And it produced a REAL screen, not an empty shell — the deterministic
    # rule extractor never needed the symbol lookup in the first place.
    assert body["screen"]["rules"][0]["primitive_id"] == "rsi"


def test_the_failure_is_not_swallowed_into_a_wrong_intent(client, failing_symbol_lookup):
    """A failed lookup must not turn a company query into a phantom company.

    Degrading to "no matches" is only safe because `classify` reads that as
    "not a company". If it ever guessed one from the raw query text, an AV
    outage would silently route users to the wrong stock.
    """
    r = client.post("/api/search/parse", json={"query": "Apple", "universe_id": "sp500"})
    assert r.status_code == 200
    assert r.json()["intent"] != "company"
