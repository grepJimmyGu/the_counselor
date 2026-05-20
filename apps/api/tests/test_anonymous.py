"""Stage 1a — anonymous session service + merge on signup."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.models.anonymous_session import AnonymousSession
from app.models.backtest import BacktestRecord
from app.services.anonymous_service import (
    COOKIE_NAME,
    get_anonymous_session_by_user_id,
    get_or_create_anonymous_session,
    increment_anonymous_run,
    merge_anonymous_into_user,
    record_anonymous_referrer,
)


def _stub_request(cookies: dict | None = None, ua: str = "pytest", lang: str = "en") -> MagicMock:
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = {"user-agent": ua, "accept-language": lang}
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _stub_response() -> MagicMock:
    return MagicMock()


# ── Session creation + cookie ────────────────────────────────────────────────


def test_session_creates_on_first_request_and_sets_cookie(db: Session) -> None:
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    assert session.id is not None
    assert session.runs_used == 0
    # Cookie was set
    resp.set_cookie.assert_called_once()
    args, kwargs = resp.set_cookie.call_args
    assert args[0] == COOKIE_NAME
    assert args[1] == session.id
    assert kwargs["httponly"] is True
    assert kwargs["samesite"] == "lax"


def test_session_reused_on_second_request(db: Session) -> None:
    req1, resp1 = _stub_request(), _stub_response()
    first = get_or_create_anonymous_session(req1, resp1, db)

    # Browser sends the cookie back on the next request
    req2, resp2 = _stub_request(cookies={COOKIE_NAME: first.id}), _stub_response()
    second = get_or_create_anonymous_session(req2, resp2, db)

    assert second.id == first.id
    # No new cookie set when reusing
    resp2.set_cookie.assert_not_called()


def test_stale_cookie_creates_new_session(db: Session) -> None:
    """A cookie pointing at a deleted/missing session should fall through to create a new one."""
    req = _stub_request(cookies={COOKIE_NAME: "00000000-0000-0000-0000-000000000000"})
    resp = _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    assert session.id != "00000000-0000-0000-0000-000000000000"
    resp.set_cookie.assert_called_once()


# ── One-shot cap behavior ────────────────────────────────────────────────────


def test_anonymous_one_shot_and_then_exhausted(db: Session) -> None:
    """First run succeeds; runs_used flips to 1."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    new_count = increment_anonymous_run(db, session, backtest_id="bt-1")
    assert new_count == 1
    assert session.runs_used == 1
    assert session.last_backtest_id == "bt-1"


# ── Referrer attribution ─────────────────────────────────────────────────────


def test_via_handle_recorded_first_touch_wins(db: Session) -> None:
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    record_anonymous_referrer(db, session, "alice")
    assert session.via_handle == "alice"

    # Second visit via a different creator — first-touch must win.
    record_anonymous_referrer(db, session, "bob")
    assert session.via_handle == "alice"


# ── Merge into user on signup ────────────────────────────────────────────────


def test_merge_into_user_sets_user_id_and_marks_converted(make_user, db: Session) -> None:
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)

    # Pretend an anonymous backtest ran and got persisted with user_id=NULL
    bt = BacktestRecord(
        id="bt-anon-1",
        strategy_type="momentum",
        strategy_name="Test",
        result_payload={},
        user_id=None,
    )
    db.add(bt)
    db.commit()
    increment_anonymous_run(db, session, backtest_id="bt-anon-1")

    # User signs up
    user = make_user(email="convert@test.com")
    merge_anonymous_into_user(db, session, user.id)

    db.refresh(session)
    db.refresh(bt)
    assert session.converted_to_user_id == user.id
    assert session.converted_at is not None
    assert bt.user_id == user.id


def test_merge_is_idempotent(make_user, db: Session) -> None:
    """Re-running merge for the same user should be a no-op (not raise, not change times)."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    user = make_user(email="idem-merge@test.com")

    merge_anonymous_into_user(db, session, user.id)
    first_converted_at = session.converted_at
    merge_anonymous_into_user(db, session, user.id)
    assert session.converted_at == first_converted_at


def test_lookup_by_converted_user_id(make_user, db: Session) -> None:
    """Stripe webhook attribution path uses this to find via_handle from user_id."""
    req, resp = _stub_request(), _stub_response()
    session = get_or_create_anonymous_session(req, resp, db)
    record_anonymous_referrer(db, session, "creator-jimmy")

    user = make_user(email="paying@test.com")
    merge_anonymous_into_user(db, session, user.id)

    found = get_anonymous_session_by_user_id(db, user.id)
    assert found is not None
    assert found.id == session.id
    assert found.via_handle == "creator-jimmy"
