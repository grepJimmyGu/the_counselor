"""Small tools for doing slow work once and sharing the answer.

Three things, each built so it is safe to keep as a module-level singleton:

  PerLoop       one object per event loop, for asyncio primitives
  SingleFlight  callers asking for the same thing at once share one piece of work
  TTLCache      remember an answer for a while, optionally serving the old one
                while a fresh one is fetched

Why "per event loop" matters here: an `asyncio.Lock`, `Semaphore` or `Future`
belongs to the loop that first uses it, and this app runs more than one loop
(the main one, plus the worker-thread loops behind the startup warmups). A
singleton that keeps one of those primitives wedges the first time a second
loop touches it. That took Market Pulse down on 2026-06-07; see
apps/api/CLAUDE.md, trap 22. Everything here keeps its primitives per loop,
and keeps only plain values (the cached answers) across loops.
"""
from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any, Awaitable, Callable, Dict, Generic, Hashable, Optional, Tuple, TypeVar

logger = logging.getLogger("livermore.concurrency")

T = TypeVar("T")

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Record the loop that serves requests. Called once, from the lifespan."""
    global _main_loop
    _main_loop = loop


def main_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _main_loop


def on_main_loop() -> bool:
    """True when the caller is running on the loop that serves requests."""
    if _main_loop is None:
        return False
    try:
        return asyncio.get_running_loop() is _main_loop
    except RuntimeError:
        return False


class PerLoop(Generic[T]):
    """One `T` per event loop, made the first time that loop asks.

    The loop is held weakly and checked by identity, so a new loop that
    happens to reuse a dead loop's `id()` gets its own fresh object rather
    than the dead loop's primitives.
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._items: Dict[int, Tuple[Any, T]] = {}

    def get(self) -> T:
        loop = asyncio.get_running_loop()
        found = self._items.get(id(loop))
        if found is not None and found[0]() is loop:
            return found[1]
        # Drop entries whose loop is gone before adding one.
        for key in [k for k, (ref, _) in self._items.items() if ref() is None]:
            self._items.pop(key, None)
        item = self._factory()
        self._items[id(loop)] = (weakref.ref(loop), item)
        return item


def _retrieve(task: "asyncio.Future[Any]") -> None:
    """Mark a finished task's exception as seen. Every waiter may have been
    cancelled by the time it fails, and Python logs an unretrieved exception
    as if something had gone unhandled."""
    if not task.cancelled():
        task.exception()


class SingleFlight:
    """Callers that ask for the same key while the work is running share it.

    The work runs as its own task, so it finishes even if the caller that
    started it goes away (a phone that left the screen); the callers still
    waiting get the answer. Because of that the work must not use anything
    that belongs to one request, such as a request-scoped database session:
    open what it needs inside the factory.
    """

    def __init__(self) -> None:
        self._running: PerLoop[Dict[Hashable, "asyncio.Task[Any]"]] = PerLoop(dict)

    def start(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> "asyncio.Task[T]":
        """The task doing the work for `key`, starting it if nobody has."""
        running = self._running.get()
        task = running.get(key)
        if task is None or task.done():
            task = asyncio.get_running_loop().create_task(factory())  # type: ignore[arg-type]
            running[key] = task

            def _finished(done: "asyncio.Task[Any]", key: Hashable = key) -> None:
                if running.get(key) is done:
                    running.pop(key, None)
                _retrieve(done)

            task.add_done_callback(_finished)
        return task

    async def run(self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> T:
        # Shielded: cancelling this caller must not cancel work others share.
        return await asyncio.shield(self.start(key, factory))

    def is_running(self, key: Hashable) -> bool:
        task = self._running.get().get(key)
        return task is not None and not task.done()


class TTLCache(Generic[T]):
    """Answers kept for `ttl` seconds, loaded once per key however many ask.

    With `stale_for`, an answer older than `ttl` but younger than
    `ttl + stale_for` is returned at once and refreshed in the background, so
    only the very first caller for a key ever waits for the slow path. A
    failed load is never stored: the next caller tries again, and a failed
    background refresh leaves the old answer in place.
    """

    def __init__(
        self,
        *,
        ttl: float,
        stale_for: float = 0.0,
        max_entries: int = 1024,
        keep: Optional[Callable[[T], bool]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl = ttl
        self.stale_for = stale_for
        self.max_entries = max_entries
        # An answer `keep` rejects is handed to the callers waiting for it
        # and then forgotten, e.g. a page built while a provider was down.
        self._keep = keep
        self._clock = clock
        self._entries: Dict[Hashable, Tuple[float, T]] = {}
        self._flight = SingleFlight()

    def peek(self, key: Hashable) -> Optional[T]:
        """The stored answer if it is still fresh, without loading anything."""
        entry = self._entries.get(key)
        if entry is not None and self._clock() - entry[0] < self.ttl:
            return entry[1]
        return None

    def put(self, key: Hashable, value: T) -> None:
        self._entries.pop(key, None)
        self._entries[key] = (self._clock(), value)
        while len(self._entries) > self.max_entries:
            # Insertion order is age order: `put` re-inserts on every write.
            self._entries.pop(next(iter(self._entries)), None)

    def invalidate(self, key: Hashable) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    async def get(self, key: Hashable, loader: Callable[[], Awaitable[T]]) -> T:
        entry = self._entries.get(key)
        if entry is not None:
            age = self._clock() - entry[0]
            if age < self.ttl:
                return entry[1]
            if age < self.ttl + self.stale_for:
                self._flight.start(key, lambda: self._load(key, loader, background=True))
                return entry[1]
        return await self._flight.run(key, lambda: self._load(key, loader, background=False))

    async def _load(self, key: Hashable, loader: Callable[[], Awaitable[T]], *, background: bool) -> T:
        try:
            value = await loader()
        except Exception:
            if background:
                logger.exception("background refresh failed for %r; keeping the previous answer", key)
            raise
        if self._keep is None or self._keep(value):
            self.put(key, value)
        return value
