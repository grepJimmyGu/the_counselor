"""The tools that let slow work be done once and shared (app/core/concurrency.py)."""
from __future__ import annotations

import asyncio
from typing import List

import pytest

from app.core import concurrency
from app.core.concurrency import PerLoop, SingleFlight, TTLCache


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ── PerLoop ───────────────────────────────────────────────────────────────────

def test_each_event_loop_gets_its_own_object_and_keeps_it() -> None:
    per_loop: PerLoop[list] = PerLoop(list)

    async def twice() -> tuple:
        return per_loop.get(), per_loop.get()

    first_a, first_b = asyncio.run(twice())
    second_a, _ = asyncio.run(twice())
    assert first_a is first_b
    assert second_a is not first_a


def test_a_lock_kept_per_loop_can_be_used_from_a_second_loop() -> None:
    """Trap 22: one asyncio.Lock held by a singleton wedges on its second loop.
    A lock per loop does not."""
    locks: PerLoop[asyncio.Lock] = PerLoop(asyncio.Lock)

    async def use() -> bool:
        async with locks.get():
            await asyncio.sleep(0)
        return True

    assert asyncio.run(use())
    assert asyncio.run(use())


def test_on_main_loop_is_only_true_on_the_registered_loop() -> None:
    async def check() -> bool:
        return concurrency.on_main_loop()

    async def registered() -> bool:
        concurrency.set_main_loop(asyncio.get_running_loop())
        try:
            return concurrency.on_main_loop()
        finally:
            concurrency.set_main_loop(None)

    assert asyncio.run(check()) is False
    assert asyncio.run(registered()) is True
    assert concurrency.on_main_loop() is False  # no loop running at all


# ── SingleFlight ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callers_at_the_same_moment_share_one_piece_of_work() -> None:
    flight = SingleFlight()
    runs = 0

    async def work() -> str:
        nonlocal runs
        runs += 1
        await asyncio.sleep(0.01)
        return "answer"

    results = await asyncio.gather(*(flight.run("k", work) for _ in range(25)))
    assert results == ["answer"] * 25
    assert runs == 1
    # Finished work is not remembered: that is the cache's job.
    assert await flight.run("k", work) == "answer"
    assert runs == 2


@pytest.mark.asyncio
async def test_different_keys_do_not_wait_for_each_other() -> None:
    flight = SingleFlight()
    started: List[str] = []
    release = asyncio.Event()

    async def work(name: str) -> str:
        started.append(name)
        await release.wait()
        return name

    tasks = [asyncio.ensure_future(flight.run(name, lambda name=name: work(name))) for name in "abc"]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sorted(started) == ["a", "b", "c"]  # all running before any finished
    release.set()
    assert sorted(await asyncio.gather(*tasks)) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_the_work_survives_the_caller_that_started_it_leaving() -> None:
    """A phone that leaves the screen cancels its request. The others waiting
    on the same work must still get their answer."""
    flight = SingleFlight()
    release = asyncio.Event()

    async def work() -> str:
        await release.wait()
        return "answer"

    first = asyncio.ensure_future(flight.run("k", work))
    await asyncio.sleep(0)
    second = asyncio.ensure_future(flight.run("k", work))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == "answer"


@pytest.mark.asyncio
async def test_a_failure_reaches_everyone_waiting_and_is_not_remembered() -> None:
    flight = SingleFlight()
    attempts = 0

    async def work() -> str:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0)
        if attempts == 1:
            raise RuntimeError("provider down")
        return "answer"

    results = await asyncio.gather(*(flight.run("k", work) for _ in range(3)), return_exceptions=True)
    assert all(isinstance(r, RuntimeError) for r in results)
    assert await flight.run("k", work) == "answer"


# ── TTLCache ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_fresh_answer_is_returned_without_loading_again() -> None:
    clock = _Clock()
    cache: TTLCache[int] = TTLCache(ttl=60, clock=clock)
    loads = 0

    async def load() -> int:
        nonlocal loads
        loads += 1
        return loads

    assert await cache.get("k", load) == 1
    clock.now += 59
    assert await cache.get("k", load) == 1
    assert cache.peek("k") == 1
    clock.now += 2
    assert cache.peek("k") is None
    assert await cache.get("k", load) == 2
    assert loads == 2


@pytest.mark.asyncio
async def test_an_old_answer_is_returned_at_once_and_replaced_behind_the_caller() -> None:
    clock = _Clock()
    cache: TTLCache[str] = TTLCache(ttl=60, stale_for=600, clock=clock)
    release = asyncio.Event()
    versions = iter(["first", "second"])

    async def load() -> str:
        value = next(versions)
        if value == "second":
            await release.wait()
        return value

    assert await cache.get("k", load) == "first"
    clock.now += 120  # past ttl, inside stale_for
    # Returned immediately even though the reload has not finished...
    assert await asyncio.wait_for(cache.get("k", load), timeout=0.5) == "first"
    release.set()
    for _ in range(5):
        await asyncio.sleep(0)
    # ...and the next caller gets what the reload fetched.
    assert await cache.get("k", load) == "second"


@pytest.mark.asyncio
async def test_an_answer_too_old_to_serve_is_waited_for() -> None:
    clock = _Clock()
    cache: TTLCache[str] = TTLCache(ttl=60, stale_for=600, clock=clock)
    versions = iter(["first", "second"])

    async def load() -> str:
        return next(versions)

    assert await cache.get("k", load) == "first"
    clock.now += 60 + 600 + 1
    assert await cache.get("k", load) == "second"


@pytest.mark.asyncio
async def test_a_failed_background_refresh_keeps_the_old_answer() -> None:
    clock = _Clock()
    cache: TTLCache[str] = TTLCache(ttl=60, stale_for=600, clock=clock)
    calls = 0

    async def load() -> str:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("provider down")
        return "first"

    assert await cache.get("k", load) == "first"
    clock.now += 120
    assert await cache.get("k", load) == "first"
    for _ in range(5):
        await asyncio.sleep(0)
    assert await cache.get("k", load) == "first"


@pytest.mark.asyncio
async def test_a_failed_first_load_raises_and_stores_nothing() -> None:
    cache: TTLCache[str] = TTLCache(ttl=60)

    async def broken() -> str:
        raise RuntimeError("provider down")

    async def working() -> str:
        return "answer"

    with pytest.raises(RuntimeError):
        await cache.get("k", broken)
    assert await cache.get("k", working) == "answer"


@pytest.mark.asyncio
async def test_an_answer_the_keep_rule_rejects_is_shared_once_and_not_stored() -> None:
    cache: TTLCache[dict] = TTLCache(ttl=60, keep=lambda value: value["complete"])
    loads = 0

    async def partial() -> dict:
        nonlocal loads
        loads += 1
        await asyncio.sleep(0)
        return {"complete": False}

    # Everyone waiting on that load gets it...
    results = await asyncio.gather(*(cache.get("k", partial) for _ in range(4)))
    assert results == [{"complete": False}] * 4 and loads == 1
    # ...and the next caller loads again.
    await cache.get("k", partial)
    assert loads == 2


@pytest.mark.asyncio
async def test_the_oldest_answers_are_dropped_past_the_limit() -> None:
    cache: TTLCache[int] = TTLCache(ttl=60, max_entries=3)
    for n in range(5):
        cache.put(n, n)
    assert len(cache) == 3
    assert cache.peek(0) is None and cache.peek(1) is None
    assert cache.peek(4) == 4


def test_a_cached_answer_is_usable_from_another_event_loop() -> None:
    """The answers are plain values. Only the in-flight sharing is per loop."""
    cache: TTLCache[str] = TTLCache(ttl=60)
    loads = 0

    async def load() -> str:
        nonlocal loads
        loads += 1
        return "answer"

    async def get() -> str:
        return await cache.get("k", load)

    assert asyncio.run(get()) == "answer"
    assert asyncio.run(get()) == "answer"
    assert loads == 1
