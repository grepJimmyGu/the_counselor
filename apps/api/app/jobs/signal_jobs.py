"""Stage 8 v0 Phase B — daily signal recompute cron.

Runs once daily at 22:00 UTC (after US market close + Alpha Vantage refresh).
For each saved strategy that has at least one active subscriber:

  1. Recompute the strategy's current position (via signal_service).
  2. If this is the strategy's first computation, store the state with no
     email (silent first-time per spec §6).
  3. If the signal is unchanged, bump `last_computed_at` only.
  4. If the signal differs, write a SignalEvent and send alert emails to
     every subscriber with `email_enabled=True`.

Per-strategy errors are isolated (spec §10 #12): a single backtest failure
does not block other strategies in the same run.

The job is registered conditionally in `app.main` — only when
`settings.signal_alerts_enabled=True` (see Phase A feature flag).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("livermore.signals.cron")


def recompute_signals_job() -> None:
    """Entry point invoked by APScheduler. Sync wrapper around the per-strategy
    loop; the engine call inside `compute_current_signal` is async but uses its
    own event loop via `asyncio.run()`."""
    # Local imports — match billing_jobs pattern. Defers heavy modules (engine,
    # pandas) until the job actually fires, keeps app boot fast.
    from app.db.session import SessionLocal
    from app.emails.signal_alert import render_signal_alert
    from app.models.saved_strategy import SavedStrategy
    from app.models.saved_strategy_signal_state import SavedStrategySignalState
    from app.models.signal_alert_subscription import SignalAlertSubscription
    from app.models.signal_event import SignalEvent
    from app.models.user import User
    from app.schemas.strategy import StrategyJSON
    from app.services.email_service import make_signal_unsub_token, send_email
    from app.services.signal_service import (
        classify_change,
        compute_current_signal,
        signals_equal,
    )

    db = SessionLocal()
    site_url = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://livermorealpha.com")
    today = date.today()

    try:
        # Distinct saved_strategy_ids with at least one subscription.
        strategy_ids = [
            sid for (sid,) in db.query(SignalAlertSubscription.saved_strategy_id)
            .distinct()
            .all()
        ]
        logger.info("signal_recompute_started count=%d", len(strategy_ids))

        for sid in strategy_ids:
            try:
                _process_one_strategy(
                    db, sid, today, site_url,
                    SavedStrategy, SavedStrategySignalState, SignalAlertSubscription,
                    SignalEvent, User, StrategyJSON,
                    compute_current_signal, signals_equal, classify_change,
                    render_signal_alert, make_signal_unsub_token, send_email,
                )
            except Exception as exc:
                # Spec §10 #12 — one strategy failure must not block others.
                # Roll back any partial state for this strategy and continue.
                db.rollback()
                logger.exception("signal_recompute_failed sid=%s: %s", sid, exc)

        logger.info("signal_recompute_finished")
    finally:
        db.close()


def _process_one_strategy(
    db,
    sid: str,
    today: date,
    site_url: str,
    SavedStrategy,
    SavedStrategySignalState,
    SignalAlertSubscription,
    SignalEvent,
    User,
    StrategyJSON,
    compute_current_signal,
    signals_equal,
    classify_change,
    render_signal_alert,
    make_signal_unsub_token,
    send_email,
) -> None:
    """Recompute one strategy and dispatch alerts if needed.

    Factored out of the loop body so the parent's try/except can wrap a single
    call site. All model + service references are injected to avoid duplicating
    the local-import block.
    """
    strategy_row: Optional = db.get(SavedStrategy, sid)
    if strategy_row is None:
        # Strategy deleted between subscription insert and this run — clean up.
        logger.info("signal_recompute_skipped sid=%s reason=missing_strategy", sid)
        return

    try:
        strategy_json = StrategyJSON.model_validate(strategy_row.strategy_json)
    except Exception as exc:
        logger.warning("signal_recompute_bad_json sid=%s: %s", sid, exc)
        return

    try:
        result = compute_current_signal(db, strategy_json, today)
    except NotImplementedError as exc:
        # Fundamental strategies — known v0 limitation, log + skip.
        logger.info("signal_recompute_skipped sid=%s reason=unsupported_type: %s", sid, exc)
        return

    new_signal = result["signal"]
    new_display = result["display"]
    prices = result["prices"]

    state = db.get(SavedStrategySignalState, sid)
    now = datetime.utcnow()

    if state is None:
        # Spec §6 — first computation is silent.
        db.add(SavedStrategySignalState(
            saved_strategy_id=sid,
            current_signal=new_signal,
            current_signal_display=new_display,
            as_of_date=today,
            last_computed_at=now,
        ))
        db.commit()
        logger.info("signal_first_compute sid=%s display=%r", sid, new_display)
        return

    if signals_equal(state.current_signal, new_signal):
        state.last_computed_at = now
        db.commit()
        return

    # Signal changed — log event + update state + dispatch emails.
    event = SignalEvent(
        id=str(uuid.uuid4()),
        saved_strategy_id=sid,
        previous_signal=state.current_signal,
        previous_signal_display=state.current_signal_display,
        new_signal=new_signal,
        new_signal_display=new_display,
        change_type=classify_change(state.current_signal, new_signal),
        as_of_date=today,
        reference_price_snapshot=prices,
    )
    db.add(event)
    state.current_signal = new_signal
    state.current_signal_display = new_display
    state.last_changed_at = now
    state.as_of_date = today
    state.last_computed_at = now
    db.flush()  # populate event.id-derived state without committing yet

    subs = db.query(SignalAlertSubscription).filter(
        SignalAlertSubscription.saved_strategy_id == sid,
        SignalAlertSubscription.email_enabled.is_(True),
    ).all()

    sent_count = 0
    for sub in subs:
        user = db.get(User, sub.user_id)
        if user is None or not user.email:
            continue
        single_token = make_signal_unsub_token(sub.user_id, sid, scope="single")
        all_token = make_signal_unsub_token(sub.user_id, None, scope="all")
        single_url = f"{site_url}/api/email/signal-unsub?token={single_token}"
        all_url = f"{site_url}/api/email/signal-unsub?token={all_token}"
        rendered = render_signal_alert(user, strategy_row, event, single_url, all_url)
        # Signal alerts are user-requested per-strategy opt-ins (SignalAlertSubscription
        # row IS the consent), so route as transactional — bypasses the global
        # marketing-unsubscribe flag in email_service._prefs_allow().
        if send_email(
            db, user,
            template="signal_alert",
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            category="transactional",
        ):
            sent_count += 1

    if sent_count:
        event.email_dispatched_at = datetime.utcnow()
        event.email_dispatch_count = sent_count

    db.commit()
    logger.info(
        "signal_change sid=%s change_type=%s sent=%d previous=%r new=%r",
        sid, event.change_type, sent_count, state.current_signal_display, new_display,
    )
