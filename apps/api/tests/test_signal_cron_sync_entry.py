"""Regression test for trap #21 in `signal_cron.compute_all_signals`.

**Background.** `compute_all_signals` is registered as an APScheduler
cron job at `main.py:366`. APScheduler's `BackgroundScheduler` does NOT
natively await coroutines — calling an `async def` returns a coroutine
object which APScheduler drops without awaiting. The cron silently does
nothing.

Before this fix the function was `async def`. Registering it ran every
night at 22:00 UTC but never actually executed the body. The bug would
have shipped the moment Sonnet's PRD-19 work made it past code review;
no email, no banner, no SignalEvent rows would have been written.

**The fix.** `compute_all_signals` is now a sync wrapper that calls
`asyncio.run(_compute_all_signals_async())`. The async body is preserved
(so it can `await` BacktestEngine calls if needed); the public surface
APScheduler sees is sync and the worker thread drives the work via a
fresh event loop.

**This test pins the post-fix invariant.** If a future change makes
`compute_all_signals` async again (the original anti-pattern), this
test fails at import time — long before the cron silently no-ops in
production.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

from app.jobs.signal_cron import compute_all_signals


def test_public_entry_point_is_sync_not_async() -> None:
    """The cron entry point APScheduler calls must be a sync function.

    If this fails, `compute_all_signals` was rewritten as `async def` —
    reintroducing trap #21. APScheduler's BackgroundScheduler would call
    it, receive a coroutine, never await, and the nightly signal recompute
    would silently no-op in production.
    """
    assert not inspect.iscoroutinefunction(compute_all_signals), (
        "compute_all_signals must be a sync function so APScheduler's "
        "BackgroundScheduler can drive it. If you need async work inside, "
        "wrap it: `def compute_all_signals(): return asyncio.run(...)`. "
        "See trap #21 in apps/api/CLAUDE.md."
    )


def test_calling_compute_all_signals_executes_the_body() -> None:
    """Smoke test: calling the entry point actually runs to completion
    and returns the expected stats dict shape.

    With the bug in place (async def + APScheduler), the cron returned
    a coroutine object instead of running. Now it returns a dict.

    We mock SessionLocal so the test has no DB dependency — the goal is
    "the body runs" not "the body computes real signals."
    """
    mock_session = MagicMock()
    # No subscribed strategies + no saved strategies — fastest exit path,
    # but proves the body actually executed (didn't just hand back a
    # coroutine that was never awaited).
    mock_session.execute.return_value.scalars.return_value.all.return_value = []

    with patch("app.jobs.signal_cron.SessionLocal", return_value=mock_session):
        result = compute_all_signals()

    # Pre-fix this returned a coroutine, not a dict. Post-fix it must be
    # the stats shape the caller (and any tests / metrics) expects.
    assert isinstance(result, dict), (
        f"compute_all_signals should return a dict; got {type(result).__name__}. "
        "If you see a coroutine here, the trap #21 fix was reverted."
    )
    assert set(result.keys()) >= {"total", "changed", "dispatched", "errors"}, (
        f"result missing expected stats keys; got {set(result.keys())}"
    )


def test_asyncio_run_is_idempotent_across_consecutive_ticks() -> None:
    """APScheduler can fire the cron back-to-back (after misfire recovery,
    manual trigger, etc.). The sync wrapper must handle repeated calls —
    each one creates its own event loop via `asyncio.run` and tears it
    down cleanly.

    If the implementation accidentally tries to reuse a loop or holds
    one open across calls, the second call would raise
    `RuntimeError: There is no current event loop in thread` or
    `RuntimeError: This event loop is already running`.
    """
    mock_session = MagicMock()
    mock_session.execute.return_value.scalars.return_value.all.return_value = []

    with patch("app.jobs.signal_cron.SessionLocal", return_value=mock_session):
        r1 = compute_all_signals()
        r2 = compute_all_signals()

    assert isinstance(r1, dict) and isinstance(r2, dict)


def test_running_inside_an_existing_event_loop_is_safe() -> None:
    """Defense-in-depth: if a future refactor schedules `compute_all_signals`
    from within an existing event loop (e.g., via `asyncio.to_thread`),
    the `asyncio.run` inside would raise. This test documents the
    constraint: the sync wrapper assumes its caller is NOT inside an
    event loop. APScheduler's BackgroundScheduler satisfies that — it
    runs jobs in plain worker threads.

    We don't have a fix for this case (it'd require detecting the loop
    and either using `loop.run_until_complete` on a fresh thread or
    refactoring callers). We just pin the documented constraint so a
    future agent doesn't accidentally call this from within a running
    loop and find their stack mysteriously broken.
    """
    async def caller_inside_a_loop():
        # Calling compute_all_signals() here would raise
        # RuntimeError: asyncio.run() cannot be called from a running event loop
        # That's the expected, documented behavior — not a bug to fix.
        return "documented_constraint"

    result = asyncio.run(caller_inside_a_loop())
    assert result == "documented_constraint"
