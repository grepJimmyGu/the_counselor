"""Daily signal_snapshot warm cron (PRD-23a §3.4).

Once post-close, recompute the screener's pre-warmed primitive cache for the
S&P 500 universe from cached `price_bars`. Any composed reading is then a
cheap boolean filter over the snapshot (the scan), so rank-by-backtest only
ever touches the matched subset.

Event-loop safety (the two outage traps this file's CLAUDE.md warns about):
- Trap #21: APScheduler runs this in a worker thread; `asyncio.run` gives that
  thread its own loop, so the sync DB calls inside never block the main loop
  that serves `/health`.
- Trap #22: the warm path (`SignalSnapshotService` -> `PriceDataService` ->
  `PriceCacheService` -> `AlphaVantageClient`) holds NO shared asyncio
  primitives, and does NOT touch `live_quote_service` / `cn_overview_service`
  (the only two singletons that do), so nothing gets wedged to this thread's
  loop.
- Trap #20: failures `logger.exception` (with traceback), never `.warning`.

Gated by `SCREENER_SNAPSHOT_ENABLED` (default off) so registering the cron
adds zero production load until PRD-23b ships the screener UI — same
"register unconditionally, no-op when disabled" convention as
`health_monitor_job` in this codebase.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict

logger = logging.getLogger("livermore.screener.snapshot_job")


def _enabled() -> bool:
    return os.getenv("SCREENER_SNAPSHOT_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def _warm_sp500() -> Dict[str, int]:
    """Warm the daily snapshot for the full S&P 500 universe. Each symbol is a
    cache-hit price-frame read (bars are already warm by post-close) + local
    pandas compute, committed per symbol."""
    from app.data.sp500_tickers import SP500_TICKERS
    from app.db.session import SessionLocal
    from app.services.screener.signal_snapshot_service import SignalSnapshotService

    svc = SignalSnapshotService()
    with SessionLocal() as db:
        return await svc.warm_universe(db, sorted(SP500_TICKERS))


def warm_signal_snapshot_job() -> None:
    """APScheduler entry point (sync wrapper around `asyncio.run`)."""
    if not _enabled():
        logger.info(
            "signal_snapshot_job: SCREENER_SNAPSHOT_ENABLED is off — skipping"
        )
        return
    try:
        summary = asyncio.run(_warm_sp500())
        logger.info("signal_snapshot_job complete: %s", summary)
    except Exception:
        logger.exception("signal_snapshot_job failed")  # trap #20


# ── PRD-23c — intraday snapshot warm (the heavier, opt-in path) ──────────────


def _intraday_enabled() -> bool:
    return os.getenv("SCREENER_INTRADAY_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def _warm_sp500_intraday() -> Dict[str, int]:
    """Warm the INTRADAY snapshot for the S&P 500 (resolution='intraday').

    Unlike the daily warm (cache-hit `price_bars`), this fetches fresh intraday
    bars per symbol via `IntradayBarService` (FMP ~15-min) — much heavier, so
    it's behind its own flag + a market-hours cadence. Trap #22-safe:
    `IntradayBarService` holds no shared asyncio primitives (the same path the
    PRD-16c `monitor_active_positions` cron already uses safely)."""
    from app.data.sp500_tickers import SP500_TICKERS
    from app.db.session import SessionLocal
    from app.services.screener.signal_snapshot_service import SignalSnapshotService

    svc = SignalSnapshotService()
    with SessionLocal() as db:
        return await svc.warm_universe(db, sorted(SP500_TICKERS), resolution="intraday")


def warm_intraday_snapshot_job() -> None:
    """APScheduler entry point — intraday screener snapshot warm.

    Gated by `SCREENER_INTRADAY_ENABLED` (default off). WARNING before
    enabling: this fetches intraday bars for the ENTIRE S&P universe each tick
    — validate FMP rate limits + Railway disk headroom first (the universe-wide
    intraday fetch is the cost the daily warm deliberately avoids)."""
    if not _intraday_enabled():
        logger.info(
            "intraday snapshot warm: SCREENER_INTRADAY_ENABLED is off — skipping"
        )
        return
    try:
        summary = asyncio.run(_warm_sp500_intraday())
        logger.info("intraday snapshot warm complete: %s", summary)
    except Exception:
        logger.exception("intraday snapshot warm failed")  # trap #20
