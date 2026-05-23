"""Backfill the full S&P 500 constituent list into `price_bars` (and
`symbols`) so the Market Pulse Top Movers pool draws from the whole
SPX universe instead of the curated top-30 warmup hardcoded in
`_TOP_US_STOCKS`.

Companion to PR-8 (which switched `_build_top_assets` to filter against
`SP500_TICKERS`). Without this backfill, the filter is correct but
constrained by the underlying ingestion — only ~30 SPX names have
price_bars in production, so the pool stays at ~30 even after the
filter is in place.

This script:
  1. Loads `app.data.sp500_tickers.SP500_TICKERS`
  2. For each ticker not already in `symbols`, inserts a SymbolCache
     row (name=symbol placeholder; sector/industry populated lazily
     by FMP via /stocks/[ticker] page-load)
  3. For each ticker, calls `PriceCacheService.ensure_history()` with
     a 3-year lookback. Skips if data is already fresh.
  4. Logs progress every 25 symbols; errors are non-fatal (logged +
     skipped).

Idempotent on re-run. Subsequent invocations skip symbols that already
have fresh bars + symbol rows — turns into a few hundred fast DB
checks. AV rate-limit aware (PriceCacheService handles backoff).

Usage (from `apps/api/`):
    DATABASE_URL=$(railway variables --service Postgres --json | jq -r '.DATABASE_PUBLIC_URL') \\
    ALPHA_VANTAGE_API_KEY=$(railway variables --service the_counselor --json | jq -r '.ALPHA_VANTAGE_API_KEY') \\
    python scripts/backfill_sp500_universe.py

    python scripts/backfill_sp500_universe.py --dry-run    # count only

Expected runtime against an empty DB: ~7-10 minutes for ~470 names
on AV Premium (75 calls/min). Subsequent runs against a populated
DB: <30 seconds (all cache hits).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta

_API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from app.data.sp500_tickers import SP500_TICKERS  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.symbol import SymbolCache  # noqa: E402
from app.services.alpha_vantage import AlphaVantageClient  # noqa: E402
from app.services.price_cache_service import PriceCacheService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_sp500")

# Quiet down httpx's per-request noise — we log our own progress
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _ensure_symbol_row(db, symbol: str, now: datetime) -> None:
    """Insert a SymbolCache row for `symbol` if missing. Uses the
    symbol itself as a placeholder name + NULL sector. The proper
    name + sector backfill happens organically via FMP profile
    lookup the first time a user clicks through to /stocks/<symbol>."""
    existing = db.get(SymbolCache, symbol)
    if existing is not None:
        return
    db.add(SymbolCache(
        symbol=symbol,
        name=symbol,
        instrument_type="Equity",
        region="US",
        is_active=True,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    ))
    db.commit()


async def backfill(dry_run: bool, log_every: int = 25) -> int:
    """Backfill the full SP500 universe. Returns the number of symbols
    that ended the run with fresh bars."""
    universe = sorted(SP500_TICKERS)
    log.info("Loaded %d SP500 tickers", len(universe))

    if dry_run:
        log.info("--dry-run: would backfill %d symbols", len(universe))
        return len(universe)

    client = AlphaVantageClient()
    svc = PriceCacheService(client)
    db = SessionLocal()
    required_from = date.today() - timedelta(days=365 * 3)
    now = datetime.utcnow()

    loaded = 0
    failed: list[str] = []
    skipped_fresh = 0

    try:
        for i, symbol in enumerate(universe, 1):
            try:
                await _ensure_symbol_row(db, symbol, now)
            except Exception as exc:  # noqa: BLE001
                log.warning("Symbol row insert failed for %s: %r", symbol, exc)
                db.rollback()
                failed.append(symbol)
                continue

            # ensure_history skips if cached + fresh + covers required_from
            try:
                pre_latest = svc.get_latest_date(db, symbol)
                await svc.ensure_history(db, symbol, required_from, force=False)
                post_latest = svc.get_latest_date(db, symbol)
                if pre_latest == post_latest and pre_latest is not None:
                    skipped_fresh += 1
                loaded += 1
            except Exception as exc:  # noqa: BLE001
                # PriceCacheService.ensure_history already logs the AV error
                # detail; here we just count failures.
                log.warning("ensure_history failed for %s: %r", symbol, exc)
                failed.append(symbol)

            if i % log_every == 0:
                log.info(
                    "Progress: %d/%d processed · %d loaded · %d skipped-fresh · %d failed",
                    i, len(universe), loaded, skipped_fresh, len(failed),
                )

        log.info(
            "Done. %d loaded · %d already-fresh (skipped fetch) · %d failed",
            loaded, skipped_fresh, len(failed),
        )
        if failed:
            log.warning("Failed symbols (%d): %s", len(failed), failed[:20])
        return loaded
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill SP500 universe into price_bars")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no fetches")
    parser.add_argument("--log-every", type=int, default=25, help="Log progress every N symbols")
    args = parser.parse_args()

    loaded = asyncio.run(backfill(args.dry_run, args.log_every))
    sys.exit(0 if loaded > 0 else 1)


if __name__ == "__main__":
    main()
