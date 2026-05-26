"""Stage 8 v0 Phase B — daily signal recompute cron.

Covers spec §10 acceptance #1, #2, #3, #12 by exercising
`recompute_signals_job` against an in-memory DB with mocked engine + email
send. The mocks isolate the cron's orchestration logic from the backtester
(tested separately in test_signal_compute.py) and from Resend (tested in
Stage 6a).
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models.saved_strategy import SavedStrategy
from app.models.saved_strategy_signal_state import SavedStrategySignalState
from app.models.signal_alert_subscription import SignalAlertSubscription
from app.models.signal_event import SignalEvent


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_strategy(db: Session, user_id: str, title: str = "Test MA filter") -> SavedStrategy:
    row = SavedStrategy(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        strategy_json={
            "strategy_type": "moving_average_filter",
            "universe": ["NVDA"],
            "benchmark": "NVDA",
            "start_date": "2024-01-02",
            "end_date": "2024-12-30",
            "initial_capital": 100_000,
            "rebalance_frequency": "monthly",
            "transaction_cost_bps": 0,
            "slippage_bps": 0,
            "rules": [{"lookback_days": 20}],
            "position_sizing": {"method": "equal_weight"},
            "risk_management": {},
            "cash_management": {},
            "strategy_name": title,
        },
    )
    db.add(row)
    db.commit()
    return row


def _subscribe(db: Session, user_id: str, saved_strategy_id: str) -> None:
    db.add(SignalAlertSubscription(
        user_id=user_id,
        saved_strategy_id=saved_strategy_id,
        email_enabled=True,
    ))
    db.commit()


def _fake_signal(position: str = "long", ticker: str = "NVDA") -> dict:
    """Build a compute_current_signal-shaped return value for mocks."""
    if position == "cash":
        return {
            "signal": {"position": "cash"},
            "display": "In cash",
            "prices": {"NVDA": 145.23},
        }
    return {
        "signal": {"position": "long", "ticker": ticker},
        "display": f"Hold {ticker}",
        "prices": {ticker: 145.23},
    }


class _NoCloseSession:
    """Wrap the test session so the cron's `db.close()` doesn't detach the
    ORM objects the test still wants to read after the call returns.

    Why this is necessary: with `sqlite:///:memory:`, closing the only
    Session implicitly drops the in-memory database, so subsequent queries
    from the test fixture's `db` raise `DetachedInstanceError`. Production
    sessions are short-lived per cron run, so the close is correct there.
    """

    def __init__(self, real: Session) -> None:
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self) -> None:
        return None


def _run_cron_with_mocks(
    db: Session,
    monkeypatch,
    *,
    compute_return=None,
    compute_side_effect=None,
    send_return: bool = True,
):
    """Invoke recompute_signals_job with compute_current_signal + send_email patched."""
    from app.jobs import signal_jobs

    monkeypatch.setattr(
        "app.db.session.SessionLocal",
        lambda: _NoCloseSession(db),
    )

    compute_kwargs = {}
    if compute_side_effect is not None:
        compute_kwargs["side_effect"] = compute_side_effect
    else:
        compute_kwargs["return_value"] = compute_return

    with patch(
        "app.services.signal_service.compute_current_signal",
        **compute_kwargs,
    ), patch(
        "app.services.email_service.send_email",
        return_value=send_return,
    ) as send_mock:
        signal_jobs.recompute_signals_job()
        return send_mock


# ── #1 First compute creates state with no email ────────────────────────────


def test_first_compute_creates_state_and_does_not_email(
    db: Session, make_user, monkeypatch
) -> None:
    """Spec §10 #1 — initial recompute writes the state row silently."""
    user = make_user(email="u1@example.com")
    strategy = _make_strategy(db, user.id)
    _subscribe(db, user.id, strategy.id)
    assert db.query(SavedStrategySignalState).count() == 0

    send_mock = _run_cron_with_mocks(db, monkeypatch, compute_return=_fake_signal("long", "NVDA"))

    states = db.query(SavedStrategySignalState).all()
    assert len(states) == 1
    assert states[0].current_signal_display == "Hold NVDA"
    assert db.query(SignalEvent).count() == 0
    send_mock.assert_not_called()


# ── #2 Unchanged signal: no event, no email ─────────────────────────────────


def test_unchanged_signal_no_event_no_email(
    db: Session, make_user, monkeypatch
) -> None:
    """Spec §10 #2 — subsequent runs with the same signal bump last_computed_at
    and nothing else."""
    user = make_user(email="u2@example.com")
    strategy = _make_strategy(db, user.id)
    _subscribe(db, user.id, strategy.id)

    # Seed an existing state row matching what compute will return.
    db.add(SavedStrategySignalState(
        saved_strategy_id=strategy.id,
        current_signal={"position": "long", "ticker": "NVDA"},
        current_signal_display="Hold NVDA",
        as_of_date=date(2026, 5, 24),
    ))
    db.commit()

    send_mock = _run_cron_with_mocks(db, monkeypatch, compute_return=_fake_signal("long", "NVDA"))

    assert db.query(SignalEvent).count() == 0
    send_mock.assert_not_called()


# ── #3 Signal flip: event + email ───────────────────────────────────────────


def test_changed_signal_creates_event_and_dispatches_emails(
    db: Session, make_user, monkeypatch
) -> None:
    """Spec §10 #3 — a flip writes a SignalEvent and routes the alert to each
    active subscriber. We mock send_email to True so the dispatch counters
    increment without touching Resend."""
    user = make_user(email="u3@example.com")
    strategy = _make_strategy(db, user.id)
    _subscribe(db, user.id, strategy.id)

    # Existing state says "long NVDA"; compute returns "cash" → flip_to_cash.
    db.add(SavedStrategySignalState(
        saved_strategy_id=strategy.id,
        current_signal={"position": "long", "ticker": "NVDA"},
        current_signal_display="Hold NVDA",
        as_of_date=date(2026, 5, 24),
    ))
    db.commit()

    send_mock = _run_cron_with_mocks(db, monkeypatch, compute_return=_fake_signal("cash"))

    events = db.query(SignalEvent).all()
    assert len(events) == 1
    assert events[0].change_type == "flip_to_cash"
    assert events[0].previous_signal_display == "Hold NVDA"
    assert events[0].new_signal_display == "In cash"
    assert events[0].email_dispatch_count == 1
    assert events[0].email_dispatched_at is not None

    assert send_mock.call_count == 1
    _, kwargs = send_mock.call_args
    assert kwargs["template"] == "signal_alert"
    assert kwargs["subject"].startswith("Your saved strategy signaled SELL")


# ── #12 Per-strategy failure does not block other strategies ────────────────


def test_failing_strategy_does_not_block_other_strategies(
    db: Session, make_user, monkeypatch
) -> None:
    """Spec §10 #12 — engine errors are logged and the loop continues. After
    the cron run, the healthy strategy still has a state row."""
    user = make_user(email="u4@example.com")
    bad = _make_strategy(db, user.id, title="bad strategy")
    good = _make_strategy(db, user.id, title="good strategy")
    _subscribe(db, user.id, bad.id)
    _subscribe(db, user.id, good.id)

    def fake_compute(_db, _strategy, _today):
        # Use the title to discriminate — distinct() doesn't preserve order,
        # so dispatch on the data the cron actually fed us.
        if _strategy.strategy_name == "bad strategy":
            raise RuntimeError("simulated engine blow-up")
        return _fake_signal("long", "NVDA")

    send_mock = _run_cron_with_mocks(db, monkeypatch, compute_side_effect=fake_compute)

    states = db.query(SavedStrategySignalState).all()
    good_state = [s for s in states if s.saved_strategy_id == good.id]
    assert len(good_state) == 1, "healthy strategy must still get a state row"
    bad_state = [s for s in states if s.saved_strategy_id == bad.id]
    assert bad_state == [], "failing strategy must not produce a partial state row"
    # First compute on the healthy strategy is silent (no email).
    send_mock.assert_not_called()
