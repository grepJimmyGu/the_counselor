"""Market news endpoint — the cache is the whole point.

This route sits on the home page, is anonymous, and calls Alpha Vantage.
Without a cache every page load would be an upstream request and the AV quota
would be gone within the hour — which is exactly the constraint that makes
per-symbol catalysts (blocks 5+6) unaffordable. One upstream call serves every
visitor for 15 minutes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes.market_news as mn
from app.schemas.sentiment import NewsArticle


def _article(title: str) -> NewsArticle:
    return NewsArticle(provider="alpha_vantage", symbol="", title=title)


@pytest.fixture(autouse=True)
def _clear_cache():
    mn._cache = None
    yield
    mn._cache = None


def test_one_upstream_call_serves_repeat_requests(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake(limit: int = 20):
        calls["n"] += 1
        return [_article("Fed holds rates")]

    monkeypatch.setattr(mn, "fetch_market_news", fake)
    client = TestClient(app)

    first = client.get("/api/news/market").json()
    second = client.get("/api/news/market").json()

    assert calls["n"] == 1, "second request re-fetched upstream — the cache is not working"
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["articles"][0]["title"] == "Fed holds rates"


def test_a_failed_refresh_serves_stale_rather_than_blank(monkeypatch) -> None:
    """A ticker that blanks on one bad upstream call is worse than one showing
    20-minute-old headlines."""
    state = {"fail": False}

    async def fake(limit: int = 20):
        return [] if state["fail"] else [_article("Oil slips")]

    monkeypatch.setattr(mn, "fetch_market_news", fake)
    client = TestClient(app)

    client.get("/api/news/market")           # warms the cache
    mn._cache = (mn._cache[0] - 10_000, mn._cache[1])  # force it stale
    state["fail"] = True

    body = client.get("/api/news/market").json()
    assert body["articles"][0]["title"] == "Oil slips"
    assert body["cached"] is True


def test_cold_cache_plus_upstream_failure_is_empty_not_an_error(monkeypatch) -> None:
    async def fake(limit: int = 20):
        return []

    monkeypatch.setattr(mn, "fetch_market_news", fake)
    r = TestClient(app).get("/api/news/market")
    assert r.status_code == 200
    assert r.json()["articles"] == []


def test_limit_is_bounded(monkeypatch) -> None:
    async def fake(limit: int = 20):
        return [_article(f"n{i}") for i in range(50)]

    monkeypatch.setattr(mn, "fetch_market_news", fake)
    client = TestClient(app)

    assert len(client.get("/api/news/market?limit=5").json()["articles"]) == 5
    # Out-of-range values are rejected at the boundary rather than passed to AV.
    assert client.get("/api/news/market?limit=999").status_code == 422
    assert client.get("/api/news/market?limit=0").status_code == 422


def test_age_is_reported_so_the_ui_can_show_freshness(monkeypatch) -> None:
    async def fake(limit: int = 20):
        return [_article("A")]

    monkeypatch.setattr(mn, "fetch_market_news", fake)
    client = TestClient(app)

    assert client.get("/api/news/market").json()["age_seconds"] == 0
    mn._cache = (mn._cache[0] - 300, mn._cache[1])
    assert client.get("/api/news/market").json()["age_seconds"] >= 300
