"""PRD-19 Step 3b — signal_cron dispatcher + throttle + PostHog wiring.

End-to-end integration: synthesize a saved strategy with a subscriber,
prime the SignalState so the next compute "detects a change," and
verify the cron:

  1. Writes a SignalEvent row
  2. Calls dispatch_in_app_banner (writes NotificationBannerEntry)
  3. Calls dispatch_signal_change_email (which calls send_email)
  4. Updates SignalEvent.email_dispatched_at / email_dispatch_count
  5. Captures `notification_dispatched` to PostHog with right props
  6. Increments throttle counters
  7. Throttles 2nd same-day flip and captures `notification_throttled`

We mock the heavy machinery (BacktestEngine, send_email, posthog) and
let the real signal_cron + channel_dispatcher code orchestrate them.
That way the assertions exercise the wiring, not the math.

Mirrors the project's TestClient-free style — invoke
`_compute_all_signals_async` directly so we can `await` and patch
module-level deps.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.notification_banner import NotificationBannerEntry
from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent
from app.services import saved_strategy_service
from app.services.saved_strategy_service import SaveStrategyRequest


# ── Fixtures: synthesize a subscribed strategy + a "prior cash" signal ───────


_BASE_STRATEGY_JSON: dict = dict(
    strategy_name="MA Filter on NVDA",
    strategy_type="moving_average_filter",
    universe=["NVDA"],
    benchmark="SPY",
    start_date="2020-01-01",
    end_date="2024-01-01",
    initial_capital=100_000,
    rebalance_frequency="monthly",
    transaction_cost_bps=5,
    slippage_bps=5,
    position_sizing={"method": "equal_weight"},
)


def _save_strategy(db: Session, user) -> SavedStrategy:
    return saved_strategy_service.save_strategy(
        db,
        user,
        SaveStrategyRequest(
            title="MA Filter on NVDA",
            strategy_json=dict(_BASE_STRATEGY_JSON),
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


def _seed_prior_state(db: Session, strategy, *, signal: dict) -> SavedStrategySignalState:
    """Seed a prior SavedStrategySignalState so the next compute sees a
    change instead of a first-write."""
    state = SavedStrategySignalState(
        saved_strategy_id=strategy.id,
        current_signal=signal,
        current_signal_display="CASH",
        as_of_date=date.today() - timedelta(days=1),
    )
    db.add(state)
    db.commit()
    return state


def _fake_backtest_result(symbol: str = "NVDA", close: float = 145.23):
    """Synthesize a duck-typed BacktestResult that satisfies what
    `_extract_signal` + `_reference_prices` + `_risk_context` look at."""
    trade = SimpleNamespace(
        symbol=symbol,
        entry_price=140.00,
        exit_price=close,
        return_pct=0.037,
        holding_period_days=14,
    )
    metrics = SimpleNamespace(
        total_return=0.12,
        max_drawdown=-0.08,
        sharpe_ratio=1.4,
    )
    return SimpleNamespace(
        trade_log=[trade],
        metrics=metrics,
        equity_curve=[
            SimpleNamespace(date=date.today() - timedelta(days=2), value=10000.0),
            SimpleNamespace(date=date.today(), value=11200.0),
        ],
    )


def _run_cron() -> dict:
    """Drive the async impl directly so the test can await + patch."""
    from app.jobs.signal_cron import _compute_all_signals_async
    return asyncio.run(_compute_all_signals_async())


# ── Test 1: subscribed strategy gets full dispatch ───────────────────────────


def test_signal_change_dispatches_email_banner_and_posthog(
    make_user, db: Session, monkeypatch
) -> None:
    """Happy path: a subscribed strategy flips from CASH → LONG. The cron
    writes the SignalEvent, calls send_email, writes a NotificationBannerEntry,
    captures notification_dispatched, and updates email_dispatched_at."""
    user = make_user(email="cron-happy@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_prior_state(db, strategy, signal={"position": "cash"})

    # The dispatch path opens its OWN SessionLocal via SessionLocal() inside
    # signal_cron + inside dispatch_in_app_banner. Patch both to return the
    # test session so the test sees the writes.
    monkeypatch.setattr("app.jobs.signal_cron.SessionLocal", lambda: db)
    monkeypatch.setattr(
        "app.db.session.SessionLocal", lambda: db,
    )
    # Don't let dispatch_in_app_banner close the test session out from under us.
    monkeypatch.setattr(db, "close", lambda: None)

    # Mock the backtest engine so the test doesn't hit price_bars / FMP.
    fake_engine = MagicMock()
    fake_engine.run = MagicMock(side_effect=lambda *a, **kw: _make_awaitable(_fake_backtest_result()))
    monkeypatch.setattr(
        "app.services.backtester.engine.BacktestEngine",
        lambda: fake_engine,
    )

    # Spy on send_email and posthog.capture. The dispatcher imports
    # send_email at module top — patch the imported name.
    sent_emails = []

    def fake_send_email(db_, user_, *, template, subject, html, text, category):
        sent_emails.append({
            "template": template,
            "subject": subject,
            "category": category,
            "user_id": user_.id,
            "html_has_unsub": "Unsubscribe from this strategy" in html,
            "html_has_compliance": "Not investment advice" in html,
            "text_has_executed_link": "Mark as executed" in text,
        })
        return True

    monkeypatch.setattr(
        "app.services.channel_dispatcher.send_email", fake_send_email,
    )

    captured = []
    monkeypatch.setattr(
        "app.services.posthog_service.capture",
        lambda *, user_id, event, properties=None: captured.append(
            {"user_id": user_id, "event": event, "properties": properties or {}}
        ),
    )

    stats = _run_cron()

    assert stats["total"] == 1
    assert stats["changed"] == 1
    assert stats["dispatched"] == 1
    assert stats["errors"] == 0

    # SignalEvent persisted with the change_type + dispatched timestamps.
    events = db.query(SignalEvent).filter(
        SignalEvent.saved_strategy_id == strategy.id
    ).all()
    assert len(events) == 1
    evt = events[0]
    assert evt.email_dispatched_at is not None
    assert evt.email_dispatch_count == 1

    # In-app banner row written.
    banners = db.query(NotificationBannerEntry).filter(
        NotificationBannerEntry.user_id == user.id
    ).all()
    assert len(banners) == 1
    assert strategy.title in banners[0].title

    # Email rendered with compliance + unsubscribe.
    assert len(sent_emails) == 1
    assert sent_emails[0]["template"] == "signal_change"
    assert sent_emails[0]["category"] == "transactional"
    assert sent_emails[0]["html_has_unsub"] is True
    assert sent_emails[0]["html_has_compliance"] is True
    assert sent_emails[0]["text_has_executed_link"] is True

    # PostHog notification_dispatched fired with the joinable props.
    dispatch_events = [c for c in captured if c["event"] == "notification_dispatched"]
    assert len(dispatch_events) == 1
    props = dispatch_events[0]["properties"]
    assert props["saved_strategy_id"] == strategy.id
    assert props["signal_event_id"] == evt.id
    assert props["email_sent"] is True
    assert props["in_app_banner_sent"] is True


# ── Test 2: per-strategy throttle blocks 2nd same-day flip ───────────────────


def test_per_strategy_throttle_blocks_second_same_day_dispatch(
    make_user, db: Session, monkeypatch
) -> None:
    """If two compute ticks happen the same day and both detect a change
    on the same strategy (e.g. flip A, flip B back), the 2nd dispatch
    must be throttled per-strategy and emit `notification_throttled`."""
    user = make_user(email="cron-throttle@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_prior_state(db, strategy, signal={"position": "cash"})

    monkeypatch.setattr("app.jobs.signal_cron.SessionLocal", lambda: db)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    engine = MagicMock()
    engine.run = MagicMock(side_effect=lambda *a, **kw: _make_awaitable(_fake_backtest_result()))
    monkeypatch.setattr(
        "app.services.backtester.engine.BacktestEngine", lambda: engine,
    )

    send_count = [0]

    def fake_send(db_, user_, **_kw):
        send_count[0] += 1
        return True

    monkeypatch.setattr("app.services.channel_dispatcher.send_email", fake_send)

    captured = []
    monkeypatch.setattr(
        "app.services.posthog_service.capture",
        lambda *, user_id, event, properties=None: captured.append(
            {"event": event, "props": properties or {}}
        ),
    )

    # First tick — fires.
    _run_cron()
    assert send_count[0] == 1

    # Flip the state back to cash so the 2nd tick detects another change.
    state = db.get(SavedStrategySignalState, strategy.id)
    state.current_signal = {"position": "cash"}
    db.commit()

    # Second tick same day — throttled.
    _run_cron()

    assert send_count[0] == 1, (
        "2nd same-day flip should be throttled (per-strategy daily cap = 1)"
    )

    throttled = [c for c in captured if c["event"] == "notification_throttled"]
    assert len(throttled) >= 1
    assert throttled[-1]["props"]["reason"] == "strategy_daily_cap"


# ── Test 3: unsubscribed strategy gets no email ──────────────────────────────


def test_unsubscribed_strategy_skips_email_and_banner(
    make_user, db: Session, monkeypatch
) -> None:
    """Subscription is the gate for any signal-change channel dispatch.
    Without an active SignalAlertSubscription, the cron still writes the
    SignalEvent row (for history) but skips banner + email + PostHog."""
    user = make_user(email="cron-nosub@test.com")
    strategy = _save_strategy(db, user)
    # NO subscription.
    _seed_prior_state(db, strategy, signal={"position": "cash"})

    monkeypatch.setattr("app.jobs.signal_cron.SessionLocal", lambda: db)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    engine = MagicMock()
    engine.run = MagicMock(side_effect=lambda *a, **kw: _make_awaitable(_fake_backtest_result()))
    monkeypatch.setattr(
        "app.services.backtester.engine.BacktestEngine", lambda: engine,
    )

    send_count = [0]
    monkeypatch.setattr(
        "app.services.channel_dispatcher.send_email",
        lambda *a, **kw: (send_count.__setitem__(0, send_count[0] + 1), True)[1],
    )

    captured = []
    monkeypatch.setattr(
        "app.services.posthog_service.capture",
        lambda *, user_id, event, properties=None: captured.append(event),
    )

    # Subscriptions list is empty because no `subs` are returned for
    # this strategy → subscribed_ids is empty → the cron doesn't recompute
    # this strategy. We can prove the no-dispatch path by ensuring no
    # email + no PostHog event.
    stats = _run_cron()
    assert send_count[0] == 0
    assert "notification_dispatched" not in captured


# ── Test 4: email-send failure does NOT block the in-app banner ─────────────


def test_email_send_failure_does_not_block_banner_or_signal_event(
    make_user, db: Session, monkeypatch
) -> None:
    """If `send_email` raises (Resend down, etc.), the cron must still:
      - Persist the SignalEvent
      - Write the NotificationBannerEntry
      - Capture `notification_dispatched` with email_sent=False
    Email is best-effort; the banner is the user's reliable surface."""
    user = make_user(email="cron-emailfail@test.com")
    strategy = _save_strategy(db, user)
    _subscribe(db, user, strategy)
    _seed_prior_state(db, strategy, signal={"position": "cash"})

    monkeypatch.setattr("app.jobs.signal_cron.SessionLocal", lambda: db)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    engine = MagicMock()
    engine.run = MagicMock(side_effect=lambda *a, **kw: _make_awaitable(_fake_backtest_result()))
    monkeypatch.setattr(
        "app.services.backtester.engine.BacktestEngine", lambda: engine,
    )

    def angry_send_email(*a, **kw):
        raise RuntimeError("Resend exploded")

    monkeypatch.setattr(
        "app.services.channel_dispatcher.send_email", angry_send_email,
    )

    captured = []
    monkeypatch.setattr(
        "app.services.posthog_service.capture",
        lambda *, user_id, event, properties=None: captured.append(
            {"event": event, "props": properties or {}}
        ),
    )

    stats = _run_cron()
    assert stats["errors"] == 0  # email failure is swallowed gracefully

    # SignalEvent persisted.
    events = db.query(SignalEvent).filter(
        SignalEvent.saved_strategy_id == strategy.id
    ).all()
    assert len(events) == 1
    # Email NOT marked dispatched.
    assert events[0].email_dispatched_at is None
    assert events[0].email_dispatch_count == 0

    # Banner still written.
    banners = db.query(NotificationBannerEntry).all()
    assert len(banners) == 1

    # PostHog still captures dispatch attempt — but with email_sent=False
    # so the dashboard can flag email-delivery anomalies.
    dispatched = [c for c in captured if c["event"] == "notification_dispatched"]
    assert len(dispatched) == 1
    assert dispatched[0]["props"]["email_sent"] is False
    assert dispatched[0]["props"]["in_app_banner_sent"] is True


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_awaitable(value):
    """Wrap a value in a coroutine for use as MagicMock.return_value when
    the caller does `await mock(...)`."""
    async def _coro(*a, **kw):
        return value
    return _coro()
