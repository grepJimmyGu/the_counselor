"""Resetting a forgotten password with an emailed code."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.api.deps import _LEGACY_USER_ID, get_current_user, get_current_user_or_anonymous
from app.api.routes.auth import (
    _send_reset_code,
    confirm_password_reset,
    password_login,
    request_password_reset,
)
from app.emails.password_reset import render_password_changed, render_reset_code
from app.models.password_reset import PasswordResetCode
from app.schemas.identity import LoginRequest, PasswordResetConfirm, PasswordResetRequest
from app.services import password_reset
from app.services.auth_service import create_session_token, verify_password

OLD = "old-password"
NEW = "Quiet-Harbor7-wren"
EMAIL = "kim@example.com"


@pytest.fixture
def user(make_user):
    return make_user(email=EMAIL, password=OLD)


def _confirm(db: Session, code: str, password: str = NEW, email: str = EMAIL, breaches=0):
    tasks = BackgroundTasks()
    with patch("app.api.routes.auth.breach_count", return_value=breaches):
        result = confirm_password_reset(
            PasswordResetConfirm(email=email, code=code, new_password=password), tasks, db=db,
        )
    return result, tasks


def _rejection(result) -> dict:
    assert result.status_code == 400
    return json.loads(result.body)


def _wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


# ── The code ──────────────────────────────────────────────────────────────────

def test_a_code_is_six_digits_and_is_not_stored(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    assert len(code) == 6 and code.isdigit()
    row = db.query(PasswordResetCode).one()
    assert code not in row.code_hash
    assert len(row.code_hash) == 64
    assert row.expires_at - row.created_at == password_reset.CODE_LIFETIME


def test_the_right_code_is_accepted_and_a_wrong_one_counted(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    assert password_reset.check_code(db, user, _wrong(code)) is None
    assert db.query(PasswordResetCode).one().attempts == 1
    assert password_reset.check_code(db, user, f" {code} ") is not None


def test_a_code_stops_working_after_five_wrong_guesses(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    for _ in range(password_reset.MAX_ATTEMPTS):
        assert password_reset.check_code(db, user, _wrong(code)) is None
    # Even the right code is refused now: the guesses are spent.
    assert password_reset.check_code(db, user, code) is None


def test_a_code_expires(user, db: Session) -> None:
    start = datetime(2026, 11, 19, 12, 0, 0)
    code = password_reset.issue_code(db, user, now=start)
    assert password_reset.check_code(db, user, code, now=start + timedelta(minutes=14)) is not None
    assert password_reset.check_code(db, user, code, now=start + timedelta(minutes=16)) is None


def test_asking_again_closes_the_earlier_code(user, db: Session) -> None:
    first = password_reset.issue_code(db, user)
    second = password_reset.issue_code(db, user)
    if first != second:
        assert password_reset.check_code(db, user, first) is None
    assert password_reset.check_code(db, user, second) is not None


def test_an_account_is_sent_three_codes_an_hour_and_six_a_day(user, db: Session) -> None:
    start = datetime(2026, 11, 19, 8, 0, 0)
    for minute in range(3):
        assert password_reset.issue_code(db, user, now=start + timedelta(minutes=minute))
    assert password_reset.issue_code(db, user, now=start + timedelta(minutes=30)) is None
    # A refused request must not close the code already sent.
    assert password_reset._open_codes(db, user.id, start + timedelta(minutes=10)).count() == 1

    later = start + timedelta(hours=2)
    for minute in range(3):
        assert password_reset.issue_code(db, user, now=later + timedelta(minutes=minute))
    # Six in the day now; the hour's allowance has room again but the day's does not.
    assert password_reset.issue_code(db, user, now=start + timedelta(hours=5)) is None
    assert password_reset.issue_code(db, user, now=start + timedelta(hours=25))


# ── Confirming ────────────────────────────────────────────────────────────────

def test_the_code_sets_the_new_password_and_signs_in(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    result, tasks = _confirm(db, code)

    assert result.session_token
    db.refresh(user)
    assert verify_password(NEW, user.password_hash)
    assert not verify_password(OLD, user.password_hash)
    assert user.password_changed_at is not None
    # Typing the code back proved the address.
    assert user.email_verified_at is not None
    assert password_login(LoginRequest(email=EMAIL, password=NEW), db=db).session_token
    # The "your password was changed" notice is queued for after the reply.
    assert len(tasks.tasks) == 1


def test_a_code_cannot_be_used_twice(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    _confirm(db, code)
    result, _ = _confirm(db, code, password="Other-Meadow4-finch")
    assert _rejection(result)["code"] == "invalid_code"
    db.refresh(user)
    assert verify_password(NEW, user.password_hash)


def test_a_wrong_code_and_an_unknown_address_get_the_same_answer(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    wrong, _ = _confirm(db, _wrong(code))
    unknown, _ = _confirm(db, code, email="nobody@example.com")
    assert _rejection(wrong) == _rejection(unknown)
    assert _rejection(wrong)["code"] == "invalid_code"
    db.refresh(user)
    assert verify_password(OLD, user.password_hash)


def test_a_weak_password_is_refused_without_spending_a_guess(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    result, _ = _confirm(db, _wrong(code), password="short")
    body = _rejection(result)
    assert body["code"] == "weak_password" and "length" in body["failed"]
    assert db.query(PasswordResetCode).one().attempts == 0


def test_a_breached_password_is_refused_and_the_code_still_works(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    result, _ = _confirm(db, code, breaches=12)
    assert _rejection(result)["code"] == "breached_password"
    again, _ = _confirm(db, code, password="Other-Meadow4-finch")
    assert again.session_token


def test_an_account_that_only_used_google_can_set_a_password(make_user, db: Session) -> None:
    google = make_user(email="g@example.com", oauth_provider="google", oauth_subject="sub-1")
    assert google.password_hash is None
    code = password_reset.issue_code(db, google)
    result, _ = _confirm(db, code, email="g@example.com")
    assert result.session_token
    db.refresh(google)
    assert verify_password(NEW, google.password_hash)
    # Google sign-in is untouched.
    assert google.oauth_subject == "sub-1"


# ── Asking for a code ─────────────────────────────────────────────────────────

def test_the_reply_is_the_same_for_any_address_and_is_sent_before_any_lookup() -> None:
    known, unknown = BackgroundTasks(), BackgroundTasks()
    first = request_password_reset(PasswordResetRequest(email=EMAIL), known)
    second = request_password_reset(PasswordResetRequest(email="nobody@example.com"), unknown)
    assert first == second
    # No database session is involved in the reply; the work is queued.
    assert len(known.tasks) == len(unknown.tasks) == 1


def test_the_code_is_emailed_as_a_transactional_message(user, db: Session) -> None:
    with patch("app.services.email_service.send_email", return_value=True) as send:
        _send_reset_code(db, EMAIL)
    kwargs = send.call_args.kwargs
    assert kwargs["category"] == "transactional" and kwargs["template"] == "password_reset"
    row = db.query(PasswordResetCode).one()
    codes = [word for word in kwargs["text"].split() if len(word) == 6 and word.isdigit()]
    assert len(codes) == 1
    assert password_reset.check_code(db, user, codes[0]) is not None
    assert row.closed_at is None


def test_nothing_is_sent_to_an_address_with_no_account(db: Session) -> None:
    with patch("app.services.email_service.send_email") as send:
        _send_reset_code(db, "nobody@example.com")
    send.assert_not_called()
    assert db.query(PasswordResetCode).count() == 0


def test_a_code_that_could_not_be_emailed_is_logged_as_an_error(user, db: Session, caplog) -> None:
    # Without RESEND_API_KEY send_email quietly does nothing. A user would
    # wait for a code that never comes, so this one is loud.
    with caplog.at_level(logging.ERROR, logger="livermore.auth"):
        with patch("app.services.email_service.send_email", return_value=False):
            _send_reset_code(db, EMAIL)
    assert "NOT emailed" in caplog.text


def test_the_emails_carry_the_code_and_no_links(user) -> None:
    code_email = render_reset_code(user, "482913")
    changed = render_password_changed(user)
    assert "482913" in code_email["text"] and "482913" in code_email["html"]
    assert "482913" not in code_email["subject"]
    for part in (code_email["text"], code_email["html"], changed["text"], changed["html"]):
        assert "http" not in part


# ── Sessions from before the reset ────────────────────────────────────────────

def _request(token: str) -> MagicMock:
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}
    return request


def _legacy_token(user_id: str, issued: datetime) -> str:
    """A token as they were minted before 2026-11-19: an expiry and no `iat`."""
    payload = {"sub": user_id, "tier": "scout", "exp": issued + timedelta(days=30)}
    return jwt.encode(payload, get_settings().nextauth_secret, algorithm="HS256")


def test_a_reset_signs_out_sessions_from_before_it(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    with patch("app.services.auth_service.datetime") as clock:
        clock.utcnow.return_value = datetime.utcnow() - timedelta(hours=1)
        before = create_session_token(user.id, "scout")
    assert get_current_user(_request(before), db=db).id == user.id

    result, _ = _confirm(db, code)

    with pytest.raises(HTTPException) as refused:
        get_current_user(_request(before), db=db)
    assert refused.value.status_code == 401
    assert refused.value.detail == "Invalid or expired session token."
    # A permissive route treats it as it treats an expired token: anonymous.
    assert get_current_user_or_anonymous(_request(before), db=db).id == _LEGACY_USER_ID
    # The session the reset itself handed out is good.
    assert get_current_user(_request(result.session_token), db=db).id == user.id


def test_tokens_minted_before_issue_times_were_recorded_are_dated_by_their_expiry(user, db: Session) -> None:
    old = _legacy_token(user.id, datetime.utcnow() - timedelta(days=3))
    # No reset has happened: nobody is signed out by this change alone.
    assert get_current_user(_request(old), db=db).id == user.id

    code = password_reset.issue_code(db, user)
    _confirm(db, code)
    with pytest.raises(HTTPException):
        get_current_user(_request(old), db=db)


def test_a_new_token_records_when_it_was_issued(user) -> None:
    payload = jwt.get_unverified_claims(create_session_token(user.id, "scout"))
    assert payload["exp"] - payload["iat"] == 30 * 86400


# ── The website's session ─────────────────────────────────────────────────────

def test_the_website_cannot_renew_a_session_from_before_the_reset(user, db: Session) -> None:
    """The site's own cookie rolls forward for ever and asks this endpoint for
    a new backend token when the old one ages out. Without this refusal a
    thief's browser session would be handed a fresh token weeks after the
    owner reset the password."""
    from app.api.routes.auth import _RefreshSessionTokenRequest, refresh_session_token

    old = _legacy_token(user.id, datetime.utcnow() - timedelta(days=29))
    request = _RefreshSessionTokenRequest(email=EMAIL, current_token=old)
    # No reset yet: the refresh works as it always has.
    assert refresh_session_token(request, db=db).session_token

    code = password_reset.issue_code(db, user)
    result, _ = _confirm(db, code)

    with pytest.raises(HTTPException) as refused:
        refresh_session_token(request, db=db)
    assert refused.value.status_code == 401
    # An expired token is dated the same way, so waiting it out does not help.
    expired = _legacy_token(user.id, datetime.utcnow() - timedelta(days=45))
    with pytest.raises(HTTPException):
        refresh_session_token(_RefreshSessionTokenRequest(email=EMAIL, current_token=expired), db=db)
    # The session the reset created renews normally.
    fresh = _RefreshSessionTokenRequest(email=EMAIL, current_token=result.session_token)
    assert refresh_session_token(fresh, db=db).session_token


def test_a_refresh_without_the_held_token_still_works(user, db: Session) -> None:
    # A website deployed before this change sends only the address.
    from app.api.routes.auth import _RefreshSessionTokenRequest, refresh_session_token

    code = password_reset.issue_code(db, user)
    _confirm(db, code)
    assert refresh_session_token(_RefreshSessionTokenRequest(email=EMAIL), db=db).session_token


# ── Changing the password while signed in ─────────────────────────────────────

def _change(db: Session, user, current: str = OLD, new: str = NEW, breaches=0):
    from app.api.routes.auth import change_password
    from app.schemas.identity import PasswordChangeRequest

    tasks = BackgroundTasks()
    with patch("app.api.routes.auth.breach_count", return_value=breaches):
        result = change_password(
            PasswordChangeRequest(current_password=current, new_password=new), tasks, user=user, db=db,
        )
    return result, tasks


def test_the_current_password_and_a_new_one_change_it(user, db: Session) -> None:
    with patch("app.services.auth_service.datetime") as clock:
        clock.utcnow.return_value = datetime.utcnow() - timedelta(hours=1)
        elsewhere = create_session_token(user.id, "scout")

    result, tasks = _change(db, user)

    db.refresh(user)
    assert verify_password(NEW, user.password_hash)
    assert not verify_password(OLD, user.password_hash)
    # Every other device is signed out...
    with pytest.raises(HTTPException):
        get_current_user(_request(elsewhere), db=db)
    # ...and this one carries on with the token in the reply.
    assert get_current_user(_request(result.session_token), db=db).id == user.id
    # The "your password was changed" notice is queued.
    assert len(tasks.tasks) == 1


def test_being_signed_in_is_not_enough_to_change_it(user, db: Session) -> None:
    result, tasks = _change(db, user, current="not-the-password")
    assert _rejection(result)["code"] == "wrong_password"
    db.refresh(user)
    assert verify_password(OLD, user.password_hash)
    assert user.password_changed_at is None
    assert tasks.tasks == []


def test_the_new_password_must_be_new_strong_and_unbreached(user, db: Session) -> None:
    same, _ = _change(db, user, new=OLD)
    assert _rejection(same)["code"] == "same_password"

    weak, _ = _change(db, user, new="short")
    body = _rejection(weak)
    assert body["code"] == "weak_password" and "length" in body["failed"]
    breached, _ = _change(db, user, breaches=40)
    assert _rejection(breached)["code"] == "breached_password"
    db.refresh(user)
    assert verify_password(OLD, user.password_hash)


def test_the_accounts_own_address_counts_against_the_new_password(make_user, db: Session) -> None:
    jordan = make_user(email="jordan@example.com", password=OLD)
    result, _ = _change(db, jordan, new="jordan-Tapgo4-zimqyr")
    assert _rejection(result)["failed"] == ["personal"]


def test_an_account_with_no_password_is_sent_to_the_reset(make_user, db: Session) -> None:
    """A Google-only account has no password to confirm. Letting a signed-in
    session set one would let a stolen session add its own way in."""
    google = make_user(email="g@example.com", oauth_provider="google", oauth_subject="sub-1")
    result, _ = _change(db, google, current="")
    assert _rejection(result)["code"] == "no_password"
    db.refresh(google)
    assert google.password_hash is None


def test_changing_the_password_closes_a_reset_code_already_sent(user, db: Session) -> None:
    code = password_reset.issue_code(db, user)
    _change(db, user)
    # The emailed code could otherwise undo the change for fifteen minutes.
    result, _ = _confirm(db, code, password="Other-Meadow4-finch")
    assert _rejection(result)["code"] == "invalid_code"

