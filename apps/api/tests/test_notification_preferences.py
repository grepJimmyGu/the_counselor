"""PRD-19 Step 4a — extension of /api/me/email-preferences with the three
notification flags + _prefs_allow gate.

Tests:
  - GET returns the new fields with the documented defaults
  - PATCH partial update touches only the named fields
  - signal_alerts_enabled=False → _prefs_allow rejects "signal_change"
    even though the template is `category="transactional"`
  - daily_digest_enabled=False → _prefs_allow rejects "daily_digest"
  - PATCH that flips a PRD-19 flag back ON clears unsubscribed_at
  - Defaults: signal_alerts_enabled=True, daily_digest_enabled=True,
    silent_days_enabled=False
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.api.routes.email import (
    EmailPreferenceUpdate,
    get_email_preferences,
    update_email_preferences,
)
from app.models.email_preference import EmailPreference
from app.services.email_service import (
    _prefs_allow,
    get_or_create_prefs,
)


# ── Defaults ─────────────────────────────────────────────────────────────────


def test_new_user_gets_signal_alerts_enabled_true_by_default(
    make_user, db: Session
) -> None:
    """Existing subscribers must keep getting alerts post-migration. The
    `default=True` server default on the column + the Python-side default
    on `mapped_column` both guarantee this."""
    user = make_user(email="defaults@test.com")
    resp = get_email_preferences(current_user=user, db=db)
    assert resp.signal_alerts_enabled is True
    assert resp.daily_digest_enabled is True
    # Silent-days defaults FALSE so existing digest subscribers don't
    # suddenly stop receiving digests on no-news days.
    assert resp.silent_days_enabled is False


# ── PATCH partial-update semantics ───────────────────────────────────────────


def test_patch_signal_alerts_disabled_only_touches_that_flag(
    make_user, db: Session
) -> None:
    user = make_user(email="patch-one@test.com")
    resp = update_email_preferences(
        EmailPreferenceUpdate(signal_alerts_enabled=False),
        current_user=user,
        db=db,
    )
    assert resp.signal_alerts_enabled is False
    assert resp.daily_digest_enabled is True  # unchanged
    assert resp.silent_days_enabled is False  # unchanged
    # Legacy marketing flags also unchanged.
    assert resp.weekly_digest is True
    assert resp.upsell_nudges is True


def test_patch_silent_days_enabled_true_persists(make_user, db: Session) -> None:
    user = make_user(email="silent@test.com")
    resp = update_email_preferences(
        EmailPreferenceUpdate(silent_days_enabled=True),
        current_user=user,
        db=db,
    )
    assert resp.silent_days_enabled is True

    # Re-read via GET to confirm persistence.
    fresh = get_email_preferences(current_user=user, db=db)
    assert fresh.silent_days_enabled is True


def test_patch_multiple_flags_in_one_call(make_user, db: Session) -> None:
    user = make_user(email="multi@test.com")
    resp = update_email_preferences(
        EmailPreferenceUpdate(
            signal_alerts_enabled=False,
            daily_digest_enabled=False,
            silent_days_enabled=True,
        ),
        current_user=user,
        db=db,
    )
    assert resp.signal_alerts_enabled is False
    assert resp.daily_digest_enabled is False
    assert resp.silent_days_enabled is True


def test_patch_signal_alerts_re_enable_clears_global_unsub(
    make_user, db: Session
) -> None:
    """If the user had globally unsubscribed and then re-enables signal
    alerts, the global unsub should clear — they want email again."""
    user = make_user(email="re-enable@test.com")
    prefs = get_or_create_prefs(db, user.id)
    # Simulate a prior global unsub.
    prefs.unsubscribed_at = datetime.utcnow()
    prefs.signal_alerts_enabled = False
    db.commit()

    resp = update_email_preferences(
        EmailPreferenceUpdate(signal_alerts_enabled=True),
        current_user=user,
        db=db,
    )
    assert resp.signal_alerts_enabled is True
    assert resp.unsubscribed_at is None


def test_patch_signal_alerts_disable_does_NOT_set_unsubscribed_at(
    make_user, db: Session
) -> None:
    """Per-template disable is finer-grained than the global unsub — flipping
    one off must not set `unsubscribed_at`, which would silently disable
    legacy marketing too."""
    user = make_user(email="no-bleed@test.com")
    resp = update_email_preferences(
        EmailPreferenceUpdate(signal_alerts_enabled=False),
        current_user=user,
        db=db,
    )
    assert resp.unsubscribed_at is None


# ── _prefs_allow gate ────────────────────────────────────────────────────────


def test_prefs_allow_blocks_signal_change_when_disabled(
    make_user, db: Session
) -> None:
    """`signal_change` is `category="transactional"`. Pre-PRD-19, the
    transactional default would override prefs and send. Step 4a's
    extension makes `signal_alerts_enabled=False` win even for the
    transactional template — explicit opt-out is honored."""
    user = make_user(email="prefs-block@test.com")
    prefs = get_or_create_prefs(db, user.id)
    prefs.signal_alerts_enabled = False
    db.commit()

    assert _prefs_allow(prefs, template="signal_change", category="transactional") is False


def test_prefs_allow_sends_signal_change_when_enabled(
    make_user, db: Session
) -> None:
    user = make_user(email="prefs-send@test.com")
    prefs = get_or_create_prefs(db, user.id)
    # Default True — should send.
    assert _prefs_allow(prefs, template="signal_change", category="transactional") is True


def test_prefs_allow_blocks_daily_digest_when_disabled(
    make_user, db: Session
) -> None:
    user = make_user(email="digest-block@test.com")
    prefs = get_or_create_prefs(db, user.id)
    prefs.daily_digest_enabled = False
    db.commit()

    assert _prefs_allow(prefs, template="daily_digest", category="marketing") is False


def test_prefs_allow_legally_required_transactional_still_sends(
    make_user, db: Session
) -> None:
    """Password reset / payment failed (template names like `password_reset`,
    `payment_failed`) are CAN-SPAM transactional and bypass even global
    `unsubscribed_at` — they must continue to bypass the new PRD-19 flags
    too, because those flags scope to signal_change / daily_digest only."""
    user = make_user(email="txn@test.com")
    prefs = get_or_create_prefs(db, user.id)
    prefs.signal_alerts_enabled = False
    prefs.daily_digest_enabled = False
    prefs.unsubscribed_at = datetime.utcnow()
    db.commit()

    # Some arbitrary transactional template that PRD-19 doesn't scope.
    assert _prefs_allow(prefs, template="password_reset", category="transactional") is True


def test_prefs_allow_global_unsub_still_blocks_marketing(
    make_user, db: Session
) -> None:
    """Regression guard: the legacy `unsubscribed_at` global-marketing
    block must still work. PRD-19's new flags are additive — they don't
    replace the legacy CAN-SPAM machinery."""
    user = make_user(email="legacy-unsub@test.com")
    prefs = get_or_create_prefs(db, user.id)
    prefs.unsubscribed_at = datetime.utcnow()
    db.commit()

    assert _prefs_allow(prefs, template="weekly_digest", category="marketing") is False


# ── PostHog capture ──────────────────────────────────────────────────────────


def test_patch_captures_posthog_with_new_flag_values(
    make_user, db: Session, monkeypatch
) -> None:
    """The existing analytics event includes the new PRD-19 flags in its
    properties payload so the dashboard can see opt-out trends."""
    captured = []

    def fake_capture(user_id, event, properties):
        captured.append({"user_id": user_id, "event": event, "properties": properties})

    import app.services.posthog_service as ph_mod
    monkeypatch.setattr(ph_mod, "capture", fake_capture)

    user = make_user(email="posthog@test.com")
    update_email_preferences(
        EmailPreferenceUpdate(signal_alerts_enabled=False, silent_days_enabled=True),
        current_user=user,
        db=db,
    )

    assert len(captured) == 1
    props = captured[0]["properties"]
    assert props["signal_alerts_enabled"] is False
    assert props["daily_digest_enabled"] is True
    assert props["silent_days_enabled"] is True
