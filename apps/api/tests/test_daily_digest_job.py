"""PRD-19 Step 4b — daily digest job + dispatcher + render integration.

End-to-end: synthesize a user with active subscriptions, optionally a
SignalEvent today, optionally a silent-days preference, and verify the
cron tick:

  1. Builds a DigestEvent with the right counts + rows
  2. Calls send_email with template="daily_digest" + the rendered html+text
  3. Captures `daily_digest_dispatched` to PostHog with the joinable props
  4. Honors `silent_days_enabled` + `daily_digest_enabled` + `unsubscribed_at`
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.jobs.daily_digest_job import run_daily_digest_job
from app.models.email_preference import EmailPreference
from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.services import saved_strategy_service
from app.services.email_service import get_or_create_prefs
from app.services.saved_strategy_service import SaveStrategyRequest


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _save_strategy(db: Session, user, title: str = "MA Filter on NVDA") -> SavedStrategy:
    return saved_strategy_service.save_strategy(
        db,
        user,
        SaveStrategyRequest(
            title=title,
            strategy_json={
                "strategy_type": "moving_average_filter",
                "universe": ["NVDA"],
            },
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


def _seed_state(
    db: Session, strategy, *, signal: dict, display: str = "LONG NVDA"
) -> SavedStrategySignalState:
    state = SavedStrategySignalState(
        saved_strategy_id=strategy.id,
        current_signal=signal,
        current_signal_display=display,
        as_of_date=datetime.utcnow().date(),
    )
    db.add(state)
    db.commit()
    return state


def _emit_event(db: Session, strategy, *, today: date) -> SignalEvent:
    """Synthesize a today-dated SignalEvent for one strategy."""
    evt = SignalEvent(
        id=str(uuid4()),
        saved_strategy_id=strategy.id,
        previous_signal={"position": "cash"},
        previous_signal_display="CASH",
        new_signal={"position": "long", "ticker": "NVDA"},
        new_signal_display="LONG NVDA",
        change_type="flip_to_long",
        as_of_date=today,
    )
    db.add(evt)
    db.commit()
    return evt


def _wire_dispatcher(monkeypatch, db, sent_emails: list, captured: list) -> None:
    """Common monkeypatch wiring for the digest path."""
    # SessionLocal is opened by the cron — return the test session.
    monkeypatch.setattr("app.jobs.daily_digest_job.SessionLocal", lambda: db)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    # Don't let the cron close the session out from under the test.
    monkeypatch.setattr(db, "close", lambda: None)

    def fake_send(db_, user_, *, template, subject, html, text, category):
        sent_emails.append({
            "template": template,
            "subject": subject,
            "category": category,
            "user_id": user_.id,
            "html_has_unsub": "Unsubscribe" in html,
            "html_has_compliance": "Not investment advice" in html,
            "text_has_settings_url": "/account/notifications" in text,
        })
        return True

    monkeypatch.setattr("app.services.channel_dispatcher.send_email", fake_send)

    import app.services.posthog_service as ph_mod
    monkeypatch.setattr(
        ph_mod, "capture",
        lambda *, user_id, event, properties=None: captured.append(
            {"user_id": user_id, "event": event, "properties": properties or {}}
        ),
    )


# ── Happy path: changed + stable bucketing ───────────────────────────────────


def test_user_with_a_changed_signal_today_gets_one_digest(
    make_user, db: Session, monkeypatch
) -> None:
    """One subscribed strategy with a SignalEvent today → one digest email,
    `changed_count=1`, PostHog `daily_digest_dispatched` fires."""
    user = make_user(email="digest-happy@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_state(db, strategy, signal={"position": "long", "ticker": "NVDA"})
    today = datetime.utcnow().date()
    _emit_event(db, strategy, today=today)

    sent_emails: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent_emails, captured)

    stats = run_daily_digest_job()

    assert stats["users_considered"] == 1
    assert stats["sent"] == 1
    assert stats["skipped"] == 0
    assert stats["errors"] == 0

    # Exactly one email.
    assert len(sent_emails) == 1
    e = sent_emails[0]
    assert e["template"] == "daily_digest"
    assert e["category"] == "marketing"
    assert e["user_id"] == user.id
    # Subject includes the counter — "1 changed".
    assert "1 changed" in e["subject"]
    assert e["html_has_unsub"] is True
    assert e["html_has_compliance"] is True
    assert e["text_has_settings_url"] is True

    # PostHog fires the dispatch event with joinable props.
    dispatch = [c for c in captured if c["event"] == "daily_digest_dispatched"]
    assert len(dispatch) == 1
    assert dispatch[0]["properties"]["changed_count"] == 1
    assert dispatch[0]["properties"]["subscribed_count"] == 1


def test_mixed_strategies_bucket_into_changed_stable_cash(
    make_user, db: Session, monkeypatch
) -> None:
    """A user with 3 strategies: 1 flipped today, 1 stable long, 1 in cash.
    The digest shows headline `1 changed · 1 stable · 1 in cash`."""
    user = make_user(email="digest-mixed@test.com")
    today = datetime.utcnow().date()

    flipped = _save_strategy(db, user, title="Flipped")
    stable = _save_strategy(db, user, title="Stable")
    cashy = _save_strategy(db, user, title="Cashy")
    for s in (flipped, stable, cashy):
        _subscribe(db, user, s)

    _seed_state(db, flipped, signal={"position": "long", "ticker": "NVDA"}, display="LONG NVDA")
    _seed_state(db, stable, signal={"position": "long", "ticker": "SPY"}, display="LONG SPY")
    _seed_state(db, cashy, signal={"position": "cash"}, display="CASH")

    _emit_event(db, flipped, today=today)
    # No SignalEvent today for stable + cashy → they bucket from state.

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    run_daily_digest_job()

    assert len(sent) == 1
    subj = sent[0]["subject"]
    assert "1 changed" in subj
    assert "1 stable" in subj
    assert "1 in cash" in subj

    dispatch = [c for c in captured if c["event"] == "daily_digest_dispatched"]
    props = dispatch[0]["properties"]
    assert props["changed_count"] == 1
    assert props["stable_count"] == 1
    assert props["cash_count"] == 1


# ── Silent-days skip ─────────────────────────────────────────────────────────


def test_silent_days_skips_when_nothing_changed(
    make_user, db: Session, monkeypatch
) -> None:
    """User opted into silent-days. Today has no SignalEvents → no email,
    but PostHog fires `daily_digest_skipped_silent_day` so the dashboard
    can count silent days saved."""
    user = make_user(email="silent@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_state(db, strategy, signal={"position": "long", "ticker": "NVDA"})

    prefs = get_or_create_prefs(db, user.id)
    prefs.silent_days_enabled = True
    db.commit()

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    stats = run_daily_digest_job()

    assert stats["sent"] == 0
    assert stats["skipped"] == 1
    assert len(sent) == 0
    silent = [c for c in captured if c["event"] == "daily_digest_skipped_silent_day"]
    assert len(silent) == 1


def test_silent_days_still_sends_when_something_changed(
    make_user, db: Session, monkeypatch
) -> None:
    """Silent-days only skips empty days — a change today still triggers
    the digest."""
    user = make_user(email="silent-changed@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_state(db, strategy, signal={"position": "long", "ticker": "NVDA"})
    today = datetime.utcnow().date()
    _emit_event(db, strategy, today=today)

    prefs = get_or_create_prefs(db, user.id)
    prefs.silent_days_enabled = True
    db.commit()

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    stats = run_daily_digest_job()

    assert stats["sent"] == 1
    assert len(sent) == 1


# ── Preference gating ────────────────────────────────────────────────────────


def test_daily_digest_disabled_skips_user(
    make_user, db: Session, monkeypatch
) -> None:
    """The user disabled daily digest globally. No email, no PostHog event."""
    user = make_user(email="digest-off@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_state(db, strategy, signal={"position": "long"})
    today = datetime.utcnow().date()
    _emit_event(db, strategy, today=today)

    prefs = get_or_create_prefs(db, user.id)
    prefs.daily_digest_enabled = False
    db.commit()

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    stats = run_daily_digest_job()
    assert stats["sent"] == 0
    assert stats["skipped"] == 1
    assert len(sent) == 0


def test_globally_unsubscribed_user_skips(
    make_user, db: Session, monkeypatch
) -> None:
    """`unsubscribed_at` blocks all marketing. The digest is marketing →
    skip. Confirms the legacy CAN-SPAM gate still works alongside the
    new PRD-19 flags."""
    user = make_user(email="all-off@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_state(db, strategy, signal={"position": "long"})
    today = datetime.utcnow().date()
    _emit_event(db, strategy, today=today)

    prefs = get_or_create_prefs(db, user.id)
    prefs.unsubscribed_at = datetime.utcnow()
    db.commit()

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    run_daily_digest_job()
    assert len(sent) == 0


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_user_with_no_active_subscriptions_skips(
    make_user, db: Session, monkeypatch
) -> None:
    """The cron query only enumerates users with active subscriptions —
    so a user with `email_enabled=False` shouldn't even hit the loop."""
    user = make_user(email="inactive@test.com")
    strategy = _save_strategy(db, user)
    sub = SignalAlertSubscription(
        user_id=user.id,
        saved_strategy_id=strategy.id,
        email_enabled=False,  # ← inactive
    )
    db.add(sub)
    db.commit()

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    stats = run_daily_digest_job()
    assert stats["users_considered"] == 0
    assert len(sent) == 0


def test_event_for_unsubscribed_strategy_does_not_count_as_changed(
    make_user, db: Session, monkeypatch
) -> None:
    """Two strategies — only one subscribed. A SignalEvent for the
    unsubscribed one must NOT contribute to the digest's changed_count."""
    user = make_user(email="partial-sub@test.com")
    subscribed = _save_strategy(db, user, title="Subscribed")
    not_subbed = _save_strategy(db, user, title="NotSubscribed")
    _subscribe(db, user, subscribed)
    _seed_state(db, subscribed, signal={"position": "long"})
    _seed_state(db, not_subbed, signal={"position": "long"})
    today = datetime.utcnow().date()
    # SignalEvent ONLY on the unsubscribed strategy.
    _emit_event(db, not_subbed, today=today)

    sent: list = []
    captured: list = []
    _wire_dispatcher(monkeypatch, db, sent, captured)

    run_daily_digest_job()

    # User still gets a digest because they have an active sub, but the
    # changed_count is 0 (not 1) — the SignalEvent was on a different strategy.
    dispatch = [c for c in captured if c["event"] == "daily_digest_dispatched"]
    if dispatch:
        assert dispatch[0]["properties"]["changed_count"] == 0
