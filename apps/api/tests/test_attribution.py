"""Stage 4a — attribution service: track, signup-convert, paid-convert,
self-attribution rejection, first-touch wins."""
from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attribution_visit import AttributionVisit
from app.services.attribution_service import (
    VSID_COOKIE_NAME,
    convert_on_signup,
    mark_paid_conversion,
    track_visit,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _request(cookies: dict | None = None):
    req = MagicMock()
    req.cookies = cookies or {}
    return req


def _response():
    return MagicMock()


# ── Track visit ──────────────────────────────────────────────────────────────


def test_track_visit_creates_row_and_sets_cookie(make_user, db: Session):
    referrer = make_user(email="jimmy@test.com")
    referrer.handle = "jimmy"
    db.commit()

    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="jimmy", landed_url="https://livermore.app/s/abc")

    assert visit is not None
    assert visit.referrer_handle == "jimmy"
    assert visit.referrer_user_id == referrer.id
    assert visit.landed_url == "https://livermore.app/s/abc"
    assert visit.converted_to_user_id is None

    # Cookie was set
    resp.set_cookie.assert_called_once()
    args, kwargs = resp.set_cookie.call_args
    assert args[0] == VSID_COOKIE_NAME
    assert kwargs["httponly"] is True
    assert kwargs["samesite"] == "lax"


def test_track_visit_reuses_cookie_on_second_call(make_user, db: Session):
    referrer = make_user(email="reuse@test.com")
    referrer.handle = "reuse"
    db.commit()

    req1, resp1 = _request(), _response()
    visit1 = track_visit(db, req1, resp1, via_handle="reuse", landed_url="https://x")
    vsid = visit1.visitor_session_id

    req2 = _request(cookies={VSID_COOKIE_NAME: vsid})
    resp2 = _response()
    visit2 = track_visit(db, req2, resp2, via_handle="reuse", landed_url="https://y")
    assert visit2.visitor_session_id == vsid
    # No new cookie set on returning visit
    resp2.set_cookie.assert_not_called()


def test_track_visit_unknown_handle_returns_none(db: Session):
    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="ghost-user-404", landed_url="https://x")
    assert visit is None
    # No row, no cookie
    resp.set_cookie.assert_not_called()


def test_track_visit_normalizes_handle_case(make_user, db: Session):
    referrer = make_user(email="case@test.com")
    referrer.handle = "alice"
    db.commit()

    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="ALICE", landed_url="https://x")
    assert visit is not None
    assert visit.referrer_handle == "alice"


# ── Signup conversion ────────────────────────────────────────────────────────


def test_convert_on_signup_stamps_user_id(make_user, db: Session):
    referrer = make_user(email="ref@test.com")
    referrer.handle = "ref"
    db.commit()

    # Track a visit (anonymous browser)
    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="ref", landed_url="https://x")
    vsid = visit.visitor_session_id

    # Visitor signs up
    new_user = make_user(email="newcomer@test.com")

    # Convert
    signup_req = _request(cookies={VSID_COOKIE_NAME: vsid})
    converted = convert_on_signup(db, signup_req, new_user)
    assert converted is not None
    assert converted.id == visit.id
    assert converted.converted_to_user_id == new_user.id
    assert converted.converted_at is not None


def test_convert_on_signup_first_touch_wins(make_user, db: Session):
    """Two visits before signup → only the FIRST gets converted."""
    referrer = make_user(email="multi-ref@test.com")
    referrer.handle = "multi"
    db.commit()

    req, resp = _request(), _response()
    first_visit = track_visit(db, req, resp, via_handle="multi", landed_url="https://x1")
    vsid = first_visit.visitor_session_id

    # Same browser visits again (different URL, same vsid)
    req2 = _request(cookies={VSID_COOKIE_NAME: vsid})
    resp2 = _response()
    second_visit = track_visit(db, req2, resp2, via_handle="multi", landed_url="https://x2")

    new_user = make_user(email="firsttouch@test.com")
    signup_req = _request(cookies={VSID_COOKIE_NAME: vsid})
    converted = convert_on_signup(db, signup_req, new_user)

    assert converted.id == first_visit.id
    # Second visit remains un-converted
    db.refresh(second_visit)
    assert second_visit.converted_to_user_id is None


def test_convert_on_signup_no_cookie_returns_none(make_user, db: Session):
    new_user = make_user(email="nocookie@test.com")
    req = _request()
    assert convert_on_signup(db, req, new_user) is None


def test_convert_on_signup_self_attribution_rejected(make_user, db: Session):
    """A creator clicking their own share URL then signing up → no self-credit."""
    self_referrer = make_user(email="selfref@test.com")
    self_referrer.handle = "selfref"
    db.commit()

    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="selfref", landed_url="https://x")
    vsid = visit.visitor_session_id

    # Same user "signs up" — convert_on_signup should refuse.
    signup_req = _request(cookies={VSID_COOKIE_NAME: vsid})
    converted = convert_on_signup(db, signup_req, self_referrer)
    assert converted is None
    db.refresh(visit)
    assert visit.converted_to_user_id is None


# ── Paid conversion ──────────────────────────────────────────────────────────


def test_mark_paid_conversion_sets_paid_at(make_user, db: Session):
    referrer = make_user(email="paid-ref@test.com")
    referrer.handle = "paidref"
    db.commit()

    req, resp = _request(), _response()
    visit = track_visit(db, req, resp, via_handle="paidref", landed_url="https://x")
    new_user = make_user(email="paying@test.com")
    convert_on_signup(db, _request(cookies={VSID_COOKIE_NAME: visit.visitor_session_id}), new_user)

    # Now mark paid
    paid = mark_paid_conversion(db, new_user.id, subscription_id="sub_test_123")
    assert paid is not None
    assert paid.converted_to_paid_at is not None
    assert paid.converted_to_user_id == new_user.id


def test_mark_paid_conversion_no_attribution_returns_none(make_user, db: Session):
    """A user who signed up without attribution → paid-conversion is a no-op."""
    user = make_user(email="organic@test.com")
    paid = mark_paid_conversion(db, user.id)
    assert paid is None
