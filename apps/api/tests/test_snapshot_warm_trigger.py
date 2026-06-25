"""Tests for the on-demand snapshot warm trigger
(app/services/snapshot_warm_trigger.py). The warm itself is verified live
post-deploy; these cover the status shape + the double-run guard (DB-free)."""
from __future__ import annotations

from app.services import snapshot_warm_trigger as sw


def test_status_shape():
    s = sw.get_status()
    assert set(s) == {"state", "started_at", "finished_at", "summary", "error"}
    assert s["state"] in ("idle", "running", "completed", "failed")


def test_start_guard_blocks_double_run(monkeypatch):
    # Force "running"; the guard must refuse without spawning a thread (returns
    # before asyncio.create_task, so this is safe outside an event loop).
    monkeypatch.setitem(sw._STATUS, "state", "running")
    assert sw.start_warm() is False


def test_trigger_endpoint_is_async():
    # The trigger endpoint MUST be `async def`. A sync (`def`) endpoint runs in
    # FastAPI's threadpool with no running event loop, so start_warm()'s
    # asyncio.create_task raises RuntimeError -> 500 (and leaves status wedged
    # at "running"). This was the 2026-06-25 bug; guard the regression.
    import asyncio

    from app.api.routes.admin import trigger_snapshot_warm

    assert asyncio.iscoroutinefunction(trigger_snapshot_warm)
