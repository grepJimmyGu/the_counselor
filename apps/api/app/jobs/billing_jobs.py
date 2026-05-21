from __future__ import annotations

"""APScheduler billing jobs.

expire_trials_job  — runs hourly at :15, reverts expired no-card trials to Scout.
dunning_expiry_job — runs hourly at :30, cancels subscriptions still past_due after 7 days.

Both jobs are safe to re-run (idempotent WHERE clauses).
"""

import logging
from datetime import datetime, timedelta

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
    """Cancel Stripe subscription and revert to Scout after 7-day grace period."""
    from app.db.session import SessionLocal
    from app.models.user import Plan
    from app.services.stripe_service import cancel_subscription

    cutoff = datetime.utcnow() - timedelta(days=7)
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
        for row in rows:
            if row.stripe_subscription_id:
                cancel_subscription(row.stripe_subscription_id)
            row.tier = "scout"
            row.status = "active"
            row.canceled_at = datetime.utcnow()
            row.stripe_subscription_id = None
        db.commit()
        if rows:
            logger.info("dunning_expiry_job: expired dunning for %d plan(s)", len(rows))
    except Exception as exc:
        logger.error("dunning_expiry_job failed: %s", exc)
        db.rollback()
    finally:
        db.close()
