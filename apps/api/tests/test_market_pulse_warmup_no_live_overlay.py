"""Regression test for the 2026-06-07 Market Pulse outage.

**Symptom.** Every `GET /api/market/pulse?market=US` returned HTTP 000
(connection timeout after 180s). Railway logs showed repeated:

    RuntimeError: <asyncio.locks.Lock object at 0x... [locked, waiters:9]>
                  is bound to a different event loop
    market_pulse live quote overlay failed
      File "/app/app/services/market_pulse_service.py", line 632, in get_live_pulse
        quotes = await live_quote_service.get_quotes(symbols)
      File "/app/app/services/live_quote_service.py", line 145, in _fetch_and_cache_stale
        await lock.acquire()

8 warmup ticks failed over 28 minutes before Jimmy noticed; users were
seeing the page hang for 3 minutes.

**Root cause.** PR #138's `_warmup_market_pulse_loop` runs in a worker
thread with its own event loop (per trap #21's `_run_async_in_thread`
bridge). Inside the loop it called `svc.get_live_pulse("US", db)`, which
internally calls `live_quote_service.get_quotes(symbols)`. The
`live_quote_service` is a module-level singleton with a `_locks: dict[str, asyncio.Lock]`
cache — `asyncio.Lock()` instances bind to whichever event loop creates
them. The warmup thread's loop was the first to touch some locks; any
subsequent user request on the main loop trying to acquire them then
raised `RuntimeError`. Locks the warmup acquired but couldn't release
(due to the cross-loop error mid-flight) stayed wedged forever; real
user requests piled up as waiters and timed out at the 180s curl mark.

**Fix.** The warmup now calls `svc.get_pulse(...)` (base computation only,
populates the 60-min `_CACHE`) instead of `svc.get_live_pulse(...)`. The
expensive N+1 `_load_bars` work happens in the background; the FMP live
overlay path (which holds the locks) is reached only by user requests on
the main event loop where the locks belong. Codified as trap #22 in
`apps/api/CLAUDE.md`.

This test pins the post-fix invariant: the warmup loop body must not call
into `live_quote_service`. If a future change reintroduces the call, this
test fails immediately at the assertion — long before any cross-loop
RuntimeError can wedge production locks again.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.main import _warmup_market_pulse_loop


@pytest.mark.asyncio
async def test_warmup_loop_does_not_call_live_quote_service(monkeypatch) -> None:
    """One full iteration of `_warmup_market_pulse_loop` must NOT reach
    `live_quote_service.get_quotes` — that's the call that binds locks to
    the wrong event loop and wedges production.

    Strategy: monkeypatch `asyncio.sleep` to raise after the first iteration
    (so we exit the `while True` loop deterministically) and assert that
    `live_quote_service.get_quotes` was never invoked during that iteration.
    """
    import asyncio

    # Break out of `while True` after the first iteration's `await asyncio.sleep(240)`.
    class _StopLoop(BaseException):
        pass

    async def _raise_after_first_sleep(seconds):
        raise _StopLoop()

    monkeypatch.setattr(asyncio, "sleep", _raise_after_first_sleep)

    with patch(
        "app.services.market_pulse_service.live_quote_service.get_quotes",
        new_callable=AsyncMock,
    ) as mock_get_quotes:
        with pytest.raises(_StopLoop):
            await _warmup_market_pulse_loop()

    mock_get_quotes.assert_not_called(), (
        "Warmup must not call live_quote_service.get_quotes — calling it "
        "from the warmup thread's event loop binds per-symbol asyncio.Locks "
        "to that loop, causing user requests on the main loop to either "
        "RuntimeError or hang indefinitely as waiters. See trap #22 in "
        "apps/api/CLAUDE.md. If this test fails, the 2026-06-07 outage "
        "(180-second timeouts on /api/market/pulse?market=US) is back."
    )


@pytest.mark.asyncio
async def test_warmup_loop_calls_get_pulse_for_both_markets(monkeypatch) -> None:
    """Post-fix, the warmup populates the base `_CACHE` for both US and CN
    by calling `svc.get_pulse("US", db)` and `svc.get_pulse("CN", db)`."""
    import asyncio

    class _StopLoop(BaseException):
        pass

    async def _raise_after_first_sleep(seconds):
        raise _StopLoop()

    monkeypatch.setattr(asyncio, "sleep", _raise_after_first_sleep)

    with patch(
        "app.services.market_pulse_service.MarketPulseService.get_pulse",
        return_value=None,
    ) as mock_get_pulse:
        with pytest.raises(_StopLoop):
            await _warmup_market_pulse_loop()

    # Both markets must be pre-warmed.
    call_markets = [c.args[0] for c in mock_get_pulse.call_args_list]
    assert "US" in call_markets, f"warmup must call get_pulse('US', ...); got calls: {call_markets}"
    assert "CN" in call_markets, f"warmup must call get_pulse('CN', ...); got calls: {call_markets}"
