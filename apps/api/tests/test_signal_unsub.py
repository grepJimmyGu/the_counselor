"""Stage 8 v0 Phase B — signal-alert unsubscribe (token + endpoint).

Covers spec §10 acceptance #7 ("Unsubscribe via email link"): single-strategy
unsub deletes only that subscription, all-signals unsub deletes every signal
subscription for the user, neither touches another user's subscriptions.

Anti-enumeration matches the existing `/api/email/unsub` posture — invalid
tokens get a friendly 200 HTML page, not a 4xx that reveals validity.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.api.routes.email import signal_unsubscribe
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.services.email_service import (
    make_signal_unsub_token,
    verify_signal_unsub_token,
)


# ── Token round-trip ────────────────────────────────────────────────────────


def test_signal_unsub_token_round_trip_single() -> None:
    token = make_signal_unsub_token("user-123", "strategy-abc", scope="single")
    parsed = verify_signal_unsub_token(token)
    assert parsed == ("user-123", "single", "strategy-abc")


def test_signal_unsub_token_round_trip_all() -> None:
    """All-scope tokens omit the strategy id (encoded as `-` internally)."""
    token = make_signal_unsub_token("user-123", None, scope="all")
    parsed = verify_signal_unsub_token(token)
    assert parsed == ("user-123", "all", None)


def test_signal_unsub_token_rejects_tampered_signature() -> None:
    """Modify the last char of the HMAC → must reject."""
    token = make_signal_unsub_token("user-123", "strategy-abc", scope="single")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert verify_signal_unsub_token(tampered) is None


def test_signal_unsub_token_rejects_wrong_part_count() -> None:
    """Whole class of malformed tokens — under 4 parts, or extra junk appended."""
    assert verify_signal_unsub_token("only.three.parts") is None
    assert verify_signal_unsub_token("one") is None
    assert verify_signal_unsub_token("a.b.c.d.e") is None


# ── Endpoint behavior (handler called directly, matching Phase A style) ────


def _make_sub(db: Session, user_id: str, saved_strategy_id: str) -> None:
    """Insert a SignalAlertSubscription row without going through the routes."""
    db.add(SignalAlertSubscription(
        user_id=user_id,
        saved_strategy_id=saved_strategy_id,
        email_enabled=True,
    ))
    db.commit()


def test_signal_unsub_endpoint_deletes_only_target_subscription(db: Session, make_user) -> None:
    """Spec §10 #7 — single-strategy scope removes one row, leaves the other."""
    user = make_user()
    strategy_a = str(uuid.uuid4())
    strategy_b = str(uuid.uuid4())
    _make_sub(db, user.id, strategy_a)
    _make_sub(db, user.id, strategy_b)
    assert db.query(SignalAlertSubscription).count() == 2

    token = make_signal_unsub_token(user.id, strategy_a, scope="single")
    response = signal_unsubscribe(token=token, db=db)

    assert response.status_code == 200
    remaining = db.query(SignalAlertSubscription).all()
    assert len(remaining) == 1
    assert remaining[0].saved_strategy_id == strategy_b


def test_signal_unsub_endpoint_deletes_all_subscriptions_for_user(
    db: Session, make_user
) -> None:
    """Spec §10 #7 — all-scope removes every row for the user, leaves siblings."""
    user_a = make_user(email="user-a@example.com")
    user_b = make_user(email="user-b@example.com")
    _make_sub(db, user_a.id, str(uuid.uuid4()))
    _make_sub(db, user_a.id, str(uuid.uuid4()))
    _make_sub(db, user_b.id, str(uuid.uuid4()))
    assert db.query(SignalAlertSubscription).count() == 3

    token = make_signal_unsub_token(user_a.id, None, scope="all")
    response = signal_unsubscribe(token=token, db=db)

    assert response.status_code == 200
    remaining = db.query(SignalAlertSubscription).all()
    assert len(remaining) == 1
    assert remaining[0].user_id == user_b.id


def test_signal_unsub_endpoint_returns_friendly_html_for_invalid_token(
    db: Session, make_user
) -> None:
    """Anti-enumeration — same 200 HTML response for invalid tokens as for valid
    ones. Never reveal whether a (user_id, strategy_id) pair exists."""
    user = make_user()
    _make_sub(db, user.id, str(uuid.uuid4()))

    response = signal_unsubscribe(token="bogus.token.here.extra", db=db)

    assert response.status_code == 200
    assert b"expired or is invalid" in response.body
    # Subscription untouched.
    assert db.query(SignalAlertSubscription).count() == 1
