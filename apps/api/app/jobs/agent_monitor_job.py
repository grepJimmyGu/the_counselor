"""Runs the portfolio agent for every user who has turned it on.

A plain `def` on APScheduler's thread. It does not run the scan itself: the
scan uses the live quote service, whose asyncio locks belong to the main
event loop (trap 22), so each scan is handed to that loop and waited for.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.agent import AgentProfile
from app.services.agent import monitor

logger = logging.getLogger("livermore.agent")

# One user's scan may wait this long before the job moves on to the next.
_SCAN_TIMEOUT_SECONDS = 90


def agent_monitor_job() -> dict:
    if not get_settings().agent_monitor_enabled:
        return {"skipped": "disabled"}
    loop = monitor.main_loop()
    if loop is None or not loop.is_running():
        logger.warning("agent monitor: no main loop to run on")
        return {"skipped": "no_loop"}
    with SessionLocal() as db:
        user_ids = list(db.execute(
            select(AgentProfile.user_id).where(AgentProfile.enabled == True)  # noqa: E712
        ).scalars().all())
    scanned = new = failed = 0
    for user_id in user_ids:
        try:
            future = asyncio.run_coroutine_threadsafe(monitor.scan_user(user_id), loop)
            result = future.result(timeout=_SCAN_TIMEOUT_SECONDS)
            scanned += 1
            new += result.new_insights
            # Only from here, never from a check the user asked for: they are
            # looking at the screen when they ask.
            try:
                monitor.email_new_findings(user_id, result.new_findings)
            except Exception:  # noqa: BLE001
                logger.exception("agent monitor: email failed user=%s", user_id)
        except Exception:  # noqa: BLE001 — one user's failure must not stop the rest
            failed += 1
            logger.exception("agent monitor: scan failed user=%s", user_id)
    logger.info("agent monitor: users=%d scanned=%d new_insights=%d failed=%d", len(user_ids), scanned, new, failed)
    return {"users": len(user_ids), "scanned": scanned, "new_insights": new, "failed": failed}
