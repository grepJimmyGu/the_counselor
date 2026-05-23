"""Backfill ^GSPC (S&P 500 index) daily OHLCV into `price_bars`.

Run this once after PR-5 ships to populate the index series the sector
comparison chart now prefers (`sector_comparison_service.py`). Until
this runs, the service transparently falls back to SPY + logs a WARN.

Usage (run from the `apps/api/` directory so `app/` is on the import path):
    cd apps/api
    DATABASE_URL=$(railway variables --service the_counselor --json | jq -r '.DATABASE_URL') \\
        FINANCIAL_MODELING_PREP_API_KEY=$(railway variables --service the_counselor --json | jq -r '.FINANCIAL_MODELING_PREP_API_KEY') \\
        python scripts/backfill_gspc.py                  # 4y default
    python scripts/backfill_gspc.py --years 6            # custom window
    python scripts/backfill_gspc.py --dry-run            # check without writing

Requires:
    DATABASE_URL              the target DB (Postgres in prod, SQLite ok locally)
    FINANCIAL_MODELING_PREP_API_KEY    set so FMP calls succeed

Notes:
    * Idempotent: skips dates that already have a `^GSPC` bar.
    * No volume data on index symbols — we store `volume=0` (index has
      no shares-traded number; the `price_bars` NOT NULL constraint on
      volume forces a non-null value but it's a "no signal" placeholder).
    * Source tag is `'backfill_gspc'` so the rows are distinguishable
      from the daily warmup pipeline (which would not pick up index
      symbols since they aren't on Alpha Vantage's free tier).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

# The script lives at `apps/api/scripts/`; the application package is
# `apps/api/app/`. Add the parent (`apps/api/`) to `sys.path` so
# `from app.* import ...` resolves whether the user runs the script as
# `python scripts/backfill_gspc.py` or via a different entry point.
_API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from sqlalchemy import select  # noqa: E402 — must follow sys.path tweak

from app.db.session import SessionLocal  # noqa: E402
from app.models.price_bar import PriceBar  # noqa: E402
from app.services.fmp_client import (  # noqa: E402
    FMPClient,
    FMPError,
    FMPNotConfiguredError,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backfill_gspc")

SYMBOL = "^GSPC"
SOURCE = "backfill_gspc"


async def fetch_gspc_history(years: int) -> list[dict]:
    """Pull `years` of ^GSPC EOD bars from FMP. Returns the raw FMP rows."""
    fmp = FMPClient()
    to_date = date.today()
    from_date = to_date - timedelta(days=int(years * 365.25))
    log.info(
        "Fetching %s history from FMP: %s → %s (%d years)",
        SYMBOL, from_date.isoformat(), to_date.isoformat(), years,
    )
    try:
        rows = await fmp.get_historical_eod(
            SYMBOL, from_date.isoformat(), to_date.isoformat(),
        )
    except FMPNotConfiguredError:
        log.error(
            "FINANCIAL_MODELING_PREP_API_KEY is not set. Cannot backfill."
        )
        return []
    except FMPError as exc:
        log.error("FMP fetch failed: %r", exc)
        return []
    log.info("FMP returned %d rows for %s", len(rows), SYMBOL)
    return rows


def _row_to_pricebar(row: dict) -> Optional[PriceBar]:
    """Convert one FMP row to a PriceBar instance. Returns None if the
    row is malformed."""
    try:
        trading_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        return PriceBar(
            symbol=SYMBOL,
            trading_date=trading_date,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            adjusted_close=float(row.get("adjClose", row["close"])),
            # Indices don't have volume; the schema requires NOT NULL.
            volume=int(row.get("volume") or 0),
            dividend_amount=0.0,
            split_coefficient=1.0,
            source=SOURCE,
            fetched_at=datetime.utcnow(),
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("Skipping malformed FMP row %r (%r)", row, exc)
        return None


def _existing_dates(db) -> set:
    """All dates we already have a `^GSPC` bar for. Skip these on insert."""
    rows = db.execute(
        select(PriceBar.trading_date).where(PriceBar.symbol == SYMBOL)
    ).fetchall()
    return {r[0] for r in rows}


def backfill(years: int, dry_run: bool) -> int:
    """Run the backfill. Returns the number of bars inserted (or that
    would be inserted in dry-run mode)."""
    rows = asyncio.run(fetch_gspc_history(years))
    if not rows:
        log.warning("Nothing to insert.")
        return 0

    db = SessionLocal()
    try:
        existing = _existing_dates(db)
        log.info("DB already has %d ^GSPC bars; skipping those dates", len(existing))

        new_bars: list[PriceBar] = []
        for row in rows:
            bar = _row_to_pricebar(row)
            if bar is None:
                continue
            if bar.trading_date in existing:
                continue
            new_bars.append(bar)

        log.info("Prepared %d new ^GSPC bars to insert", len(new_bars))
        if dry_run:
            log.info("--dry-run: not committing")
            return len(new_bars)

        db.add_all(new_bars)
        db.commit()
        log.info("Committed %d bars to price_bars (source=%s)", len(new_bars), SOURCE)
        return len(new_bars)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill ^GSPC into price_bars")
    parser.add_argument(
        "--years", type=int, default=4,
        help="Years of history to fetch (default: 4)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch + count, but don't write to DB",
    )
    args = parser.parse_args()

    inserted = backfill(args.years, args.dry_run)
    if inserted == 0 and not args.dry_run:
        log.error("No bars inserted — check FMP key + logs above.")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
