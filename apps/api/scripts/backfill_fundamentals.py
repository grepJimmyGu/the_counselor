"""Repopulate `symbols.pe_ratio` AND `symbols.dividend_yield` for the Russell 3000.

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

It ALSO rewrites `dividend_yield`, for a subtler reason. PR #283 corrected the
adapter to derive a real yield (`lastDividend / price`) instead of storing the
raw dollar payout — but that only takes effect for a symbol when its profile
next refreshes, one company-page view at a time. Left alone, the column would
hold a MIX of scales: refreshed symbols as fractions (0.007), everything else
still as dollars (3.56). A "yield above 4%" screen would blend the two and
return an unpredictable set — worse than being uniformly wrong. So this script
refreshes both fields together, from source, in one pass.

Recomputing from the profile (rather than dividing the stored value by price)
keeps the script IDEMPOTENT: re-running derives the same answer from the same
upstream numbers, where an in-place division would halve the value every run.

Scope is the Russell 3000 because it is a superset of the S&P 500, so it covers
both universes the home screener can target. Serial calls, per trap #15 — FMP
burst-rate-limits concurrent requests and drops late-alphabet symbols.

Idempotent: symbols that already have a P/E are skipped, so a re-run after an
interruption resumes rather than restarting. Only UPDATEs existing rows — no
inserts, so no meaningful disk growth (trap #10 does not apply).

Usage (from `apps/api/`):
    DATABASE_URL=$(railway variables --service Postgres --json | jq -r '.DATABASE_PUBLIC_URL') \\
    FINANCIAL_MODELING_PREP_API_KEY=... python scripts/backfill_fundamentals.py --dry-run --limit 20

    DATABASE_URL=... FINANCIAL_MODELING_PREP_API_KEY=... python scripts/backfill_fundamentals.py

The key name is `FINANCIAL_MODELING_PREP_API_KEY` (what `Settings` reads), NOT
`FMP_API_KEY` — passing the latter silently configures nothing and every symbol
fails once the run starts.

Expected runtime: ~2,545 symbols × 2 calls at roughly 4/s → 20-25 minutes.
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

logger = logging.getLogger("backfill_fundamentals")

# Gap between calls. FMP burst-rate-limits; `get_quotes_batch` runs strictly
# serial for the same reason. key-metrics-ttm has no batch form, so this is one
# call per symbol either way.
_DELAY_SECONDS = 0.25
# Commit every N updates so an interrupted run keeps its progress.
_COMMIT_EVERY = 50
# Symbols already written, one per line. Without this a resume restarts from
# "A" — and since target selection deliberately can't skip on "already has a
# P/E" (a dollars-per-share yield is indistinguishable from a small fraction),
# there is nothing else to resume from.
_DEFAULT_STATE_FILE = "/tmp/backfill_fundamentals_done.txt"


def _load_done(path: str) -> set:
    try:
        with open(path) as fh:
            return {line.strip() for line in fh if line.strip()}
    except FileNotFoundError:
        return set()


def _targets(db, limit: Optional[int], done: Optional[set] = None) -> List[str]:
    """Every Russell 3000 symbol present in `symbols`.

    Deliberately not "only the ones missing a P/E": a dollars-per-share
    `dividend_yield` is indistinguishable from a plausible fraction for small
    payouts, so there is no safe "already fixed?" predicate to skip on. The
    pass recomputes from source and is idempotent, so re-running is harmless.
    """
    universe = set(RUSSELL3000_TICKERS)
    rows = db.execute(select(SymbolCache.symbol)).all()
    out = sorted(
        sym for (sym,) in rows if sym in universe and sym not in (done or set())
    )
    return out[:limit] if limit else out


async def _run(dry_run: bool, limit: Optional[int], state_file: str) -> int:
    adapter = FMPAdapter()
    updated = failed = skipped = 0
    done = _load_done(state_file)
    if done:
        logger.info("resuming — %d symbols already done per %s", len(done), state_file)

    with SessionLocal() as db:
        targets = _targets(db, limit, done)
        logger.info("%d Russell 3000 symbols need a P/E", len(targets))
        if dry_run:
            logger.info("DRY RUN — first 20: %s", targets[:20])
            return 0

        for i, sym in enumerate(targets, 1):
            row = db.get(SymbolCache, sym)
            if row is None:
                await asyncio.sleep(_DELAY_SECONDS)
                continue

            wrote = False

            # P/E — from key-metrics (the profile never carries it).
            try:
                metrics = await adapter.get_key_metrics(sym)
                if metrics.pe_ratio is not None:
                    row.pe_ratio = metrics.pe_ratio
                    wrote = True
                else:
                    # Legitimately absent — an unprofitable company has no P/E.
                    skipped += 1
            except Exception as exc:
                # Don't let one bad symbol kill a 2,500-symbol run.
                failed += 1
                logger.warning("%s: key-metrics failed (%s)", sym, exc)
            await asyncio.sleep(_DELAY_SECONDS)

            # Dividend yield + price — from the profile, via the corrected
            # adapter, so the stored value is a fraction rather than dollars.
            try:
                profile = await adapter.get_profile(sym, include_peers=False)
                row.dividend_yield = profile.dividend_yield
                if profile.price is not None:
                    row.price = profile.price
                wrote = True
            except Exception as exc:
                failed += 1
                logger.warning("%s: profile failed (%s)", sym, exc)

            if wrote:
                updated += 1

            # Checkpoint ONLY on a symbol that actually wrote something.
            #
            # Recording unconditionally meant a symbol whose calls both failed
            # — FMP rate limits do this intermittently — was marked done and
            # never retried on any later run. Silent permanent data loss, at
            # roughly the failure rate (~2% observed mid-run). A crash
            # mid-symbol still re-does it, which was the original intent.
            if wrote and not dry_run:
                with open(state_file, "a") as fh:
                    fh.write(sym + "\n")

            if i % _COMMIT_EVERY == 0:
                db.commit()
                logger.info(
                    "%d/%d — %d updated, %d no-P/E, %d failed",
                    i, len(targets), updated, skipped, failed,
                )
            await asyncio.sleep(_DELAY_SECONDS)

        db.commit()

    logger.info(
        "DONE — %d symbols updated, %d had no P/E (unprofitable), %d call(s) failed",
        updated, skipped, failed,
    )
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="List targets, write nothing.")
    ap.add_argument("--limit", type=int, default=None, help="Cap the number of symbols (for a smoke run).")
    ap.add_argument("--state-file", default=_DEFAULT_STATE_FILE,
                    help="Checkpoint of completed symbols; delete it to force a full re-run.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs the full request URL at INFO — which includes `?apikey=...`.
    # Over a 2,500-symbol run that wrote the FMP key into the log thousands of
    # times, and the log is world-readable. Nothing here needs per-request
    # logging; our own progress lines are the useful signal.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL is not set — refusing to run against the default local DB.")
        return 2

    # Check the FMP key BEFORE starting. --dry-run makes no API calls, so it
    # can't surface a missing key; without this you'd discover it one failed
    # symbol at a time, 2,500 warnings deep.
    if not args.dry_run:
        from app.core.config import get_settings

        if not get_settings().financial_modeling_prep_api_key:
            logger.error(
                "FINANCIAL_MODELING_PREP_API_KEY is not configured — every symbol "
                "would fail. Note the name: NOT 'FMP_API_KEY'."
            )
            return 2

    asyncio.run(_run(args.dry_run, args.limit, args.state_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
