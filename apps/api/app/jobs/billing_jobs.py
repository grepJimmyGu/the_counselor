from __future__ import annotations

"""APScheduler billing jobs.

expire_trials_job  — runs hourly at :15, reverts expired no-card trials to Scout.
dunning_expiry_job — runs hourly at :30, cancels subscriptions still past_due after 7 days.

Both jobs are safe to re-run (idempotent WHERE clauses).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def expire_trials_job() -> None:
    """Trials that ended without a card added revert to Scout."""
    from datetime import timedelta
    from app.db.session import SessionLocal
    from app.models.user import Plan

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(Plan)
            .filter(
                Plan.status == "trialing",
                Plan.trial_end < now,
                Plan.stripe_subscription_id.is_(None),
            )
            .all()
        )
        for row in rows:
            row.tier = "scout"
            row.status = "active"
            # Keep trial_end as an audit trail; one-trial-per-user enforced by checking it
        db.commit()
        if rows:
            logger.info("expire_trials_job: reverted %d expired trial(s) to Scout", len(rows))

        # Stage 6a — DEFERRED_TRIGGER tripwires for the Stage 6b lifecycle emails.
        # Trial-day-7 nudge candidates: trial expires in ~7 days, no card yet.
        day_7_candidates = (
            db.query(Plan)
            .filter(
                Plan.status == "trialing",
                Plan.stripe_subscription_id.is_(None),
                Plan.trial_end.between(now + timedelta(days=6), now + timedelta(days=7, hours=1)),
            )
            .count()
        )
        if day_7_candidates > 0:
            logger.info(
                "DEFERRED_TRIGGER: trial_day_7_email — %d trialist(s) would receive "
                "the day-7 nudge if Stage 6b were wired (see docs/DEFERRED.md)",
                day_7_candidates,
            )
        # Trial-day-13 last-call candidates: trial expires in <24h, no card.
        day_13_candidates = (
            db.query(Plan)
            .filter(
                Plan.status == "trialing",
                Plan.stripe_subscription_id.is_(None),
                Plan.trial_end.between(now, now + timedelta(hours=24)),
            )
            .count()
        )
        if day_13_candidates > 0:
            logger.info(
                "DEFERRED_TRIGGER: trial_day_13_email — %d trialist(s) within 24h "
                "of expiry would receive the last-call nudge (see docs/DEFERRED.md)",
                day_13_candidates,
            )
    except Exception as exc:
        logger.error("expire_trials_job failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def dunning_expiry_job() -> None:
    """Cancel Stripe subscription and revert to Scout after 7-day grace period.

    Split into three phases so the DB connection is NEVER held during the
    Stripe API round-trip — that pattern (Stripe-call-inside-open-tx) was
    the root cause of the 2026-05-26 Railway pool exhaustion. See
    `docs/KNOWN_ISSUES.md` (entry "Production wedged 16h").

    Phase 1: open session, collect plan ids + their Stripe subscription
             ids, close session.
    Phase 2: hit Stripe API per row (no DB conn held during this). One
             failure per row only skips that row — doesn't block others.
    Phase 3: reopen session, update rows that Stripe canceled (or whose
             stripe_subscription_id was already None), commit, close.
    """
    from app.db.session import SessionLocal
    from app.models.user import Plan
    from app.services.stripe_service import cancel_subscription

    cutoff = datetime.utcnow() - timedelta(days=7)

    # ── Phase 1: collect work items (DB conn held for ~milliseconds) ──
    work_items: list[tuple[str, Optional[str]]] = []  # (plan_id, stripe_sub_id_or_None)
    db = SessionLocal()
    try:
        rows = (
            db.query(Plan)
            .filter(
                Plan.status == "past_due",
                Plan.updated_at < cutoff,
            )
            .all()
        )
        work_items = [(row.user_id, row.stripe_subscription_id) for row in rows]
    except Exception as exc:
        logger.error("dunning_expiry_job phase-1 query failed: %s", exc)
        return
    finally:
        db.close()

    if not work_items:
        return

    # ── Phase 2: external Stripe calls, NO DB connection held ─────────
    # If Stripe is slow/down, this hangs HERE, not inside an open tx.
    # Per-row try/except so one Stripe outage on one customer can't
    # block the rest of the batch.
    successfully_canceled: list[str] = []  # plan ids ready for DB update
    for plan_id, stripe_sub_id in work_items:
        if stripe_sub_id is None:
            # No Stripe sub to cancel; just needs the DB revert step.
            successfully_canceled.append(plan_id)
            continue
        try:
            cancel_subscription(stripe_sub_id)
            successfully_canceled.append(plan_id)
        except Exception as exc:
            logger.warning(
                "dunning_expiry_job: cancel_subscription failed for plan=%s sub=%s: %s — will retry next run",
                plan_id, stripe_sub_id, exc,
            )

    if not successfully_canceled:
        return

    # ── Phase 3: persist the revert-to-Scout state for canceled rows ──
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(Plan)
            .filter(Plan.user_id.in_(successfully_canceled))
            .all()
        )
        for row in rows:
            row.tier = "scout"
            row.status = "active"
            row.canceled_at = now
            row.stripe_subscription_id = None
        db.commit()
        logger.info(
            "dunning_expiry_job: expired dunning for %d plan(s) (skipped %d Stripe failures)",
            len(rows), len(work_items) - len(successfully_canceled),
        )
    except Exception as exc:
        logger.error("dunning_expiry_job phase-3 commit failed: %s", exc)
        db.rollback()
    finally:
        db.close()
