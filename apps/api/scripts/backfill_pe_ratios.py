"""Populate `symbols.pe_ratio` for the Russell 3000 from FMP key-metrics.

SYMPTOM: every P/E screen matched nothing. `GET /api/screener/results?max_pe=60`
returned 0 of 16,832 symbols, and two of the nine live presets ("Top Value
Stocks", "Top Rated Stocks") showed `result_count: 0`. In the home Conditions
builder, the P/E and Value pills produced empty screens.

ROOT CAUSE: two compounding bugs, both fixed in the same PR as this script.
`fmp_adapter.get_profile` hardcodes `pe_ratio=None` (the value lives in
key-metrics, not the profile), and `FundamentalService._upsert_symbol` wrote
that None over the column on every cache refresh. `get_summary` opportunistically
merged a real P/E back in for symbols whose company page someone opened, but
the next profile refresh clobbered it again. Net effect: the column was
permanently null.

FIX: the clobber is guarded now, so P/E survives once written. This script does
the initial population, which is otherwise only reachable one company-page view
at a time.

Scope is the Russell 3000 because it is a superset of the S&P 500, so it covers
both universes the home screener can target. Serial calls, per trap #15 — FMP
burst-rate-limits concurrent requests and drops late-alphabet symbols.

Idempotent: symbols that already have a P/E are skipped, so a re-run after an
interruption resumes rather than restarting. Only UPDATEs existing rows — no
inserts, so no meaningful disk growth (trap #10 does not apply).

Usage (from `apps/api/`):
    DATABASE_URL=$(railway variables --service Postgres --json | jq -r '.DATABASE_PUBLIC_URL') \\
    FMP_API_KEY=... python scripts/backfill_pe_ratios.py --dry-run --limit 20

    DATABASE_URL=... FMP_API_KEY=... python scripts/backfill_pe_ratios.py

Expected runtime: ~2,545 symbols at roughly 4/s → 10-15 minutes.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.data.russell3000_tickers import RUSSELL3000_TICKERS  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.symbol import SymbolCache  # noqa: E402
from app.services.adapters.fmp_adapter import FMPAdapter  # noqa: E402

logger = logging.getLogger("backfill_pe")

# Gap between calls. FMP burst-rate-limits; `get_quotes_batch` runs strictly
# serial for the same reason. key-metrics-ttm has no batch form, so this is one
# call per symbol either way.
_DELAY_SECONDS = 0.25
# Commit every N updates so an interrupted run keeps its progress.
_COMMIT_EVERY = 50


def _targets(db, force: bool, limit: Optional[int]) -> List[str]:
    """Russell 3000 symbols present in `symbols` that still need a P/E."""
    universe = set(RUSSELL3000_TICKERS)
    rows = db.execute(
        select(SymbolCache.symbol, SymbolCache.pe_ratio)
    ).all()
    out = [
        sym
        for sym, pe in rows
        if sym in universe and (force or pe is None)
    ]
    out.sort()
    return out[:limit] if limit else out


async def _run(dry_run: bool, force: bool, limit: Optional[int]) -> int:
    adapter = FMPAdapter()
    updated = failed = skipped = 0

    with SessionLocal() as db:
        targets = _targets(db, force, limit)
        logger.info("%d Russell 3000 symbols need a P/E", len(targets))
        if dry_run:
            logger.info("DRY RUN — first 20: %s", targets[:20])
            return 0

        for i, sym in enumerate(targets, 1):
            try:
                metrics = await adapter.get_key_metrics(sym)
            except Exception as exc:
                # Don't let one bad symbol kill a 2,500-symbol run.
                failed += 1
                logger.warning("%s: key-metrics failed (%s)", sym, exc)
                await asyncio.sleep(_DELAY_SECONDS)
                continue

            pe = metrics.pe_ratio
            if pe is None:
                # Legitimately absent — an unprofitable company has no P/E.
                skipped += 1
            else:
                row = db.get(SymbolCache, sym)
                if row is not None:
                    row.pe_ratio = pe
                    updated += 1

            if i % _COMMIT_EVERY == 0:
                db.commit()
                logger.info(
                    "%d/%d — %d updated, %d no-P/E, %d failed",
                    i, len(targets), updated, skipped, failed,
                )
            await asyncio.sleep(_DELAY_SECONDS)

        db.commit()

    logger.info(
        "DONE — %d updated, %d had no P/E (unprofitable), %d failed",
        updated, skipped, failed,
    )
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="List targets, write nothing.")
    ap.add_argument("--force", action="store_true", help="Refresh even symbols that already have a P/E.")
    ap.add_argument("--limit", type=int, default=None, help="Cap the number of symbols (for a smoke run).")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL is not set — refusing to run against the default local DB.")
        return 2

    asyncio.run(_run(args.dry_run, args.force, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
