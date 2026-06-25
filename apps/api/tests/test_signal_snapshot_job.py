"""PRD-23a slice 2b — signal_snapshot warm cron gating.

The job is registered unconditionally but must no-op unless
SCREENER_SNAPSHOT_ENABLED is set, so it adds zero production load until the
screener UI ships.
"""
from __future__ import annotations

import app.jobs.signal_snapshot_job as job


def test_enabled_reflects_env(monkeypatch):
    monkeypatch.delenv("SCREENER_SNAPSHOT_ENABLED", raising=False)
    assert job._enabled() is False
    for truthy in ("true", "1", "yes", "on", "TRUE"):
        monkeypatch.setenv("SCREENER_SNAPSHOT_ENABLED", truthy)
        assert job._enabled() is True
    for falsy in ("false", "0", "", "no"):
        monkeypatch.setenv("SCREENER_SNAPSHOT_ENABLED", falsy)
        assert job._enabled() is False


def test_job_noops_when_disabled(monkeypatch):
    monkeypatch.delenv("SCREENER_SNAPSHOT_ENABLED", raising=False)

    def _boom():
        raise AssertionError("_warm_standing_universes must not run when disabled")

    monkeypatch.setattr(job, "_warm_standing_universes", _boom)
    # Should return cleanly without touching the warm path.
    job.warm_signal_snapshot_job()


def test_job_runs_warm_when_enabled(monkeypatch):
    monkeypatch.setenv("SCREENER_SNAPSHOT_ENABLED", "true")
    calls = {"n": 0}

    async def _fake_warm():
        calls["n"] += 1
        return {"symbols_ok": 3, "symbols_empty": 0, "rows": 99}

    monkeypatch.setattr(job, "_warm_standing_universes", _fake_warm)
    job.warm_signal_snapshot_job()
    assert calls["n"] == 1


def test_job_swallows_and_logs_warm_failure(monkeypatch):
    # A warm failure must not propagate out of the cron entry point (trap #20:
    # logged via logger.exception, not raised).
    monkeypatch.setenv("SCREENER_SNAPSHOT_ENABLED", "true")

    async def _fail():
        raise RuntimeError("boom")

    monkeypatch.setattr(job, "_warm_standing_universes", _fail)
    job.warm_signal_snapshot_job()  # no exception escapes
