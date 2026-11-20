"""The portfolio agent: what it looks for, what a scan keeps, and its endpoints."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.routes import agent as agent_routes
from app.models.agent import AgentInsight, AgentProfile
from app.schemas.agent import AgentProfileUpdate
from app.services.agent import checks, monitor
from app.services.agent.checks import Holding

TODAY = date(2026, 11, 20)


# ── Checks ────────────────────────────────────────────────────────────────────

def test_a_move_past_the_threshold_is_reported_and_a_smaller_one_is_not() -> None:
    quotes = {
        "NVDA": {"price": 145.98, "change_percent": -5.2},
        "AAPL": {"price": 349.21, "change_percent": -0.9},
        "MSFT": {"price": 498.30, "change_percent": 4.0},
    }
    found = checks.price_moves(quotes, 4.0, [], TODAY)
    assert [f.symbol for f in found] == ["MSFT", "NVDA"]
    nvda = found[1]
    assert nvda.title == "NVDA is down 5.2% today"
    assert "on your watchlist" in nvda.body and "$145.98" in nvda.body
    assert nvda.action == {"type": "open_company", "symbol": "NVDA"}
    assert nvda.severity == "info"


def test_a_fall_in_something_held_is_marked_to_watch_and_says_what_is_held() -> None:
    quotes = {"NVDA": {"price": 100.0, "change_percent": -6.0}}
    (found,) = checks.price_moves(quotes, 4.0, [Holding("NVDA", 50, 106.0)], TODAY)
    assert found.severity == "watch"
    assert "You hold 50 shares, worth $5,000" in found.body
    # A rise in something held is news, not a warning.
    (up,) = checks.price_moves({"NVDA": {"price": 100.0, "change_percent": 6.0}}, 4.0, [Holding("NVDA", 50, 94.0)], TODAY)
    assert up.severity == "info"


def test_a_move_is_reported_once_a_day_per_direction() -> None:
    quotes = {"NVDA": {"price": 100.0, "change_percent": -6.0}}
    first = checks.price_moves(quotes, 4.0, [], TODAY)[0].dedupe_key
    again = checks.price_moves({"NVDA": {"price": 98.0, "change_percent": -8.0}}, 4.0, [], TODAY)[0].dedupe_key
    tomorrow = checks.price_moves(quotes, 4.0, [], TODAY + timedelta(days=1))[0].dedupe_key
    assert first == again and first != tomorrow


def test_a_holding_over_the_limit_comes_with_the_sale_that_would_fix_it() -> None:
    holdings = [Holding("AAPL", 100, 400.0), Holding("MSFT", 40, 500.0), Holding("JPM", 100, 200.0)]
    # AAPL is 40,000 of 80,000: half. The limit is a quarter.
    (found,) = checks.concentration(holdings, 25.0, TODAY)
    assert found.symbol == "AAPL"
    assert found.title == "AAPL is 50% of your holdings, over your 25% limit"
    # Selling x leaves (40000 - x) / (80000 - x) = 0.25, so x = 26,666.67: 66 whole shares.
    assert found.facts["excess_value"] == pytest.approx(26666.67, abs=0.01)
    assert found.action == {"type": "review_order", "symbol": "AAPL", "side": "sell", "units": 66}
    # After that sale it is at the limit, not under it by a wide margin.
    after = (40000 - 66 * 400) / (80000 - 66 * 400)
    assert 0.25 <= after < 0.26


def test_nothing_is_said_about_a_portfolio_inside_its_limit() -> None:
    even = [Holding(s, 10, 100.0) for s in ("A", "B", "C", "D", "E")]
    assert checks.concentration(even, 25.0, TODAY) == []
    assert checks.concentration([], 25.0, TODAY) == []
    # One holding is all of the portfolio; a limit of 100% allows that.
    assert checks.concentration([Holding("A", 1, 10.0)], 100.0, TODAY) == []


def test_concentration_is_repeated_weekly_not_daily() -> None:
    holdings = [Holding("AAPL", 100, 400.0), Holding("MSFT", 10, 100.0)]
    monday = checks.concentration(holdings, 25.0, date(2026, 11, 16))[0].dedupe_key
    friday = checks.concentration(holdings, 25.0, date(2026, 11, 20))[0].dedupe_key
    next_week = checks.concentration(holdings, 25.0, date(2026, 11, 23))[0].dedupe_key
    assert monday == friday and monday != next_week


def test_a_filing_is_reported_once_with_its_watch_items() -> None:
    (found,) = checks.filing("GOOGL", "Q3 FY2026", ["Gross margin narrowed", "Debt rose"], ["A.", "B."])
    assert found.title == "GOOGL's Q3 FY2026 filing has 2 things to check"
    assert found.body == "A. B."
    assert found.dedupe_key == "filing:GOOGL:Q3 FY2026"
    assert checks.filing("GOOGL", "Q3 FY2026", [], []) == []
    assert "1 thing to check" in checks.filing("X", "Q1 FY2026", ["One"], ["One."])[0].title


def test_waiting_exits_send_the_user_to_the_actions_screen() -> None:
    (found,) = checks.exits_waiting([{"symbol": "NVDA"}, {"symbol": "AMD"}], TODAY)
    assert found.title == "2 exits are waiting on your decision"
    assert found.action == {"type": "open_actions"}
    assert "AMD, NVDA" in found.body
    assert checks.exits_waiting([], TODAY) == []
    assert checks.exits_waiting([{"symbol": "NVDA"}], TODAY)[0].title == "1 exit is waiting on your decision"


def test_no_check_tells_the_user_what_to_do() -> None:
    # The agent reports what happened under rules the user set.
    found = (
        checks.price_moves({"NVDA": {"price": 100.0, "change_percent": -6.0}}, 4.0, [Holding("NVDA", 5, 106.0)], TODAY)
        + checks.concentration([Holding("AAPL", 100, 400.0), Holding("MSFT", 10, 100.0)], 25.0, TODAY)
        + checks.filing("GOOGL", "Q3 FY2026", ["Debt rose"], ["Debt rose 25.9% to $126.1B."])
        + checks.exits_waiting([{"symbol": "NVDA"}], TODAY)
    )
    assert len(found) == 4
    for finding in found:
        words = (finding.title + " " + finding.body).lower().replace(",", " ").replace(".", " ").split()
        for banned in ("should", "must", "recommend", "expect", "will"):
            assert banned not in words, (banned, finding.title)


# ── A scan ────────────────────────────────────────────────────────────────────

class _SameSession:
    """Stands in for SessionLocal. The test database is in-memory SQLite, where
    a second connection is a second, empty database, so code that opens its
    own session is handed the test's session instead."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> "_SameSession":
        return self

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture
def agent_db(db: Session):
    """Point the monitor's own sessions at the test database."""
    factory = _SameSession(db)

    async def inline(function, *args):
        # SQLite keeps one in-memory database per thread, so the scan's
        # blocking steps run on this thread here rather than a worker.
        return function(*args)

    with patch.object(monitor, "SessionLocal", factory), \
         patch.object(agent_routes, "SessionLocal", factory), \
         patch.object(monitor.asyncio, "to_thread", inline):
        yield db


def _scan(user_id: str, *, holdings=None, quotes=None, exits=None, filings=None):
    async def fake_quotes(symbols):
        return {s: q for s, q in (quotes or {}).items() if s in symbols}

    async def fake_filings(symbols, today):
        return list(filings or [])

    with patch.object(monitor, "read_holdings", return_value=holdings), \
         patch.object(monitor, "read_unresolved_exits", return_value=exits or []), \
         patch.object(monitor, "_quotes", fake_quotes), \
         patch.object(monitor, "_filing_findings", fake_filings):
        return asyncio.run(monitor.scan_user(user_id))


def test_a_scan_keeps_what_it_finds_and_finds_it_only_once(make_user, agent_db: Session) -> None:
    user = make_user(email="scan@example.com")
    profile = monitor.get_or_create_profile(agent_db, user.id)
    profile.watchlist = ["NVDA", "AAPL"]
    agent_db.commit()
    quotes = {"NVDA": {"price": 100.0, "change_percent": -6.0}, "AAPL": {"price": 300.0, "change_percent": 0.2}}

    first = _scan(user.id, quotes=quotes)
    assert first.new_insights == 1 and first.symbols_checked == 2
    assert first.brokerage_linked is False
    assert any("No brokerage is linked" in note for note in first.notes)

    second = _scan(user.id, quotes=quotes)
    assert second.new_insights == 0
    assert agent_db.query(AgentInsight).count() == 1
    agent_db.expire_all()
    assert agent_db.get(AgentProfile, user.id).last_scan_at is not None


def test_a_dismissed_insight_does_not_come_back(make_user, agent_db: Session) -> None:
    user = make_user(email="dismiss@example.com")
    monitor.get_or_create_profile(agent_db, user.id).watchlist = ["NVDA"]
    agent_db.commit()
    quotes = {"NVDA": {"price": 100.0, "change_percent": -6.0}}
    _scan(user.id, quotes=quotes)
    row = agent_db.query(AgentInsight).one()

    agent_routes.dismiss_insight(row.id, user=user, db=agent_db)
    assert agent_routes.list_insights(user=user, db=agent_db) == []
    assert _scan(user.id, quotes=quotes).new_insights == 0
    assert agent_routes.list_insights(user=user, db=agent_db) == []


def test_holdings_are_checked_against_the_users_own_limit(make_user, agent_db: Session) -> None:
    user = make_user(email="held@example.com")
    profile = monitor.get_or_create_profile(agent_db, user.id)
    profile.max_position_pct = 40.0
    agent_db.commit()
    holdings = [Holding("AAPL", 100, 400.0), Holding("MSFT", 40, 500.0), Holding("JPM", 100, 200.0)]

    result = _scan(user.id, holdings=holdings)
    assert result.brokerage_linked is True and result.symbols_checked == 3
    (row,) = agent_db.query(AgentInsight).all()
    # 50% against a 40% limit. At the default 25% MSFT (25%) would not have been flagged either.
    assert row.kind == "concentration" and row.symbol == "AAPL"
    assert row.facts["limit_pct"] == 40.0


def test_a_scan_with_nothing_to_watch_says_so(make_user, agent_db: Session) -> None:
    user = make_user(email="empty@example.com")
    result = _scan(user.id)
    assert result.new_insights == 0 and result.symbols_checked == 0
    assert any("Nothing to watch yet" in note for note in result.notes)


def test_a_broker_that_cannot_be_read_does_not_stop_the_rest_of_the_scan(make_user, agent_db: Session) -> None:
    user = make_user(email="broken@example.com")
    monitor.get_or_create_profile(agent_db, user.id).watchlist = ["NVDA"]
    agent_db.commit()

    async def fake_quotes(symbols):
        return {"NVDA": {"price": 100.0, "change_percent": -6.0}}

    async def no_filings(symbols, today):
        return []

    with patch.object(monitor, "read_holdings", side_effect=RuntimeError("broker down")), \
         patch.object(monitor, "read_unresolved_exits", return_value=[]), \
         patch.object(monitor, "_quotes", fake_quotes), \
         patch.object(monitor, "_filing_findings", no_filings):
        result = asyncio.run(monitor.scan_user(user.id))
    assert result.new_insights == 1
    assert any("broker could not be read" in note for note in result.notes)


def test_only_a_recent_filing_is_news() -> None:
    def analysis(filed: date):
        quarter = SimpleNamespace(label="Q3 FY2026", filed=filed)
        finding = SimpleNamespace(severity="watch", title="Debt rose", detail="Debt rose 25.9%.")
        other = SimpleNamespace(severity="good", title="Margin widened", detail="Wider.")
        return SimpleNamespace(quarters=[quarter], findings=[finding, other])

    today = datetime.now(timezone.utc).date()

    async def run(filed: date):
        async def fake(symbol):
            return analysis(filed)
        with patch("app.services.sec_company_facts.filing_analysis", fake):
            return await monitor._filing_findings(["GOOGL"], today)

    recent = asyncio.run(run(today - timedelta(days=5)))
    assert [f.title for f in recent] == ["GOOGL's Q3 FY2026 filing has 1 thing to check"]
    # Filed two months ago: it was news before the agent was watching.
    assert asyncio.run(run(today - timedelta(days=60))) == []


# ── Settings and endpoints ────────────────────────────────────────────────────

def test_the_agent_is_off_until_turned_on_and_settings_change_one_at_a_time(make_user, db: Session) -> None:
    user = make_user(email="profile@example.com")
    profile = agent_routes.get_profile(user=user, db=db)
    assert profile.enabled is False and profile.watchlist == []
    assert (profile.move_alert_pct, profile.max_position_pct) == (4.0, 25.0)

    updated = agent_routes.update_profile(
        AgentProfileUpdate(enabled=True, watchlist=[" nvda", "AAPL", "nvda", "brk.b"]), user=user, db=db)
    assert updated.enabled is True
    assert updated.watchlist == ["NVDA", "AAPL", "BRK.B"]
    # A field that was not sent is left alone.
    assert updated.max_position_pct == 25.0
    again = agent_routes.update_profile(AgentProfileUpdate(notes="I hold for years."), user=user, db=db)
    assert again.enabled is True and again.watchlist == ["NVDA", "AAPL", "BRK.B"]
    assert again.notes == "I hold for years."


def test_settings_outside_their_range_are_refused() -> None:
    for bad in ({"move_alert_pct": 0.2}, {"max_position_pct": 2}, {"max_position_pct": 150},
                {"watchlist": ["NOT A TICKER"]}, {"watchlist": ["A%d" % i for i in range(60)]},
                {"notes": "x" * 1001}):
        with pytest.raises(ValidationError):
            AgentProfileUpdate(**bad)


def test_one_user_cannot_dismiss_anothers_insight(make_user, agent_db: Session) -> None:
    owner = make_user(email="owner@example.com")
    other = make_user(email="other@example.com")
    monitor.get_or_create_profile(agent_db, owner.id).watchlist = ["NVDA"]
    agent_db.commit()
    _scan(owner.id, quotes={"NVDA": {"price": 100.0, "change_percent": -6.0}})
    row = agent_db.query(AgentInsight).one()
    with pytest.raises(HTTPException) as refused:
        agent_routes.dismiss_insight(row.id, user=other, db=agent_db)
    assert refused.value.status_code == 404
    assert agent_routes.list_insights(user=other, db=agent_db) == []
    assert len(agent_routes.list_insights(user=owner, db=agent_db)) == 1


def test_the_scheduled_job_scans_only_users_who_turned_the_agent_on(make_user, agent_db: Session) -> None:
    from app.jobs import agent_monitor_job as job

    on = make_user(email="on@example.com")
    off = make_user(email="off@example.com")
    monitor.get_or_create_profile(agent_db, on.id).enabled = True
    monitor.get_or_create_profile(agent_db, off.id)
    agent_db.commit()
    scanned = []

    async def fake_scan(user_id):
        scanned.append(user_id)
        return monitor.ScanResult(checked_at=datetime.utcnow(), new_insights=2)

    loop = asyncio.new_event_loop()
    import threading
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        with patch.object(job, "SessionLocal", _SameSession(agent_db)), \
             patch.object(monitor, "scan_user", fake_scan), \
             patch.object(monitor, "main_loop", return_value=loop):
            summary = job.agent_monitor_job()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
    assert scanned == [on.id]
    assert summary == {"users": 1, "scanned": 1, "new_insights": 2, "failed": 0}


# ── Email from scheduled checks ───────────────────────────────────────────────

def _finding(severity: str, title: str = "AAPL is 50% of your holdings, over your 25% limit") -> checks.Finding:
    return checks.Finding(kind="concentration", severity=severity, title=title,
                          body="Selling about $26,667 would bring it to 25%.", dedupe_key=title)


def test_new_watch_findings_are_emailed_once_as_one_message(make_user, agent_db: Session) -> None:
    user = make_user(email="mail@example.com")
    monitor.get_or_create_profile(agent_db, user.id)
    findings = [_finding("watch"), _finding("watch", "2 exits are waiting on your decision"), _finding("info", "MSFT is up 4.2% today")]
    with patch("app.services.email_service.send_email", return_value=True) as send:
        assert monitor.email_new_findings(user.id, findings) is True
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["subject"] == "Your agent found 2 things to look at"
    assert "AAPL is 50%" in kwargs["text"] and "2 exits are waiting" in kwargs["text"]
    # Something that is only informational waits for the app to be opened.
    assert "MSFT" not in kwargs["text"]
    assert "does not place orders" in kwargs["text"] and "turn off email" in kwargs["text"]
    assert "http" not in kwargs["text"]


def test_one_finding_is_its_own_subject_and_nothing_to_watch_sends_nothing(make_user, agent_db: Session) -> None:
    user = make_user(email="one@example.com")
    monitor.get_or_create_profile(agent_db, user.id)
    with patch("app.services.email_service.send_email", return_value=True) as send:
        monitor.email_new_findings(user.id, [_finding("watch")])
        assert send.call_args.kwargs["subject"] == "AAPL is 50% of your holdings, over your 25% limit"
        send.reset_mock()
        assert monitor.email_new_findings(user.id, [_finding("info")]) is False
        assert monitor.email_new_findings(user.id, []) is False
    send.assert_not_called()


def test_email_is_not_sent_to_a_user_who_turned_it_off(make_user, agent_db: Session) -> None:
    user = make_user(email="quiet@example.com")
    monitor.get_or_create_profile(agent_db, user.id).email_alerts = False
    agent_db.commit()
    with patch("app.services.email_service.send_email") as send:
        assert monitor.email_new_findings(user.id, [_finding("watch")]) is False
    send.assert_not_called()


def test_a_check_the_user_asked_for_does_not_email_them(make_user, agent_db: Session) -> None:
    user = make_user(email="asked@example.com")
    monitor.get_or_create_profile(agent_db, user.id)
    holdings = [Holding("AAPL", 100, 400.0), Holding("MSFT", 10, 100.0)]
    with patch("app.services.email_service.send_email") as send:
        result = _scan(user.id, holdings=holdings)
    assert [f.kind for f in result.new_findings] == ["concentration"]
    send.assert_not_called()

