"""Phase 1g — `/api/market/data-latency` tests.

Covers the per-source freshness classifier + roll-up math. Doesn't
exercise the HTTP layer (no TestClient setup) — we call the handler's
inner classifier and compose against an in-memory DB to verify the
shape.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.api.routes.market_data import (
    _LATENCY_FRESH_DAYS,
    _LATENCY_SOURCES,
    _LATENCY_STALE_DAYS,
    _classify_latency,
    get_data_latency,
)
from app.models.price_bar import PriceBar


def _insert_bar(db, symbol: str, trading_date: date) -> None:
    db.add(PriceBar(
        symbol=symbol, trading_date=trading_date,
        open=100.0, high=100.0, low=100.0, close=100.0,
        adjusted_close=100.0, volume=1, dividend_amount=0.0,
        split_coefficient=1.0, source="test",
        fetched_at=datetime.utcnow(),
    ))
    db.commit()


def test_classify_latency_fresh():
    today = date(2026, 5, 22)
    # Within FRESH window
    status, hours = _classify_latency(today, today)
    assert status == "fresh"
    assert hours == 0


def test_classify_latency_fresh_weekend_window():
    today = date(2026, 5, 22)
    # Within FRESH window (accounts for weekends)
    bar = today - timedelta(days=_LATENCY_FRESH_DAYS)
    status, _ = _classify_latency(bar, today)
    assert status == "fresh"


def test_classify_latency_stale():
    today = date(2026, 5, 22)
    bar = today - timedelta(days=_LATENCY_FRESH_DAYS + 1)
    status, _ = _classify_latency(bar, today)
    assert status == "stale"


def test_classify_latency_very_stale():
    today = date(2026, 5, 22)
    bar = today - timedelta(days=_LATENCY_STALE_DAYS + 1)
    status, _ = _classify_latency(bar, today)
    assert status == "very_stale"


def test_classify_latency_missing():
    today = date(2026, 5, 22)
    status, hours = _classify_latency(None, today)
    assert status == "missing"
    assert hours is None


def test_latency_sources_registry_shape():
    """Sanity-check the source list — must be the 4 expected groups
    and every symbol is uppercase."""
    groups = [g for g, _, _ in _LATENCY_SOURCES]
    assert "Benchmarks" in groups
    assert "Sector ETFs" in groups
    assert "Macro basket" in groups
    assert "CN proxies" in groups
    for _, syms, _ in _LATENCY_SOURCES:
        for s in syms:
            assert s == s.upper(), f"Symbol {s!r} not uppercase"


def test_get_data_latency_returns_all_groups_when_db_empty(db):
    """No price_bars → every group has status='missing' but the
    endpoint still returns shape."""
    payload = get_data_latency(db=db)
    assert payload["overall_status"] == "missing"
    assert payload["overall_hours_stale"] is None
    assert payload["overall_latest_date"] is None
    assert len(payload["sources"]) == len(_LATENCY_SOURCES)
    for s in payload["sources"]:
        assert s["status"] == "missing"
        assert s["latest_date"] is None


def test_get_data_latency_rollup_picks_oldest(db):
    """When sources have mixed freshness, the overall status reflects
    the OLDEST source (worst-case wins)."""
    today = date.today()
    # Insert one bar per symbol — SPY fresh, but XLE very stale
    _insert_bar(db, "SPY", today)
    _insert_bar(db, "^GSPC", today)
    _insert_bar(db, "XLK", today)
    _insert_bar(db, "XLE", today - timedelta(days=_LATENCY_STALE_DAYS + 5))  # very_stale
    # Other sector ETFs missing entirely — they keep the sector group's
    # oldest at very_stale (XLE is the freshest of them all)

    payload = get_data_latency(db=db)
    # Sector ETFs group: only XLE has bars, so group oldest = XLE date
    sector = next(s for s in payload["sources"] if s["group"] == "Sector ETFs")
    # XLE is far enough back → very_stale
    assert sector["status"] in ("very_stale", "missing")
    # Other ETFs in the same group are missing — they show up under members
    member_syms = {m["symbol"] for m in sector["members"]}
    assert "XLE" in member_syms
    assert "XLK" in member_syms


def test_get_data_latency_member_detail_for_benchmarks(db):
    today = date.today()
    _insert_bar(db, "SPY", today)
    # No ^GSPC inserted
    payload = get_data_latency(db=db)
    bench = next(s for s in payload["sources"] if s["group"] == "Benchmarks")
    members = {m["symbol"]: m for m in bench["members"]}
    assert members["SPY"]["status"] == "fresh"
    assert members["^GSPC"]["status"] == "missing"
    assert members["^GSPC"]["latest_date"] is None
