"""PRD-23c PR1 — saved-screen tracking: rescan/diff + new-entrant notify.

The novel logic is the basket DIFF (transition-only membership) and the cron's
notify-per-new-entrant. Both are tested against the in-memory `db` fixture with
`scan()` stubbed, so no warmed snapshot is needed. The Scout-402/Strategist-200
endpoint tier-gate e2e is deferred to PR2 (UI) — see PROJECT_BACKLOG.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.saved_strategy import SavedStrategy
from app.models.screen_basket_member import ScreenBasketMember
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.schemas.screener_scan import ScreenSaveRequest
from app.services.screener import saved_screen_service
from app.services.screener.saved_screen_service import (
    current_basket,
    is_screen,
    rescan_and_diff,
    screen_strategy_json,
)
from app.services.screener.scan_service import ScanResult
from app.jobs import saved_screen_cron


# ── helpers ──────────────────────────────────────────────────────────────────


def _scan_result(matched, as_of="2026-06-17") -> ScanResult:
    return ScanResult(
        matched=list(matched),
        readings={s: [] for s in matched},
        as_of_date=date.fromisoformat(as_of),
        universe_size=500,
        matched_count=len(matched),
    )


def _make_screen(db, *, user_id="u1", title="Pullback screen", universe_id="sp500"):
    s = SavedStrategy(
        id=str(uuid4()),
        user_id=user_id,
        title=title,
        strategy_json=screen_strategy_json(universe_id, []),
        is_public=False,
    )
    db.add(s)
    db.commit()
    return s


def _patch_scan(monkeypatch, sequence):
    """`scan()` returns the next basket from `sequence` on each call."""
    calls = iter(sequence)
    monkeypatch.setattr(
        saved_screen_service, "scan", lambda db, uid, rules, **kw: _scan_result(next(calls))
    )


# ── service: rescan / diff (the core) ────────────────────────────────────────


def test_is_screen_distinguishes_screens_from_plain_strategies(db):
    assert is_screen(_make_screen(db))
    plain = SavedStrategy(
        id=str(uuid4()), user_id="u1", title="x",
        strategy_json={"strategy_type": "custom_build"},
    )
    assert not is_screen(plain)


def test_first_rescan_seeds_the_whole_basket(db, monkeypatch):
    screen = _make_screen(db)
    _patch_scan(monkeypatch, [["AAPL", "MSFT", "CAT"]])
    diff = rescan_and_diff(db, screen)
    assert sorted(diff.new_entrants) == ["AAPL", "CAT", "MSFT"]
    assert diff.exits == []
    assert {m.symbol for m in current_basket(db, screen.id)} == {"AAPL", "MSFT", "CAT"}


def test_staying_in_the_basket_is_not_a_new_entrant(db, monkeypatch):
    screen = _make_screen(db)
    _patch_scan(monkeypatch, [["AAPL", "MSFT"], ["AAPL", "MSFT"]])
    rescan_and_diff(db, screen)          # seed
    diff = rescan_and_diff(db, screen)   # unchanged
    assert diff.new_entrants == [] and diff.exits == []


def test_entrant_and_exit_are_detected(db, monkeypatch):
    screen = _make_screen(db)
    _patch_scan(monkeypatch, [["AAPL", "MSFT"], ["MSFT", "NVDA"]])
    rescan_and_diff(db, screen)          # seed {AAPL, MSFT}
    diff = rescan_and_diff(db, screen)   # AAPL out, NVDA in
    assert diff.new_entrants == ["NVDA"]
    assert diff.exits == ["AAPL"]
    assert {m.symbol for m in current_basket(db, screen.id)} == {"MSFT", "NVDA"}


def test_reentry_after_exit_fires_again_and_keeps_history(db, monkeypatch):
    screen = _make_screen(db)
    _patch_scan(monkeypatch, [["AAPL"], [], ["AAPL"]])
    rescan_and_diff(db, screen)                  # seed {AAPL}
    d2 = rescan_and_diff(db, screen)             # AAPL exits
    assert d2.exits == ["AAPL"] and d2.new_entrants == []
    d3 = rescan_and_diff(db, screen)             # AAPL re-enters
    assert d3.new_entrants == ["AAPL"]
    rows = (
        db.execute(
            select(ScreenBasketMember).where(ScreenBasketMember.symbol == "AAPL")
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2  # two distinct stints
    assert sum(1 for r in rows if r.exited_date is None) == 1


def test_rescan_is_idempotent_for_a_given_as_of(db, monkeypatch):
    screen = _make_screen(db)
    _patch_scan(monkeypatch, [["AAPL", "MSFT"], ["AAPL", "MSFT"]])
    rescan_and_diff(db, screen)
    diff = rescan_and_diff(db, screen)  # same scan again → nothing fires, no dup rows
    assert diff.new_entrants == []
    assert len(current_basket(db, screen.id)) == 2


# ── cron: notify on new entrants ─────────────────────────────────────────────


class _SessionCtx:
    """Make `with SessionLocal() as db:` yield the test session without closing it."""

    def __init__(self, session):
        self._s = session

    def __enter__(self):
        return self._s

    def __exit__(self, *a):
        return False


def _wire_cron(db, monkeypatch, scan_sequence, *, subscribed=True):
    monkeypatch.setenv("SCREENER_SNAPSHOT_ENABLED", "true")
    screen = _make_screen(db)
    if subscribed:
        db.add(
            SignalAlertSubscription(
                user_id=screen.user_id, saved_strategy_id=screen.id, email_enabled=True
            )
        )
        db.commit()
    _patch_scan(monkeypatch, scan_sequence)
    banners = []
    monkeypatch.setattr(
        saved_screen_cron, "dispatch_in_app_banner", lambda ev: banners.append(ev) or True
    )
    monkeypatch.setattr(saved_screen_cron, "SessionLocal", lambda: _SessionCtx(db))
    return screen, banners


def test_cron_noops_when_flag_disabled(db, monkeypatch):
    monkeypatch.delenv("SCREENER_SNAPSHOT_ENABLED", raising=False)
    stats = saved_screen_cron.monitor_saved_screens()
    assert stats["screens"] == 0 and stats["dispatched"] == 0


def test_cron_fires_one_alert_and_one_signalevent_per_new_entrant(db, monkeypatch):
    # Seed {AAPL}, then the cron scan returns {AAPL, NVDA} → only NVDA is new.
    screen, banners = _wire_cron(db, monkeypatch, [["AAPL"], ["AAPL", "NVDA"]])
    rescan_and_diff(db, screen)  # seed silently (consumes the first scan)
    stats = saved_screen_cron.monitor_saved_screens()
    assert stats["entrants"] == 1 and stats["dispatched"] == 1
    assert len(banners) == 1 and banners[0].new_signal_display.startswith("NVDA entered")
    events = (
        db.execute(select(SignalEvent).where(SignalEvent.change_type == "screen_entrant"))
        .scalars()
        .all()
    )
    assert len(events) == 1 and events[0].new_signal_display.startswith("NVDA")


def test_cron_does_not_refire_for_a_symbol_that_stays(db, monkeypatch):
    screen, banners = _wire_cron(db, monkeypatch, [["AAPL"], ["AAPL"]])
    rescan_and_diff(db, screen)  # seed {AAPL}
    stats = saved_screen_cron.monitor_saved_screens()  # AAPL stays
    assert stats["dispatched"] == 0 and banners == []


def test_cron_skips_unsubscribed_screens(db, monkeypatch):
    screen, banners = _wire_cron(
        db, monkeypatch, [["AAPL"], ["AAPL", "NVDA"]], subscribed=False
    )
    rescan_and_diff(db, screen)
    stats = saved_screen_cron.monitor_saved_screens()
    assert stats["screens"] == 0 and banners == []


# ── guards: standing-only + auth-gated ───────────────────────────────────────


def test_save_request_rejects_non_standing_universe():
    # A single symbol is the build-from-scratch path, not a trackable basket.
    with pytest.raises(ValidationError):
        ScreenSaveRequest(title="My screen", universe_id="symbols", rules=[])
    # sp500 + sector are accepted.
    assert ScreenSaveRequest(title="My screen", universe_id="sp500", rules=[]).universe_id == "sp500"
    assert ScreenSaveRequest(title="My screen", universe_id="sector_XLK", rules=[]).universe_id == "sector_XLK"


def test_save_endpoint_requires_auth():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        client = TestClient(app)
        r = client.post(
            "/api/screen/save",
            json={"title": "Pullback screen", "universe_id": "sp500", "rules": []},
        )
        # allow_anonymous=False → unauthenticated callers can't track screens.
        assert r.status_code == 401, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
