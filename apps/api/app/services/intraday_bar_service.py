"""PRD-16c-1 — IntradayBarService.

Cache-fronted intraday bar fetcher. The composer-driven custom_build
strategies opt into intraday backtest + live monitoring; this service
is the single point of access for the underlying bar data.

Three responsibilities:

  1. `get_bars(db, symbol, resolution, start, end)` — return a pandas
     DataFrame indexed by datetime spanning [start, end]. Checks the
     `intraday_bars` cache first; fetches from AV to fill gaps; writes
     the fresh bars back. Returns the combined frame.

  2. `ensure_recent_bars(db, symbol, resolution, lookback_minutes)` —
     refresh the most recent N minutes from AV unconditionally. Used by
     the intraday monitor cron (PRD-16c-3) for the "what's happening
     right now" path. Returns the freshly-fetched frame.

  3. Internal cache plumbing — read existing rows; identify time gaps;
     write fresh rows; tolerate concurrent writes idempotently via the
     composite-PK upsert.

Distinct from `LiveQuoteService` (in-process 30s cache of "right-now"
quotes) and `PriceDataService` (EOD daily bars via AV's
`TIME_SERIES_DAILY_ADJUSTED`). All three coexist; intraday is the
medium-term scale between them.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.models.intraday_bar import IntradayBar
from app.services.alpha_vantage import AlphaVantageClient, AlphaVantageError


VALID_RESOLUTIONS = frozenset({"5min", "15min", "30min", "60min"})

# Minutes per resolution — used to identify gaps.
_RESOLUTION_MINUTES = {"5min": 5, "15min": 15, "30min": 30, "60min": 60}


class IntradayBarService:
    """Public surface — instantiate without args; caller passes db each
    call so the service stays stateless and test-friendly."""

    def __init__(
        self,
        client: Optional[AlphaVantageClient] = None,
    ):
        self._client = client or AlphaVantageClient()

    # ── Public methods ─────────────────────────────────────────────────────

    async def get_bars(
        self,
        db: Session,
        symbol: str,
        resolution: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return cached + fetched bars for [start, end] as a pandas
        DataFrame indexed by `bar_time`. Columns: open / high / low /
        close / volume.

        Caches misses by fetching the AV-default 100-bar window
        (`outputsize=compact`) when the requested range is recent, or
        `outputsize=full` for longer ranges. Aggressive — fetches the
        full AV window even when only a few bars are missing; AV's
        intraday endpoint returns the same payload either way so a
        bigger response is free.

        Returns empty DataFrame when the symbol has no AV data + no
        cached bars."""
        if resolution not in VALID_RESOLUTIONS:
            raise ValueError(
                f"Invalid resolution '{resolution}'. "
                f"Must be one of {sorted(VALID_RESOLUTIONS)}."
            )
        symbol = symbol.upper()

        # 1. Read what's already cached in the window.
        cached = self._read_cached(db, symbol, resolution, start, end)

        # 2. Decide if we need a fresh fetch. Heuristic: if the cache
        # has < 2 bars in the window, or the cache's last bar is older
        # than 2 * resolution, fetch.
        need_fetch = self._needs_fetch(cached, resolution, end)

        if need_fetch:
            outputsize = "full" if (end - start) > timedelta(days=2) else "compact"
            try:
                fresh = await self._client.fetch_intraday_bars(
                    symbol=symbol,
                    interval=resolution,
                    outputsize=outputsize,
                )
                if fresh:
                    self._write_bars(db, symbol, resolution, fresh)
                    # Re-read the merged cache.
                    cached = self._read_cached(db, symbol, resolution, start, end)
            except AlphaVantageError:
                # Fall back to whatever's in cache (possibly empty). The
                # composer surfaces the empty result; the monitor cron
                # logs + skips this tick.
                pass

        if not cached:
            return pd.DataFrame()
        return _rows_to_frame(cached)

    async def ensure_recent_bars(
        self,
        db: Session,
        symbol: str,
        resolution: str,
        lookback_minutes: int = 120,
    ) -> pd.DataFrame:
        """For the monitor cron (PRD-16c-3): unconditionally refresh the
        last `lookback_minutes` of bars from AV and return the result.
        Always re-fetches — the cache is for `get_bars`'s read path."""
        if resolution not in VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution '{resolution}'.")
        symbol = symbol.upper()
        try:
            fresh = await self._client.fetch_intraday_bars(
                symbol=symbol,
                interval=resolution,
                outputsize="compact",
            )
        except AlphaVantageError:
            return pd.DataFrame()
        if not fresh:
            return pd.DataFrame()
        self._write_bars(db, symbol, resolution, fresh)
        # Read back the trailing N minutes of cached bars.
        cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        recent = self._read_cached(db, symbol, resolution, cutoff, datetime.utcnow())
        return _rows_to_frame(recent)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _read_cached(
        self,
        db: Session,
        symbol: str,
        resolution: str,
        start: datetime,
        end: datetime,
    ) -> list[IntradayBar]:
        rows = db.execute(
            select(IntradayBar)
            .where(IntradayBar.symbol == symbol)
            .where(IntradayBar.resolution == resolution)
            .where(IntradayBar.bar_time >= start)
            .where(IntradayBar.bar_time <= end)
            .order_by(IntradayBar.bar_time.asc())
        ).scalars().all()
        return list(rows)

    def _needs_fetch(
        self,
        cached: list[IntradayBar],
        resolution: str,
        end: datetime,
    ) -> bool:
        if len(cached) < 2:
            return True
        # If the freshest cached bar is older than 2 resolution intervals
        # behind `end`, we're stale.
        latest_cached = cached[-1].bar_time
        stale_threshold = end - timedelta(
            minutes=2 * _RESOLUTION_MINUTES[resolution]
        )
        return latest_cached < stale_threshold

    def _write_bars(
        self,
        db: Session,
        symbol: str,
        resolution: str,
        bars: list[dict],
    ) -> None:
        """Upsert via delete-then-insert on the composite PK. SQLite +
        Postgres both support it; ON CONFLICT would be Postgres-only.
        Delete is bounded to the bar_time range of the incoming batch,
        so concurrent writes for non-overlapping ranges don't collide.

        Caller commits — the service is stateless about transaction
        boundaries to let the cron / backtest engine batch writes."""
        if not bars:
            return
        bar_times = [b["bar_time"] for b in bars]
        min_time = min(bar_times)
        max_time = max(bar_times)
        # Wipe the range we're about to write.
        db.execute(
            delete(IntradayBar)
            .where(IntradayBar.symbol == symbol)
            .where(IntradayBar.resolution == resolution)
            .where(IntradayBar.bar_time >= min_time)
            .where(IntradayBar.bar_time <= max_time)
        )
        for bar in bars:
            db.add(IntradayBar(
                symbol=symbol,
                resolution=resolution,
                bar_time=bar["bar_time"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
                fetched_at=datetime.utcnow(),
            ))
        db.commit()


def _rows_to_frame(rows: list[IntradayBar]) -> pd.DataFrame:
    """Convert a list of IntradayBar ORM rows into a pandas DataFrame
    indexed by bar_time. Mirrors `PriceDataService.get_price_frame`'s
    output shape so downstream code can branch on resolution without
    re-mapping columns."""
    frame = pd.DataFrame(
        [
            {
                "bar_time": row.bar_time,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in rows
        ]
    )
    frame["bar_time"] = pd.to_datetime(frame["bar_time"])
    return frame.set_index("bar_time").sort_index()
