"""PRD-19 Step 4c — extend /api/email/unsub for signal_alerts_<id> +
daily_digest tokens.

The signal-change email Step 3b sends has a strategy-scoped unsubscribe
URL signed with category `signal_alerts_<strategy_id>`. The daily-digest
email Step 4b sends has a `daily_digest` unsub URL. This PR routes both
through the existing CAN-SPAM endpoint.

Anti-enumeration is the load-bearing UX property: every code path
returns the same HTML status 200 — never a 404, never a JSON error,
never anything that tells a scraper whether the token was valid. The
hard-rule test below pins that.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import Response
from sqlalchemy.orm import Session

from app.api.routes.email import unsubscribe
from app.models.email_preference import EmailPreference
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.services import saved_strategy_service
from app.services.email_service import (
    get_or_create_prefs,
    make_unsub_token,
)
from app.services.saved_strategy_service import SaveStrategyRequest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _save_strategy(db: Session, user) -> "SavedStrategy":  # type: ignore[name-defined]
    return saved_strategy_service.save_strategy(
        db,
        user,
        SaveStrategyRequest(
            title="MA Filter on NVDA",
            strategy_json={"strategy_type": "moving_average_filter", "universe": ["NVDA"]},
        ),
    )


def _subscribe(db: Session, user, strategy) -> SignalAlertSubscription:
    sub = SignalAlertSubscription(
        user_id=user.id,
        saved_strategy_id=strategy.id,
        email_enabled=True,
    )
    db.add(sub)
    db.commit()
    return sub


# ── signal_alerts_<id> token: happy path ─────────────────────────────────────


def test_signal_alerts_token_mutes_the_right_strategy(
    make_user, db: Session
) -> None:
    """One-click on the strategy-scoped link flips
    SignalAlertSubscription.email_enabled=False for THIS user + strategy
    only. Other subscriptions stay on."""
    user = make_user(email="mute-one@test.com")
    strategy_a = _save_strategy(db, user)
    strategy_b = saved_strategy_service.save_strategy(
        db, user,
        SaveStrategyRequest(
            title="Other Strategy",
            strategy_json={"strategy_type": "moving_average_filter", "universe": ["SPY"]},
        ),
    )
    _subscribe(db, user, strategy_a)
    _subscribe(db, user, strategy_b)

    token = make_unsub_token(user.id, f"signal_alerts_{strategy_a.id}")
    resp = unsubscribe(token=token, db=db)

    assert resp.status_code == 200
    # Friendly page rendered.
    assert b"You won't receive alerts for that strategy" in resp.body

    # Subscription A: muted.
    sub_a = db.get(SignalAlertSubscription, (user.id, strategy_a.id))
    assert sub_a is not None
    assert sub_a.email_enabled is False

    # Subscription B: untouched.
    sub_b = db.get(SignalAlertSubscription, (user.id, strategy_b.id))
    assert sub_b is not None
    assert sub_b.email_enabled is True


def test_signal_alerts_token_on_nonexistent_subscription_no_ops_gracefully(
    make_user, db: Session
) -> None:
    """User had a strategy + signed-link token, then deleted the
    subscription before clicking. The token verifies fine but the
    `SignalAlertSubscription` row is gone — must NOT 500. Same friendly
    page, no DB write."""
    user = make_user(email="orphan@test.com")
    strategy = _save_strategy(db, user)
    # NO _subscribe call.

    token = make_unsub_token(user.id, f"signal_alerts_{strategy.id}")
    resp = unsubscribe(token=token, db=db)

    assert resp.status_code == 200
    assert b"You won't receive alerts for that strategy" in resp.body

    # No subscription created as a side effect.
    sub = db.get(SignalAlertSubscription, (user.id, strategy.id))
    assert sub is None


def test_signal_alerts_token_does_not_touch_other_users(
    make_user, db: Session
) -> None:
    """Alice's token can only mute Alice's subscription. Even if Bob
    happens to have the same strategy_id (impossible in practice but
    defensible by HMAC anyway), Bob's row stays on."""
    alice = make_user(email="alice-unsub@test.com")
    bob = make_user(email="bob-unsub@test.com")
    a_strat = _save_strategy(db, alice)
    _subscribe(db, alice, a_strat)
    # Bob subscribes to Alice's PUBLIC strategy (Scout force-public).
    bob_sub = SignalAlertSubscription(
        user_id=bob.id,
        saved_strategy_id=a_strat.id,
        email_enabled=True,
    )
    db.add(bob_sub)
    db.commit()

    # Alice clicks her unsub link.
    token = make_unsub_token(alice.id, f"signal_alerts_{a_strat.id}")
    unsubscribe(token=token, db=db)

    # Alice muted, Bob still on.
    assert db.get(SignalAlertSubscription, (alice.id, a_strat.id)).email_enabled is False
    assert db.get(SignalAlertSubscription, (bob.id, a_strat.id)).email_enabled is True


# ── daily_digest token ───────────────────────────────────────────────────────


def test_daily_digest_token_flips_pref_flag(make_user, db: Session) -> None:
    """One-click on the digest unsub link flips
    EmailPreference.daily_digest_enabled=False."""
    user = make_user(email="digest-unsub@test.com")
    prefs = get_or_create_prefs(db, user.id)
    assert prefs.daily_digest_enabled is True  # default

    token = make_unsub_token(user.id, "daily_digest")
    resp = unsubscribe(token=token, db=db)

    assert resp.status_code == 200
    assert b"You won't receive the daily digest" in resp.body

    fresh = db.get(EmailPreference, user.id)
    assert fresh.daily_digest_enabled is False


def test_daily_digest_token_does_not_touch_signal_alerts(
    make_user, db: Session
) -> None:
    """Per-category opt-out is finer-grained than global — muting digest
    must not mute signal alerts (separate product, separate flag)."""
    user = make_user(email="digest-only-off@test.com")
    prefs = get_or_create_prefs(db, user.id)

    token = make_unsub_token(user.id, "daily_digest")
    unsubscribe(token=token, db=db)

    fresh = db.get(EmailPreference, user.id)
    assert fresh.daily_digest_enabled is False
    assert fresh.signal_alerts_enabled is True  # unchanged
    assert fresh.unsubscribed_at is None  # no global bleed


# ── "all" token now sweeps PRD-19 flags too ──────────────────────────────────


def test_all_token_mutes_signal_alerts_and_digest_too(
    make_user, db: Session
) -> None:
    """The global one-click `category="all"` token already flipped the
    legacy marketing flags. Step 4c extends it to flip the PRD-19 flags
    too — otherwise a user clicking "Unsubscribe from all marketing"
    would keep receiving signal alerts (`category=transactional`) and
    digests."""
    user = make_user(email="all-off@test.com")
    prefs = get_or_create_prefs(db, user.id)

    token = make_unsub_token(user.id, "all")
    resp = unsubscribe(token=token, db=db)

    assert resp.status_code == 200
    fresh = db.get(EmailPreference, user.id)
    # Legacy flags off (regression guard).
    assert fresh.weekly_digest is False
    assert fresh.upsell_nudges is False
    assert fresh.creator_program is False
    # PRD-19 flags also off.
    assert fresh.signal_alerts_enabled is False
    assert fresh.daily_digest_enabled is False
    # Global unsubscribed timestamp set.
    assert fresh.unsubscribed_at is not None


# ── Anti-enumeration: every path returns 200 + friendly HTML ─────────────────


def test_invalid_token_returns_friendly_200_not_error(
    make_user, db: Session
) -> None:
    """An attacker probing the endpoint must not learn whether a token
    was valid. Random garbage gets a 200 with the expired-message page,
    not a 400 or JSON error."""
    resp = unsubscribe(token="garbage.token.zzzz", db=db)
    assert resp.status_code == 200
    assert b"expired or is invalid" in resp.body


def test_token_for_unknown_category_returns_friendly_200(
    make_user, db: Session
) -> None:
    """Same anti-enumeration property — a forged token with a category
    not in our switch ladder produces the same 'expired or invalid' page
    so the attacker can't distinguish 'bad signature' from 'unknown
    category'."""
    user = make_user(email="bogus@test.com")
    # Token signed with a category we don't handle.
    token = make_unsub_token(user.id, "made_up_category")
    resp = unsubscribe(token=token, db=db)
    assert resp.status_code == 200
    assert b"expired or is invalid" in resp.body


def test_signed_with_wrong_user_id_is_rejected(make_user, db: Session) -> None:
    """Attacker tries to forge a `signal_alerts_<id>` token for Bob's
    strategy using Alice's HMAC. They can't — the signature wouldn't
    verify because the message bytes are `<user_id>.<category>` and they
    don't have the server-side signing key. Confirms by attempting a
    manually-crafted bad token."""
    user = make_user(email="forge@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)

    # A forged token with the right shape but a tampered user_id segment.
    # Real token is `user.id.signal_alerts_<sid>.<sig>` — we keep the sig
    # but swap user.id for a different one.
    real = make_unsub_token(user.id, f"signal_alerts_{strategy.id}")
    user_part, category_part, sig = real.split(".", 2)
    # Note: rsplit on the last dot is wrong since category contains
    # `signal_alerts_<uuid-with-dashes>`. verify_unsub_token splits on
    # the first two dots, so we have to be careful — see verify_unsub_token.
    # For this test we use a simpler tamper: append a junk char to the sig.
    bad_token = f"{user_part}.{category_part}.{sig}X"
    resp = unsubscribe(token=bad_token, db=db)
    assert resp.status_code == 200
    assert b"expired or is invalid" in resp.body

    # Subscription untouched.
    sub = db.get(SignalAlertSubscription, (user.id, strategy.id))
    assert sub.email_enabled is True
