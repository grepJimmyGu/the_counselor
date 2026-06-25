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
