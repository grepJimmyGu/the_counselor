"""Live quote cache (2026-05-21).

In-process cache for live stock quotes from FMP. Single source of truth for
every "live price" surface on the frontend — the ticker bar, stock detail
pages, workspace strategy preview, Market Pulse, and the community feed.

Design (one diagram for the file):

    page A asks for [NVDA, AAPL]  ┐
    page B asks for [AAPL, MSFT]  ┼──> get_quotes()
    page C asks for [NVDA]        ┘        │
                                            ├── split fresh vs stale
                                            ├── for each stale symbol:
                                            │     acquire per-symbol Lock
                                            │     check cache again (lock may
                                            │     have been waiting on the
                                            │     fetch that just populated it)
                                            │     fetch FMP if still stale
                                            │     release Lock
                                            └── return merged result

Properties:
  - 30s TTL by default — any quote within 30s of fetch is reused. A caller
    may ask for fresher with `max_age`; /api/live/quotes does, from
    `settings.live_quote_ttl_seconds`.
  - Optional Alpha Vantage real-time source in front of FMP
    (`settings.live_quote_provider == "alpha_vantage"`), for small requests
    only; anything it does not return is fetched from FMP as before.
  - Per-symbol asyncio.Lock prevents the thundering-herd case where two
    concurrent requests both miss cache for the same symbol.
  - Batches across symbols when multiple stale symbols arrive in one call
    (a page with 12 tickers = 1 FMP call, not 12).
  - Single-process (cache lives in this Python module's globals). If we ever
    scale Railway to multi-worker, swap the _cache dict for Redis.

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
from dataclasses import dataclass
from typing import Optional

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


class LiveQuoteService:
    """Holds the cache + locks. Instantiated as a module-level singleton at
    the bottom of this file; routes import `live_quote_service`."""

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
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, symbol: str) -> asyncio.Lock:
        """One Lock per symbol, created on demand. Cheap — Locks are tiny."""
        lock = self._locks.get(symbol)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[symbol] = lock
        return lock

    def _is_fresh(self, q: LiveQuote, now: float, max_age: float = TTL_SECONDS) -> bool:
        return (now - q.fetched_at) < max_age

    def _uses_alpha_vantage(self, count: int) -> bool:
        """Alpha Vantage first, for requests it can answer in one call.

        Market Pulse asks for ~500 symbols at a time; sending those to AV
        would spend five calls per refresh against a per-minute quota that
        the watch-list traffic also draws on. Those stay on FMP.
        """
        provider = self._provider_override or get_settings().live_quote_provider
        return (provider or "").strip().lower() == "alpha_vantage" and count <= BULK_LIMIT

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

        await self._fetch_and_cache_stale(stale, now, ttl)

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

    async def _fetch_and_cache_stale(
        self, stale: list[str], now: float, ttl: float = TTL_SECONDS
    ) -> None:
        """Fetch all *stale* symbols in a single FMP call, then cache them.

        Wraps with per-symbol locks so two concurrent callers asking for the
        same stale symbol don't both fire an FMP request. The lock-then-check
        pattern means the second caller, after waiting, finds the cache
        populated and skips the redundant fetch.
        """
        # Acquire all locks first (sorted to avoid ordering deadlock between
        # callers asking for overlapping sets).
        ordered = sorted(set(stale))
        locks = [self._lock_for(s) for s in ordered]
        for lock in locks:
            await lock.acquire()
        try:
            # Recheck: another coroutine that held the locks may have just
            # populated the cache for some of these.
            now2 = time.monotonic()
            still_stale = [
                s for s in ordered
                if not (self._cache.get(s) and self._is_fresh(self._cache[s], now2, ttl))
            ]
            if not still_stale:
                return

            asked = still_stale
            if self._uses_alpha_vantage(len(still_stale)):
                still_stale = await self._fetch_from_alpha_vantage(still_stale)
                if not still_stale:
                    return

            raw = await self._fmp.get_quotes_batch(still_stale)
            fetched_at = time.monotonic()
            checked_at = time.time()
            returned: set[str] = set(asked) - set(still_stale)
            for item in raw:
                quote = _from_fmp_payload(item, fetched_at, checked_at)
                if quote is None:
                    continue
                self._cache[quote.symbol] = quote
                returned.add(quote.symbol)

            missing = set(asked) - returned
            if missing:
                # Log but don't fail — caller already treats missing as "no data".
                _log.info(
                    "live_quote_service: FMP returned no data for %s",
                    sorted(missing),
                )
        finally:
            for lock in locks:
                lock.release()


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
