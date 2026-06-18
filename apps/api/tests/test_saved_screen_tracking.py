"""PRD-23c PR1 — saved-screen tracking: rescan/diff + new-entrant notify.

The novel logic is the basket DIFF (transition-only membership) and the cron's
notify-per-new-entrant. Both are tested against the in-memory `db` fixture with
`scan()` stubbed, so no warmed snapshot is needed. The Scout-402/Strategist-200
endpoint tier-gate e2e is deferred to PR2 (UI) — see PROJECT_BACKLOG.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
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


# ── authed endpoint e2e: tier-gate (save) + owner-gate (read) ────────────────

from app.api.deps import get_current_user  # noqa: E402
from app.api.routes.auth import _create_user_with_plan  # noqa: E402


@pytest.fixture
def authed(monkeypatch):
    """Shared-engine TestClient + a `set_user(tier)` factory. `scan()` is
    stubbed so /save's basket seed is deterministic."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    seed = Local()
    state: dict = {"user": None}

    def _override_db():
        s = Local()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    monkeypatch.setattr(
        saved_screen_service, "scan", lambda db, uid, rules, **kw: _scan_result(["AAPL", "MSFT"])
    )

    def set_user(tier="strategist", email="t@x.com"):
        u = _create_user_with_plan(seed, email=email, password_hash=None, oauth_provider=None, oauth_subject=None)
        if tier != "scout":
            u.plan.tier = tier
            seed.commit()
            seed.refresh(u)
        _ = u.plan.tier  # force-load plan so cross-session reads don't lazy-load
        state["user"] = u
        return u

    yield TestClient(app), set_user, seed
    seed.close()
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    engine.dispose()


def _save_body(title="Pullback screen"):
    return {"title": title, "universe_id": "sp500", "rules": []}


def test_save_endpoint_seeds_basket_for_strategist(authed):
    client, set_user, _ = authed
    set_user(tier="strategist")
    r = client.post("/api/screen/save", json=_save_body())
    assert r.status_code == 200, r.text
    data = r.json()
    assert sorted(data["basket"]) == ["AAPL", "MSFT"]
    assert data["saved_strategy_id"]


def _gating_on(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.screen.get_settings", lambda: SimpleNamespace(gating_enabled=True)
    )


def test_save_endpoint_blocks_scout_with_402(authed, monkeypatch):
    _gating_on(monkeypatch)
    client, set_user, _ = authed
    set_user(tier="scout")
    r = client.post("/api/screen/save", json=_save_body())
    assert r.status_code == 402, r.text
    assert r.json()["detail"]["entitlement"]["code"] == "screen_tracking_locked"


def test_gating_off_lifts_the_tier_gate(authed, monkeypatch):
    # GATING_ENABLED=false (shadow mode) → any signed-in tier can save + track.
    monkeypatch.setattr(
        "app.api.routes.screen.get_settings", lambda: SimpleNamespace(gating_enabled=False)
    )
    client, set_user, _ = authed
    set_user(tier="scout")
    r = client.post("/api/screen/save", json={**_save_body(), "bar_resolution": "intraday"})
    assert r.status_code == 200, r.text  # Scout + intraday, both gates lifted


def test_get_saved_screen_returns_basket_and_history(authed):
    client, set_user, _ = authed
    set_user(tier="strategist")
    saved_id = client.post("/api/screen/save", json=_save_body()).json()["saved_strategy_id"]
    r = client.get(f"/api/screen/saved/{saved_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert sorted(data["basket"]) == ["AAPL", "MSFT"]
    assert data["basket_size"] == 2
    assert {h["symbol"] for h in data["history"]} == {"AAPL", "MSFT"}
    assert all(h["is_current"] for h in data["history"])


def test_get_saved_screen_404_for_non_owner(authed):
    client, set_user, _ = authed
    set_user(tier="strategist", email="owner@x.com")
    saved_id = client.post("/api/screen/save", json=_save_body()).json()["saved_strategy_id"]
    set_user(tier="strategist", email="intruder@x.com")  # different user
    assert client.get(f"/api/screen/saved/{saved_id}").status_code == 404


def test_list_saved_screens_returns_the_users_screens(authed):
    client, set_user, _ = authed
    set_user(tier="strategist")
    client.post("/api/screen/save", json=_save_body("Screen A"))
    r = client.get("/api/screen/saved")
    assert r.status_code == 200, r.text
    screens = r.json()["screens"]
    assert len(screens) == 1
    assert screens[0]["title"] == "Screen A" and screens[0]["basket_size"] == 2


def test_saved_screens_excluded_from_my_strategies(authed):
    """A tracked screen (kind=='screen') must NOT leak into GET
    /api/saved-strategies — it has no backtest and would render broken on the
    strategy-detail page. It lives at /screens instead (PR2c). A plain
    strategy in the same account still shows up."""
    client, set_user, seed = authed
    user = set_user(tier="strategist")
    client.post("/api/screen/save", json=_save_body("My screen"))
    plain = SavedStrategy(
        id=str(uuid4()),
        user_id=user.id,
        title="My plain strategy",
        strategy_json={"strategy_type": "custom_build"},
        is_public=False,
    )
    seed.add(plain)
    seed.commit()

    r = client.get("/api/saved-strategies")
    assert r.status_code == 200, r.text
    titles = [s["title"] for s in r.json()]
    assert "My plain strategy" in titles
    assert "My screen" not in titles


# ── PR3: intraday ────────────────────────────────────────────────────────────


def test_rescan_uses_the_screens_bar_resolution(db, monkeypatch):
    screen = SavedStrategy(
        id=str(uuid4()), user_id="u1", title="Intraday screen",
        strategy_json=screen_strategy_json("sp500", [], bar_resolution="intraday"),
        is_public=False,
    )
    db.add(screen)
    db.commit()
    captured: dict = {}

    def fake_scan(db_, uid, rules, **kw):
        captured["resolution"] = kw.get("resolution")
        return _scan_result(["AAPL"])

    monkeypatch.setattr(saved_screen_service, "scan", fake_scan)
    rescan_and_diff(db, screen)
    assert captured["resolution"] == "intraday"


def test_daily_screen_scans_daily(db, monkeypatch):
    screen = _make_screen(db)  # default bar_resolution = "daily"
    captured: dict = {}

    def fake_scan(db_, uid, rules, **kw):
        captured["resolution"] = kw.get("resolution")
        return _scan_result([])

    monkeypatch.setattr(saved_screen_service, "scan", fake_scan)
    rescan_and_diff(db, screen)
    assert captured["resolution"] == "daily"


def test_intraday_warm_writes_rows_from_intraday_bars(db, monkeypatch):
    import asyncio

    import pandas as pd

    from app.models.signal_snapshot import SignalSnapshot
    from app.services.screener.signal_snapshot_service import SignalSnapshotService

    idx = pd.date_range("2026-06-17 09:30", periods=250, freq="15min")
    closes = [100.0 + i * 0.1 for i in range(250)]
    frame = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1_000_000.0},
        index=idx,
    )

    async def fake_get_bars(self, db_, symbol, interval, start, end):
        return frame

    monkeypatch.setattr(
        "app.services.intraday_bar_service.IntradayBarService.get_bars", fake_get_bars
    )
    n = asyncio.run(SignalSnapshotService().warm_symbol(db, "AAPL", resolution="intraday"))
    assert n > 0
    rows = (
        db.execute(select(SignalSnapshot).where(SignalSnapshot.resolution == "intraday"))
        .scalars()
        .all()
    )
    assert rows and all(r.symbol == "AAPL" for r in rows)


def test_intraday_screen_requires_quant(authed, monkeypatch):
    _gating_on(monkeypatch)
    client, set_user, _ = authed
    set_user(tier="strategist")
    r = client.post("/api/screen/save", json={**_save_body(), "bar_resolution": "intraday"})
    assert r.status_code == 402, r.text
    assert r.json()["detail"]["entitlement"]["code"] == "screen_tracking_locked"
    set_user(tier="quant", email="q@x.com")
    r2 = client.post("/api/screen/save", json={**_save_body(), "bar_resolution": "intraday"})
    assert r2.status_code == 200, r2.text
