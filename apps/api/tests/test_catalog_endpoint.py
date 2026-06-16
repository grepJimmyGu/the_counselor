"""PRD-16a-1 — catalog endpoint tests.

End-to-end: hit `GET /api/signal-primitives` via FastAPI's TestClient
and verify shape + caching headers + ETag handshake.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data.signal_primitives import get_catalog_version_hash
from app.main import app

client = TestClient(app)


def test_get_catalog_returns_200_with_full_payload() -> None:
    """Smoke: the endpoint mounted, fires, returns 200 with the expected
    top-level shape."""
    r = client.get("/api/signal-primitives")
    assert r.status_code == 200
    body = r.json()
    assert "primitives" in body
    assert "categories" in body
    assert "version_hash" in body
    # ≥ 50 primitives per acceptance.
    assert len(body["primitives"]) >= 50
    # All 8 category enum values returned.
    assert len(body["categories"]) == 8


def test_etag_header_present_and_matches_payload_hash() -> None:
    """The ETag header should equal the payload's `version_hash`
    (wrapped in standard quotes). Required for the conditional-GET
    handshake."""
    r = client.get("/api/signal-primitives")
    assert r.status_code == 200
    body = r.json()
    expected = f'"{body["version_hash"]}"'
    assert r.headers["ETag"] == expected


def test_cache_control_set_for_proxy_caching() -> None:
    """We want Vercel + Railway proxies to be able to cache the catalog.
    `public, max-age=3600` says one hour at the edge — content-static, so
    safe."""
    r = client.get("/api/signal-primitives")
    cc = r.headers.get("Cache-Control", "")
    assert "public" in cc
    assert "max-age=3600" in cc


def test_if_none_match_with_matching_hash_returns_304() -> None:
    """The frontend's conditional-GET path: send last-known hash → if
    matches, get 304 + no body → reuse cached payload."""
    current = get_catalog_version_hash()
    r = client.get(
        "/api/signal-primitives",
        headers={"If-None-Match": f'"{current}"'},
    )
    assert r.status_code == 304
    # 304 must return empty body.
    assert r.content == b""
    assert r.headers["ETag"] == f'"{current}"'


def test_if_none_match_with_stale_hash_returns_full_payload() -> None:
    """A stale or unrelated If-None-Match value should not short-circuit;
    the client gets the full payload + the current ETag."""
    r = client.get(
        "/api/signal-primitives",
        headers={"If-None-Match": '"definitely-not-the-current-hash"'},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["primitives"]) >= 50


def test_no_authentication_required() -> None:
    """The catalog is content, not user data — every visitor sees the
    same payload. No Authorization header on the request."""
    r = client.get("/api/signal-primitives")
    assert r.status_code == 200


@pytest.mark.parametrize("category", [
    "trend",
    "mean_reversion",
    "momentum",
    "volume",
    "volatility",
    "fundamental",
    "sentiment",
    "cross_sectional",
])
def test_response_includes_at_least_one_primitive_per_category(category: str) -> None:
    """Front-end filter buttons render per category — every category
    button must produce at least one card on click."""
    r = client.get("/api/signal-primitives")
    body = r.json()
    matches = [p for p in body["primitives"] if p["category"] == category]
    assert len(matches) >= 1, f"No primitives returned for category '{category}'"


def test_catalog_exposes_reading_layer_fields() -> None:
    """PRD-22c slice b: every catalog row carries intent_group (the chip
    grouping) + reading (the headline) so the composer can render the
    intent-first 'what are you reading?' UI."""
    valid_groups = {
        "trend", "momentum", "overbought_oversold", "breakout", "volatility",
        "volume", "value_quality", "sentiment_events", "relative_strength",
    }
    r = client.get("/api/signal-primitives")
    assert r.status_code == 200
    for entry in r.json()["primitives"]:
        assert entry["intent_group"] in valid_groups, entry["id"]
        assert isinstance(entry["reading"], str) and entry["reading"], entry["id"]


def test_catalog_exposes_v2_semantic_fields() -> None:
    """PRD-22a: every catalog row carries output_kind / output_channels /
    composes so the composer (PRD-22c) can dispatch on semantic kind.
    Serialization is automatic via Pydantic once the schema accepts them."""
    valid_kinds = {
        "value", "event", "regime", "level", "distance", "cross", "divergence",
    }
    r = client.get("/api/signal-primitives")
    assert r.status_code == 200
    for entry in r.json()["primitives"]:
        assert entry["output_kind"] in valid_kinds, entry["id"]
        # Always at least one channel; default single-channel is ["value"].
        assert isinstance(entry["output_channels"], list)
        assert entry["output_channels"], entry["id"]
        assert isinstance(entry["composes"], list)
