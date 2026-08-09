"""POST /api/screen/metric-values — snapshot values for an explicit basket.

The results page uses this to add a technical column to names it already
shows. `scan` returns values only for the primitives its rules referenced, so
"also show me RSI" on a screen that filtered by something else has nothing to
read; this fills that gap without re-running the screen.

Same StaticPool fixture as `test_screen_endpoints.py`: the route's `get_db`
session must hit the same in-memory DB the seed wrote to, which the shared
`db` fixture can't guarantee under TestClient.
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
from app.services.screener.signal_snapshot_service import (
    SignalSnapshotService,
    snapshot_primitive_ids,
)

AS_OF = date(2026, 6, 15)

# Real snapshot-covered primitives, so the "unavailable" split is exercised
# against the actual catalog rather than a name invented for the test.
COVERED = [p for p in snapshot_primitive_ids()][:2]


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
    svc.write_symbol(seed, "AAPL", {COVERED[0]: 25.0, COVERED[1]: 150.0}, AS_OF)
    svc.write_symbol(seed, "MSFT", {COVERED[0]: 55.0}, AS_OF)
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


def _post(client, **kwargs):
    return client.post("/api/screen/metric-values", json=kwargs)


def test_returns_requested_values(client):
    r = _post(client, symbols=["AAPL", "MSFT"], primitives=COVERED)
    assert r.status_code == 200
    body = r.json()
    assert body["values"]["AAPL"][COVERED[0]] == 25.0
    assert body["values"]["AAPL"][COVERED[1]] == 150.0
    assert body["as_of_date"] == AS_OF.isoformat()
    assert body["unavailable"] == []


def test_symbol_missing_a_primitive_omits_the_cell_not_the_row(client):
    """MSFT has COVERED[0] but not COVERED[1]. The row must still come back
    with the value it does have — dropping the row would lose a real reading,
    and a 0 for the missing one would sort as the lowest reading in the
    table."""
    r = _post(client, symbols=["MSFT"], primitives=COVERED)
    row = r.json()["values"]["MSFT"]
    assert row[COVERED[0]] == 55.0
    assert COVERED[1] not in row


def test_unknown_symbol_is_omitted_not_null(client):
    r = _post(client, symbols=["AAPL", "NOSUCH"], primitives=COVERED[:1])
    values = r.json()["values"]
    assert "AAPL" in values
    assert "NOSUCH" not in values


def test_uncovered_primitive_is_reported_not_silently_empty(client):
    """A primitive the daily snapshot doesn't carry must come back named in
    `unavailable`. Returning it as an empty column would tell the user these
    stocks have no value for it, which is a different — and false — claim."""
    r = _post(client, symbols=["AAPL"], primitives=[COVERED[0], "pe_ratio"])
    body = r.json()
    assert body["unavailable"] == ["pe_ratio"]
    # The covered one is still served; one bad name doesn't void the request.
    assert body["values"]["AAPL"][COVERED[0]] == 25.0


def test_all_primitives_uncovered_returns_empty_values_and_names_them(client):
    r = _post(client, symbols=["AAPL"], primitives=["pe_ratio", "dividend_yield"])
    body = r.json()
    assert body["values"] == {}
    assert set(body["unavailable"]) == {"pe_ratio", "dividend_yield"}


def test_symbol_cap_applies_to_the_request_not_the_response(client):
    """A symbol past the cap must not come back. If the cap were applied to
    the response instead, it would look enforced while the DB had already been
    asked for every name — the cost the cap exists to bound."""
    from app.api.routes.screen import _METRIC_VALUES_SYMBOL_CAP

    padding = [f"FILL{i}" for i in range(_METRIC_VALUES_SYMBOL_CAP)]
    r = _post(client, symbols=padding + ["AAPL"], primitives=COVERED[:1])
    assert "AAPL" not in r.json()["values"]


def test_primitive_cap_applies_to_the_request(client):
    from app.api.routes.screen import _METRIC_VALUES_PRIMITIVE_CAP

    padding = [f"fake_{i}" for i in range(_METRIC_VALUES_PRIMITIVE_CAP)]
    r = _post(client, symbols=["AAPL"], primitives=padding + [COVERED[0]])
    body = r.json()
    assert body["values"] == {}
    assert COVERED[0] not in body["unavailable"]


def test_empty_lists_are_rejected(client):
    """Empty means "nothing asked for", and the endpoint must not read that as
    a wildcard — the failure mode `screen()` has, where no filters means the
    whole universe."""
    assert _post(client, symbols=[], primitives=COVERED[:1]).status_code == 422
    assert _post(client, symbols=["AAPL"], primitives=[]).status_code == 422
