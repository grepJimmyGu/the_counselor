"""The rules a new password must pass, and the sign-up route that enforces them."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.orm import Session

from app.api.routes.auth import _get_user_by_email, password_signup
from app.schemas.identity import SignupRequest
from app.services import password_policy, pwned_passwords
from app.services.auth_service import verify_google_id_token

# Passes every rule. Shaped like the password an iPhone proposes.
GOOD = "nuvmyz-Tapgo4-zimqyr"


# ── The rules ─────────────────────────────────────────────────────────────────

def test_a_strong_password_breaks_no_rule() -> None:
    assert password_policy.violations(GOOD, "jordan@example.com", "Jordan Lee") == []


@pytest.mark.parametrize(
    "password, rule",
    [
        ("Short1!aB", "length"),
        ("aB1!" + "xy" * 31, "length"),         # 66 characters
        ("NUVMYZ-TAPGO4-ZIMQYR", "lowercase"),
        ("nuvmyz-tapgo4-zimqyr", "uppercase"),
        ("nuvmyz-Tapgoh-zimqyr", "number"),
        ("nuvmyzTapgo4zimqyr", "symbol"),
        ("nuvmyz-Taaago4-zimq", "repeat"),
        ("nuvmyz-Tapgo-1234-z", "sequence"),
        ("nuvmyz-Tdcba4-zimqyr", "sequence"),   # downwards counts too
        ("nuvmyz-TaWXyZ4-zimq", "sequence"),    # and case does not hide it
        ("My-Livermore-4-ever", "personal"),
        ("jordan-Tapgo4-zimqyr", "personal"),   # the email's name
        ("nuvmyz-Tapgo4-Marsh!", "personal"),   # one part of a dotted handle
        ("nuvmyz-Tapgo4-Smith!", "personal"),   # the display name
    ],
)
def test_each_rule_is_reported_by_its_code(password: str, rule: str) -> None:
    email = "kim.marsh@example.com" if "Marsh" in password else "jordan@example.com"
    failed = password_policy.violations(password, email, "Sam Smith")
    assert failed == [rule]


def test_a_space_is_allowed_but_is_not_the_symbol() -> None:
    assert password_policy.violations("nuvmyz Tapgo4 zimqyr") == ["symbol"]
    assert password_policy.violations("nuvmyz Tapgo4-zimqyr") == []


def test_a_password_bcrypt_would_cut_short_is_refused() -> None:
    # 42 characters, inside the limit, but 78 bytes: bcrypt stops at 72 and
    # the last characters would not count towards the password at all.
    password = "aB1!" + "é" * 36 + "xy"
    assert len(password) <= password_policy.MAX_LENGTH
    assert len(password.encode("utf-8")) > password_policy.MAX_BYTES
    assert "length" in password_policy.violations(password)


def test_a_short_name_or_handle_is_not_held_against_the_password() -> None:
    # "al" and "bo" are inside ordinary words; only four letters or more count.
    assert password_policy.violations("global-Tabor4-zimqyr", "al@example.com", "Bo") == []


def test_two_in_a_row_and_three_in_a_run_are_fine() -> None:
    assert password_policy.violations("nuvmmz-Tapgo4-123-abc!") == []


def test_every_rule_has_a_message() -> None:
    weak = password_policy.violations("aaaa", "aaaa@example.com")
    for code in weak + ["sequence", "personal", "repeat"]:
        assert password_policy.MESSAGES[code]


# ── The breach lookup ─────────────────────────────────────────────────────────

def _range_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status.return_value = None
    return response


def test_breach_lookup_sends_only_a_hash_prefix() -> None:
    # SHA-1("password") = 5BAA6 1E4C9B93F3F0682250B6CF8331B7EE68FD8
    body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n1E4C9B93F3F0682250B6CF8331B7EE68FD8:52256179\r\n"
    with patch.object(pwned_passwords.httpx, "get", return_value=_range_response(body)) as get:
        assert pwned_passwords.breach_count("password") == 52256179
    url = get.call_args.args[0]
    assert url == "https://api.pwnedpasswords.com/range/5BAA6"
    assert get.call_args.kwargs["headers"] == {"Add-Padding": "true"}


def test_breach_lookup_counts_an_unlisted_password_as_zero() -> None:
    # Padding rows come back with a count of 0 and must not read as a match.
    body = "0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n1E4C9B93F3F0682250B6CF8331B7EE68FD8:0\r\n"
    with patch.object(pwned_passwords.httpx, "get", return_value=_range_response(body)):
        assert pwned_passwords.breach_count("password") == 0
        assert pwned_passwords.breach_count(GOOD) == 0


def test_breach_lookup_is_unknown_when_the_service_is_down() -> None:
    with patch.object(pwned_passwords.httpx, "get", side_effect=httpx.ConnectTimeout("slow")):
        assert pwned_passwords.breach_count(GOOD) is None


# ── The sign-up route ─────────────────────────────────────────────────────────

def _request() -> MagicMock:
    request = MagicMock()
    request.cookies = {}
    return request


def _sign_up(db: Session, password: str, email: str = "new@example.com", breaches=0):
    with patch("app.api.routes.auth.breach_count", return_value=breaches), \
         patch("app.api.routes.auth._try_send_welcome_email"):
        return password_signup(SignupRequest(email=email, password=password), request=_request(), db=db)


def test_sign_up_with_a_strong_password_creates_the_account(db: Session) -> None:
    result = _sign_up(db, GOOD)
    assert result.session_token
    assert _get_user_by_email(db, "new@example.com") is not None


def test_sign_up_refuses_a_weak_password_and_says_why(db: Session) -> None:
    result = _sign_up(db, "password")
    assert result.status_code == 400
    body = json.loads(result.body)
    assert body["code"] == "weak_password"
    assert body["failed"] == ["length", "uppercase", "number", "symbol"]
    assert "Add an uppercase letter." in body["detail"]
    assert _get_user_by_email(db, "new@example.com") is None


def test_sign_up_refuses_a_breached_password(db: Session) -> None:
    result = _sign_up(db, GOOD, breaches=12)
    assert result.status_code == 400
    assert json.loads(result.body)["code"] == "breached_password"
    assert _get_user_by_email(db, "new@example.com") is None


def test_sign_up_goes_ahead_when_the_breach_lookup_is_down(db: Session) -> None:
    result = _sign_up(db, GOOD, breaches=None)
    assert result.session_token


def test_an_existing_account_can_still_sign_in_with_an_old_short_password(make_user, db: Session) -> None:
    # The rules apply to new passwords. Nobody is locked out by them.
    from app.api.routes.auth import password_login
    from app.schemas.identity import LoginRequest

    make_user(email="old@example.com", password="pw123")
    assert password_login(LoginRequest(email="old@example.com", password="pw123"), db=db).session_token


# ── Google ID tokens ──────────────────────────────────────────────────────────

def _settings(web: str = "", ios: str = "") -> MagicMock:
    settings = MagicMock()
    settings.google_client_id = web
    settings.google_ios_client_id = ios
    return settings


def test_a_google_token_is_checked_against_the_web_and_ios_clients() -> None:
    with patch("app.services.auth_service.get_settings", return_value=_settings("web-id", "ios-id")), \
         patch("google.oauth2.id_token.verify_oauth2_token", return_value={"sub": "1"}) as verify:
        assert verify_google_id_token("token") == {"sub": "1"}
    assert verify.call_args.args[2] == ["web-id", "ios-id"]


def test_a_google_token_is_refused_when_no_client_id_is_configured() -> None:
    """With an empty audience google-auth skips the audience check, so a token
    minted for any other app would have signed its holder in here."""
    with patch("app.services.auth_service.get_settings", return_value=_settings()), \
         patch("google.oauth2.id_token.verify_oauth2_token", return_value={"sub": "1"}) as verify:
        with pytest.raises(ValueError, match="not configured"):
            verify_google_id_token("token")
    verify.assert_not_called()
