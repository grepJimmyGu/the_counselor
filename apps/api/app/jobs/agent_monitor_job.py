"""Runs the portfolio agent for every user who has turned it on.

A plain `def` on APScheduler's thread. It does not run the scans itself:
they use the live quote service and the shared FMP connection pool, which
belong to the main event loop (trap 22), so each batch of scans is handed to
that loop and waited for.

Scans run several at a time, not one after another. Done one by one, a run
could reach about one user every few seconds, which is a few hundred users
before the next run was due; anything beyond that was never scanned.
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.agent import AgentProfile
from app.services.agent import monitor

logger = logging.getLogger("livermore.agent")

# Users handed to the main loop at a time. Small enough that emails for a
# batch go out soon after its scans, large enough to keep every scan slot busy.
_BATCH = 50


def _now() -> float:
    return time.monotonic()


def agent_monitor_job() -> dict:
    settings = get_settings()
    if not settings.agent_monitor_enabled:
        return {"skipped": "disabled"}
    loop = monitor.main_loop()
    if loop is None or not loop.is_running():
        logger.warning("agent monitor: no main loop to run on")
        return {"skipped": "no_loop"}
    with SessionLocal() as db:
        user_ids = list(db.execute(
            select(AgentProfile.user_id)
            .where(AgentProfile.enabled == True)  # noqa: E712
            # Least recently scanned first, so if a run ever runs out of
            # time, the users it did not reach are first in the next one.
            .order_by(AgentProfile.last_scan_at.asc().nullsfirst())
        ).scalars().all())

    # Two scan slots stay free for people asking their agent to check now.
    at_once = max(1, settings.agent_scan_concurrency - 2)
    deadline = _now() + settings.agent_monitor_budget_seconds
    scanned = new = failed = 0
    for start in range(0, len(user_ids), _BATCH):
        if _now() >= deadline:
            break
        batch = user_ids[start:start + _BATCH]
        try:
            future = asyncio.run_coroutine_threadsafe(monitor.scan_many(batch, at_once=at_once), loop)
            # Every scan in the batch has its own timeout; this is the bound
            # on the batch as a whole should the loop itself stop answering.
            results = future.result(timeout=monitor.SCAN_TIMEOUT_SECONDS * (len(batch) / at_once + 1))
        except Exception:  # noqa: BLE001 — a lost batch must not stop the rest
            failed += len(batch)
            logger.exception("agent monitor: batch failed users=%d", len(batch))
            continue
        for user_id, result in results:
            if result is None:
                failed += 1
                continue
            scanned += 1
            new += result.new_insights
            # Only from here, never from a check the user asked for: they are
            # looking at the screen when they ask.
            try:
                monitor.email_new_findings(user_id, result.new_findings)
            except Exception:  # noqa: BLE001
                logger.exception("agent monitor: email failed user=%s", user_id)
    not_reached = len(user_ids) - scanned - failed
    log = logger.warning if not_reached else logger.info
    log("agent monitor: users=%d scanned=%d new_insights=%d failed=%d not_reached=%d",
        len(user_ids), scanned, new, failed, not_reached)
    return {"users": len(user_ids), "scanned": scanned, "new_insights": new, "failed": failed,
            "not_reached": not_reached}
