"""On-demand trigger for the standing-universe snapshot warm.

The daily cron (`jobs.signal_snapshot_job`) warms the snapshot at 23:00 UTC;
this runs the SAME work immediately — so a freshly-registered standing universe
(e.g. russell3000) is scannable without waiting for the cron. Worker thread +
in-memory status, mirroring `universe_backfill`.

Trap #21: the warm mixes sync SQLAlchemy + pandas compute; running it on a
worker thread (its own event loop) keeps it off the main loop that serves
/health and user requests.
Trap #22: the warm path holds no shared asyncio primitives (documented in
`signal_snapshot_job`), so it's safe on this thread's loop.

In-memory status is fine (single-process app). Coarse by design — the warm
loops symbols internally without a progress hook, so status reports
running -> completed/failed plus the final summary, not an incremental %.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("livermore.snapshot_warm_trigger")

_STATUS: Dict[str, Any] = {
    "state": "idle",  # idle | running | completed | failed
    "started_at": None,
    "finished_at": None,
    "summary": None,  # warm_universe's {symbols_ok, symbols_empty, rows, ...}
    "error": None,
}
_TASK: Optional["asyncio.Task[Any]"] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_status() -> Dict[str, Any]:
    """Current warm progress (read by the status endpoint)."""
    return dict(_STATUS)


def _run() -> None:
    """Worker-thread bridge (trap #21): give the sync-DB warm its own loop."""
    from app.jobs.signal_snapshot_job import _warm_standing_universes

    try:
        summary = asyncio.run(_warm_standing_universes())
        _STATUS.update(state="completed", summary=summary, finished_at=_now())
        logger.info("snapshot warm trigger complete: %s", summary)
    except Exception:  # noqa: BLE001 — trap #20: surface the traceback
        logger.exception("snapshot warm trigger failed")
        _STATUS.update(state="failed", error="see logs", finished_at=_now())


def start_warm() -> bool:
    """Kick the warm onto a worker thread. Returns False (no-op) if one is
    already running — guards against a double-trigger."""
    global _TASK
    if _STATUS["state"] == "running":
        return False
    _STATUS.update(
        state="running",
        started_at=_now(),
        finished_at=None,
        summary=None,
        error=None,
    )
    _TASK = asyncio.create_task(asyncio.to_thread(_run))
    return True
