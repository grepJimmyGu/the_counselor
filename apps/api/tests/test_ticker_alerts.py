"""PRD-28 — per-ticker signal alerts.

The distinction that justifies the feature: `monitor_saved_screens` notifies on
basket ENTRANTS only. These tests pin that per-ticker alerts fire in BOTH
directions, stay silent on the first evaluation, and never fire twice for a
state that hasn't changed.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.jobs.ticker_alert_cron import (
    STATE_IN,
    STATE_OUT,
    classify_ticker_change,
    current_state,
)
from app.models.saved_strategy import SavedStrategy
from app.models.screen_basket_member import ScreenBasketMember
from app.models.ticker_signal_subscription import TickerSignalSubscription


def _screen(db: Session, sid: str, user_id: str, title: str = "My screen") -> SavedStrategy:
    row = SavedStrategy(
        id=sid,
        user_id=user_id,
        title=title,
        strategy_json={"kind": "screen", "universe_id": "sp500", "rules": []},
        is_public=False,
    )
    db.add(row)
    db.commit()
    return row


def _member(
    db: Session, sid: str, symbol: str, exited: bool = False, mid: str = None
) -> ScreenBasketMember:
    row = ScreenBasketMember(
        id=mid or f"{sid}-{symbol}",
        saved_strategy_id=sid,
        symbol=symbol,
        entered_date=date(2026, 7, 20),
        exited_date=date(2026, 7, 29) if exited else None,
    )
    db.add(row)
    db.commit()
    return row


# ── transition classification (the both-directions guarantee) ──────────────


def test_first_evaluation_is_silent() -> None:
    """Subscribing must not immediately notify about a condition that was
    already true when the user asked to watch it."""
    assert classify_ticker_change(None, STATE_IN) is None
    assert classify_ticker_change(None, STATE_OUT) is None


def test_entering_the_basket_fires() -> None:
    assert classify_ticker_change(STATE_OUT, STATE_IN) == "ticker_entered"


def test_leaving_the_basket_ALSO_fires() -> None:
    """The gap this PRD exists to close — the screen monitor records exits but
    deliberately never notifies them."""
    assert classify_ticker_change(STATE_IN, STATE_OUT) == "ticker_exited"


def test_unchanged_state_is_silent_in_both_directions() -> None:
    assert classify_ticker_change(STATE_IN, STATE_IN) is None
    assert classify_ticker_change(STATE_OUT, STATE_OUT) is None


# ── membership read ────────────────────────────────────────────────────────


def test_current_state_reads_live_membership(db: Session, make_user) -> None:
    user = make_user(email="tick@test.com")
    _screen(db, "scr1", user.id)
    _member(db, "scr1", "NVDA")                       # live row
    _member(db, "scr1", "AMD", exited=True)           # exited row

    assert current_state(db, "scr1", "NVDA") == STATE_IN
    assert current_state(db, "scr1", "AMD") == STATE_OUT
    assert current_state(db, "scr1", "TSLA") == STATE_OUT  # never a member


def test_membership_is_scoped_per_screen(db: Session, make_user) -> None:
    """A name in screen A must not read as in-basket for screen B."""
    user = make_user(email="scoped@test.com")
    _screen(db, "scrA", user.id)
    _screen(db, "scrB", user.id, title="Other")
    _member(db, "scrA", "NVDA", mid="a-nvda")

    assert current_state(db, "scrA", "NVDA") == STATE_IN
    assert current_state(db, "scrB", "NVDA") == STATE_OUT


# ── subscription model ─────────────────────────────────────────────────────


def test_subscription_is_unique_per_user_symbol_screen(db: Session, make_user) -> None:
    user = make_user(email="uniq@test.com")
    _screen(db, "scr1", user.id)
    db.add(
        TickerSignalSubscription(
            user_id=user.id, symbol="NVDA", saved_screen_id="scr1"
        )
    )
    db.commit()

    # The composite PK makes a re-subscribe a lookup, not a duplicate.
    found = db.get(TickerSignalSubscription, (user.id, "NVDA", "scr1"))
    assert found is not None
    assert found.email_enabled is True
    assert found.last_state is None  # never evaluated → first pass is silent


def test_subscription_records_observed_state(db: Session, make_user) -> None:
    user = make_user(email="state@test.com")
    _screen(db, "scr1", user.id)
    sub = TickerSignalSubscription(
        user_id=user.id, symbol="NVDA", saved_screen_id="scr1"
    )
    db.add(sub)
    db.commit()

    sub.last_state = STATE_IN
    sub.last_as_of = date(2026, 7, 30)
    db.commit()

    reread = db.get(TickerSignalSubscription, (user.id, "NVDA", "scr1"))
    assert reread.last_state == STATE_IN
    assert reread.last_as_of == date(2026, 7, 30)


# ── the cron's own gate ────────────────────────────────────────────────────


def test_monitor_no_ops_when_snapshot_disabled(monkeypatch) -> None:
    """Mirrors monitor_saved_screens: without a warmed snapshot the screens it
    depends on are stale, so the job must skip rather than emit on stale data."""
    from app.jobs import ticker_alert_cron

    monkeypatch.delenv("SCREENER_SNAPSHOT_ENABLED", raising=False)
    stats = ticker_alert_cron.monitor_ticker_subscriptions()
    assert stats == {
        "subscriptions": 0,
        "entered": 0,
        "exited": 0,
        "dispatched": 0,
        "throttled": 0,
        "errors": 0,
    }
