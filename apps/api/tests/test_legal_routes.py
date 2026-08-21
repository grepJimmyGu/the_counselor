"""The disclaimer endpoint.

Public by design: this is the text shown BEFORE someone has an account,
and gating it behind a login would defeat its purpose.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.disclaimer import FULL, SHORT

client = TestClient(app)


def test_disclaimer_is_public():
    """No Authorization header. A 401 here would mean the one piece of copy
    a prospective user most needs is the one they cannot read."""
    r = client.get("/api/legal/disclaimer")
    assert r.status_code == 200


def test_it_serves_the_canonical_text_not_a_copy():
    r = client.get("/api/legal/disclaimer")
    body = r.json()
    assert body["short"] == SHORT
    assert body["full"] == FULL


def test_it_is_cacheable():
    """Static text. Without this every render round-trips for a string that
    changes a few times a year."""
    r = client.get("/api/legal/disclaimer")
    assert "max-age" in r.headers.get("Cache-Control", "")


def test_the_served_text_does_not_claim_we_cannot_see_holdings():
    """The endpoint is the surface a lawyer would actually read. Pin the
    correction here too, not only at the constant."""
    r = client.get("/api/legal/disclaimer")
    assert "do not know your financial situation" not in r.json()["full"]
