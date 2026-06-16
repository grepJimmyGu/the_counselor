"""PRD-23a slice 4 — /api/screen/scan + /count endpoints.

Wires scan_service behind two POST routes. Uses a shared in-memory engine
(StaticPool) so the seed session and the route's get_db session hit the same
DB, and overrides get_db to that engine.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.migrations import run_startup_migrations
from app.db.session import Base, get_db
from app.main import app
from app.services.screener.signal_snapshot_service import SignalSnapshotService

AS_OF = date(2026, 6, 15)


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

    seed = SessionLocal()
    svc = SignalSnapshotService()
    svc.write_symbol(seed, "AAPL", {"rsi": 25.0, "sma": 150.0}, AS_OF)
    svc.write_symbol(seed, "MSFT", {"rsi": 55.0, "sma": 200.0}, AS_OF)
    svc.write_symbol(seed, "TSLA", {"rsi": 20.0}, AS_OF)
    seed.commit()
    seed.close()

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


def _body(rsi_lt=30):
    return {
        "universe_id": "symbols",
        "symbols": ["AAPL", "MSFT", "TSLA"],
        "rules": [{"primitive_id": "rsi", "operator": "lt", "threshold": rsi_lt}],
    }


def test_scan_returns_matched_basket(client):
    r = client.post("/api/screen/scan", json=_body())
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data["matched"]) == {"AAPL", "TSLA"}
    assert data["matched_count"] == 2
    assert data["universe_size"] == 3
    assert data["as_of_date"] == "2026-06-15"
    assert data["readings"]["AAPL"]  # why-it-matched copy present


def test_scan_allows_anonymous(client):
    # No Authorization header — explorable pre-sign-in (not 401).
    r = client.post("/api/screen/scan", json=_body())
    assert r.status_code == 200


def test_count_matches_scan_length(client):
    body = _body()
    scan_r = client.post("/api/screen/scan", json=body).json()
    count_r = client.post("/api/screen/count", json=body).json()
    assert count_r["matched_count"] == len(scan_r["matched"])
    assert count_r["universe_size"] == 3
    # /count omits the symbol list (the live funnel stays lean).
    assert "matched" not in count_r


def test_scan_surfaces_unsupported_primitive(client):
    body = {
        "universe_id": "symbols",
        "symbols": ["AAPL", "MSFT"],
        "rules": [{"primitive_id": "fcf_yield", "operator": "gt", "threshold": 5}],
    }
    r = client.post("/api/screen/scan", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] == []
    assert data["unsupported_primitives"] == ["fcf_yield"]


def test_and_fold_over_endpoint(client):
    body = {
        "universe_id": "symbols",
        "symbols": ["AAPL", "MSFT", "TSLA"],
        "rules": [
            {"primitive_id": "rsi", "operator": "lt", "threshold": 30},
            {"primitive_id": "sma", "operator": "gt", "threshold": 100, "logic_with_prior": "AND"},
        ],
    }
    data = client.post("/api/screen/scan", json=body).json()
    # AAPL passes both; TSLA passes RSI but has no sma cell → excluded.
    assert data["matched"] == ["AAPL"]
