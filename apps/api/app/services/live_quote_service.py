"""Live quote cache (2026-05-21).

In-process cache for live stock quotes from FMP. Single source of truth for
every "live price" surface on the frontend — the ticker bar, stock detail
pages, workspace strategy preview, Market Pulse, and the community feed.

Design (one diagram for the file):

    page A asks for [NVDA, AAPL]  ┐
    page B asks for [AAPL, MSFT]  ┼──> get_quotes()
    page C asks for [NVDA]        ┘        │
                                            ├── split fresh vs stale
                                            ├── each stale symbol joins the
                                            │   queue for the next FMP call,
                                            │   or the wait for the call that
                                            │   is already fetching it
                                            ├── one FMP call at a time carries
                                            │   everything queued meanwhile
                                            └── return merged result

Properties:
  - 30s TTL by default — any quote within 30s of fetch is reused. A caller
    may ask for fresher with `max_age`; /api/live/quotes does, from
    `settings.live_quote_ttl_seconds`.
  - Optional Alpha Vantage real-time source in front of FMP
    (`settings.live_quote_provider == "alpha_vantage"`), for small batches
    only; anything it does not return is fetched from FMP as before.
  - A symbol is fetched once however many callers want it at the same moment.
  - Callers never queue behind each other. They queue behind FMP, and every
    FMP call carries the union of what all of them are missing (a page with
    12 tickers = 1 FMP call, and so do forty pages arriving together).
  - Nothing asyncio-bound is kept across event loops (trap 22): the queue and
    its futures are per loop, and only the cached quotes are shared.
  - Single-process (cache lives in this Python module's globals). If we ever
    scale Railway to multi-worker, swap the _cache dict for Redis.

Why it changed (2026-11-20). The first version took one asyncio.Lock per
stale symbol, in sorted order, and held them all across the FMP call. Two
callers with one symbol in common therefore ran strictly one after the other,
each paying a full FMP round trip, and with a popular symbol on every
watchlist that made the whole endpoint serial: 40 simultaneous requests
across 12 symbols took 6.9 s in production, where one FMP call would have
answered all of them.

Numbers (for context):
  - FMP starter rate limit: ~300 calls/min
  - 100 users on 100 different stocks, 30s refresh:
        first 30s: 100 cache misses → 100 fetches (or fewer with batching)
        steady state: 0 calls until TTL expires
  - 100 users on the SAME stock: 1 fetch total.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.concurrency import PerLoop
from app.core.config import get_settings
from app.services.alpha_vantage_quotes import BULK_LIMIT, AlphaVantageQuoteClient
from app.services.fmp_client import FMPClient

_log = logging.getLogger(__name__)

# 30 seconds is the design point: long enough to amortize FMP calls across
# concurrent users, short enough that "live" still feels live. Don't bump
# without re-running the call-rate math.
TTL_SECONDS = 30.0

# A caller cannot ask for quotes fresher than this. Below a couple of seconds
# every poll is a provider call, which is a rate-limit incident rather than a
# feature.
MIN_MAX_AGE_SECONDS = 2.0


@dataclass(frozen=True)
class LiveQuote:
    """Snapshot of an FMP /stable/quote response, normalized."""
    symbol: str
    price: float
    change: float
    change_percent: float
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[int]
    market_cap: Optional[float]
    name: Optional[str]
    exchange: Optional[str]
    # time.monotonic() at fetch — a cache-age clock, NOT a wall-clock time.
    # (The field was documented as "epoch seconds" and never was; it stays
    # for cache arithmetic and for clients that already read it.)
    fetched_at: float
    # Wall-clock epoch seconds when we fetched it: "prices checked at".
    checked_at: Optional[float] = None
    # Epoch seconds of the quote itself — the last trade — when the provider
    # says. During market hours this is how old the PRICE is, which
    # `checked_at` cannot tell you.
    as_of: Optional[float] = None
    source: str = "fmp"


@dataclass
class _Pending:
    """What one event loop is waiting on FMP for."""
    # Every symbol asked for and not yet answered, queued or in flight.
    waiting: Dict[str, "asyncio.Future[None]"] = field(default_factory=dict)
    # The ones not yet sent to FMP.
    queue: List[str] = field(default_factory=list)
    fetcher: Optional["asyncio.Task[None]"] = None


def _seen(future: "asyncio.Future[None]") -> None:
    # A caller may have been cancelled before its symbol failed.
    if not future.cancelled():
        future.exception()


class LiveQuoteService:
    """Holds the cache and the queue for FMP. Instantiated as a module-level
    singleton at the bottom of this file; routes import `live_quote_service`."""

    def __init__(
        self,
        fmp: Optional[FMPClient] = None,
        alpha_vantage: Optional[AlphaVantageQuoteClient] = None,
        provider: Optional[str] = None,
    ) -> None:
        self._fmp = fmp or FMPClient()
        self._alpha_vantage = alpha_vantage or AlphaVantageQuoteClient()
        # None = read the setting on each fetch, so the env var is the switch.
        self._provider_override = provider
        self._cache: dict[str, LiveQuote] = {}
        self._pending: PerLoop[_Pending] = PerLoop(_Pending)

    def _is_fresh(self, q: LiveQuote, now: float, max_age: float = TTL_SECONDS) -> bool:
        return (now - q.fetched_at) < max_age

    def _uses_alpha_vantage(self, count: int) -> bool:
        """Alpha Vantage first, for batches it can answer in one call.

        Market Pulse asks for ~500 symbols at a time; sending those to AV
        would spend five calls per refresh against a per-minute quota that
        the watch-list traffic also draws on. Those stay on FMP. A batch is
        everything queued while the previous call was out, so a watch list
        that happens to arrive alongside Market Pulse rides to FMP with it.
        """
        provider = self._provider_override or get_settings().live_quote_provider
        return (provider or "").strip().lower() == "alpha_vantage" and count <= BULK_LIMIT

    def cached(self, symbol: str, max_age: float = TTL_SECONDS) -> Optional[LiveQuote]:
        """The last quote fetched for *symbol* if it is younger than
        *max_age* seconds. Never fetches, so it never waits."""
        quote = self._cache.get(symbol.upper())
        if quote is not None and (time.monotonic() - quote.fetched_at) < max_age:
            return quote
        return None

    async def get_quotes(
        self, symbols: list[str], max_age: Optional[float] = None
    ) -> dict[str, LiveQuote]:
        """Return cached quotes for *symbols*, fetching any stale ones.

        `max_age` (seconds) asks for fresher quotes than the 30 s default;
        it is floored at `MIN_MAX_AGE_SECONDS` and never widens the default.

        Result dict only contains entries we successfully resolved; callers
        treat missing keys as "no data available" (e.g., bad ticker, FMP
        outage). Symbols are upper-cased on the way in.
        """
        if not symbols:
            return {}
        normalized = [s.upper() for s in symbols if s]
        now = time.monotonic()
        ttl = TTL_SECONDS if max_age is None else min(TTL_SECONDS, max(MIN_MAX_AGE_SECONDS, max_age))

        fresh: dict[str, LiveQuote] = {}
        stale: list[str] = []
        for sym in normalized:
            cached = self._cache.get(sym)
            if cached and self._is_fresh(cached, now, ttl):
                fresh[sym] = cached
            else:
                stale.append(sym)

        if not stale:
            return fresh

        await self._fetch_stale(stale)

        # Re-collect after the fetch; some symbols may still be missing if
        # FMP didn't return them.
        result = dict(fresh)
        for sym in stale:
            q = self._cache.get(sym)
            if q is not None:
                result[sym] = q
        return result

    async def get_quote(self, symbol: str) -> Optional[LiveQuote]:
        """Convenience wrapper around get_quotes() for the one-ticker case."""
        result = await self.get_quotes([symbol])
        return result.get(symbol.upper())

    async def _fetch_from_alpha_vantage(self, symbols: list[str]) -> list[str]:
        """Cache whatever Alpha Vantage returns; hand back what it did not.

        Never raises. A failure here — transport, quota, a key that is not
        entitled — must cost the user nothing but the FMP fallback, so every
        symbol is simply returned as still wanted.
        """
        try:
            rows = await self._alpha_vantage.get_bulk_quotes(symbols)
        except Exception:  # noqa: BLE001
            _log.exception("live_quote_service: Alpha Vantage quotes failed; using FMP")
            return symbols
        fetched_at = time.monotonic()
        checked_at = time.time()
        wanted = set(symbols)
        returned: set[str] = set()
        for row in rows:
            sym = row.get("symbol")
            # Only what was asked for: a provider answering with extra or
            # renamed symbols must not write into unrelated cache entries.
            if sym not in wanted:
                continue
            previous = self._cache.get(sym)
            self._cache[sym] = LiveQuote(
                symbol=sym,
                price=row["price"],
                change=row["change"],
                change_percent=row["change_percent"],
                day_high=row.get("day_high"),
                day_low=row.get("day_low"),
                volume=_maybe_int(row.get("volume")),
                # AV's quote has no company fields; keep what FMP gave us.
                market_cap=previous.market_cap if previous else None,
                name=previous.name if previous else None,
                exchange=previous.exchange if previous else None,
                fetched_at=fetched_at,
                checked_at=checked_at,
                as_of=row.get("as_of"),
                source="alpha_vantage",
            )
            returned.add(sym)
        return [s for s in symbols if s not in returned]

    async def _fetch_stale(self, stale: list[str]) -> None:
        """Wait until every symbol in *stale* has been asked of FMP once.

        A symbol somebody is already waiting on is joined rather than asked
        for again; the rest go on the queue for the next FMP call. Raises
        what FMP raised if a call carrying one of this caller's symbols
        failed, as a direct call would have.
        """
        loop = asyncio.get_running_loop()
        pending = self._pending.get()
        waits: list["asyncio.Future[None]"] = []
        for sym in dict.fromkeys(stale):
            future = pending.waiting.get(sym)
            if future is None:
                future = loop.create_future()
                future.add_done_callback(_seen)
                pending.waiting[sym] = future
                pending.queue.append(sym)
            waits.append(future)
        if pending.fetcher is None or pending.fetcher.done():
            pending.fetcher = loop.create_task(self._drain(pending))
        # Shielded: a caller that gives up must not cancel a future other
        # callers are waiting on.
        outcomes = await asyncio.gather(*(asyncio.shield(f) for f in waits), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                raise outcome

    async def _drain(self, pending: _Pending) -> None:
        """Send the queue to the provider, one batch at a time, until it is empty.

        One at a time is deliberate: FMP's burst limiter drops symbols from
        concurrent quote requests (apps/api/CLAUDE.md, trap 15). Whatever is
        asked for while a batch is out simply rides on the next one.

        A batch goes to Alpha Vantage first when that source is switched on
        and the batch is small enough, and to FMP for whatever is left.
        """
        try:
            while pending.queue:
                batch, pending.queue = pending.queue, []
                failure: Optional[Exception] = None
                try:
                    remaining = batch
                    if self._uses_alpha_vantage(len(batch)):
                        remaining = await self._fetch_from_alpha_vantage(batch)
                    returned: set[str] = set(batch) - set(remaining)
                    if remaining:
                        raw = await self._fmp.get_quotes_batch(remaining)
                        fetched_at = time.monotonic()
                        checked_at = time.time()
                        for item in raw:
                            quote = _from_fmp_payload(item, fetched_at, checked_at)
                            if quote is None:
                                continue
                            self._cache[quote.symbol] = quote
                            returned.add(quote.symbol)
                    missing = set(batch) - returned
                    if missing:
                        # Log but don't fail — caller already treats missing as "no data".
                        _log.info("live_quote_service: FMP returned no data for %s", sorted(missing))
                except Exception as exc:  # noqa: BLE001 — handed to the callers waiting on this batch
                    failure = exc
                for sym in batch:
                    future = pending.waiting.pop(sym, None)
                    if future is None or future.done():
                        continue
                    if failure is None:
                        future.set_result(None)
                    else:
                        future.set_exception(failure)
        finally:
            # Only reached with work left if this task was cancelled or broke:
            # nobody may be left waiting on a call that will never be made.
            for sym in pending.queue:
                future = pending.waiting.pop(sym, None)
                if future is not None and not future.done():
                    future.cancel()
            pending.queue = []


def _from_fmp_payload(
    raw: dict, fetched_at: float, checked_at: Optional[float] = None
) -> Optional[LiveQuote]:
    """Build a LiveQuote from one FMP /stable/quote response item.

    FMP's response field names vary slightly across endpoint variants. We
    pick the most reliable signals and tolerate missing optionals.
    """
    if not isinstance(raw, dict):
        return None
    sym = raw.get("symbol")
    price = raw.get("price")
    if not sym or price is None:
        return None
    try:
        return LiveQuote(
            symbol=sym.upper(),
            price=float(price),
            change=float(raw.get("change") or 0.0),
            change_percent=float(raw.get("changesPercentage") or raw.get("changePercentage") or 0.0),
            day_high=_maybe_float(raw.get("dayHigh")),
            day_low=_maybe_float(raw.get("dayLow")),
            volume=_maybe_int(raw.get("volume")),
            market_cap=_maybe_float(raw.get("marketCap")),
            name=raw.get("name"),
            exchange=raw.get("exchange"),
            fetched_at=fetched_at,
            checked_at=checked_at,
            # FMP stamps the quote with the last trade, in epoch seconds.
            as_of=_maybe_float(raw.get("timestamp")),
            source="fmp",
        )
    except (TypeError, ValueError):
        return None


def _maybe_float(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _maybe_int(v) -> Optional[int]:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


# Module-level singleton — routes import this directly.
live_quote_service = LiveQuoteService()
