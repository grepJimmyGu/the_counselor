"""Normalize `symbols.sector` onto the canonical GICS taxonomy.

SYMPTOM: `GET /api/screener/filters` returned 18 sector values — six alias pairs
naming the same sector ("Healthcare"/"Health Care", "Technology"/"Information
Technology", "Financials"/"Financial Services", "Consumer Cyclical"/"Consumer
Discretionary", "Consumer Defensive"/"Consumer Staples", "Basic
Materials"/"Materials") plus the literal string "nan" on 518 rows. Because
`ScreenerService.screen()` matches with exact `==`, picking one spelling
silently excluded every row stored under the other.

ROOT CAUSE: three writers populate `symbols.sector` in two different
vocabularies and none normalized on write (see `app/data/sectors.py`). The "nan"
rows come from `app/scripts/seed_symbols.py`, which built the value as
`str(row.get("sector") or "")[:120] or None` — but pandas represents a missing
cell as `float('nan')` and `bool(float('nan')) is True`, so the `or ""` guard
never fired and `str()` produced the literal label "nan".

FIX: `normalize_sector()` now runs at every write site. This script repairs the
rows written before that landed.

Works on DISTINCT labels rather than row-by-row, so it issues one UPDATE per
distinct spelling regardless of table size. Idempotent: a second run finds
nothing to change and reports 0 updated.

Usage (from `apps/api/`):
    DATABASE_URL=$(railway variables --service Postgres --json | jq -r '.DATABASE_PUBLIC_URL') \\
    python scripts/normalize_symbol_sectors.py --dry-run

    DATABASE_URL=... python scripts/normalize_symbol_sectors.py

Expected runtime: a few seconds (~18 distinct labels, one UPDATE each).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional, Tuple

_API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from sqlalchemy import func, select, update  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.data.sectors import normalize_sector  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.symbol import SymbolCache  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("normalize_sectors")


def _distinct_sectors(db: Session) -> List[Tuple[str, int]]:
    """Non-NULL sector labels with their row counts, largest first."""
    rows = db.execute(
        select(SymbolCache.sector, func.count())
        .where(SymbolCache.sector.isnot(None))
        .group_by(SymbolCache.sector)
        .order_by(func.count().desc())
    ).all()
    return [(label, count) for label, count in rows]


def _label(value: Optional[str]) -> str:
    return repr(value) if value is not None else "NULL"


def normalize_sectors(dry_run: bool) -> int:
    db = SessionLocal()
    try:
        before = _distinct_sectors(db)
        log.info(
            "Before: %d distinct labels over %d non-NULL rows",
            len(before), sum(n for _, n in before),
        )

        # (current_label, canonical_target, row_count) for labels that must change.
        # A canonical target is never itself a key here (normalize_sector is
        # idempotent), so these UPDATEs cannot cascade into each other.
        plan = [
            (label, normalize_sector(label), count)
            for label, count in before
            if normalize_sector(label) != label
        ]

        if not plan:
            log.info("Nothing to do — every label is already canonical.")
            return 0

        for label, target, count in plan:
            log.info("  %-26s -> %-26s (%d rows)", _label(label), _label(target), count)

        affected = sum(count for _, _, count in plan)
        if dry_run:
            log.info(
                "--dry-run: would rewrite %d rows across %d labels (no changes made)",
                affected, len(plan),
            )
            return affected

        updated = 0
        for label, target, _count in plan:
            try:
                result = db.execute(
                    update(SymbolCache)
                    .where(SymbolCache.sector == label)
                    .values(sector=target)
                )
                db.commit()
                updated += result.rowcount or 0
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed rewriting %s: %r", _label(label), exc)
                db.rollback()
                continue

        after = _distinct_sectors(db)
        log.info("Done — rewrote %d rows.", updated)
        log.info("After: %d distinct labels", len(after))
        for label, count in sorted(after):
            log.info("  %-26s %d", _label(label), count)
        return updated
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize symbols.sector onto the canonical GICS taxonomy."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the rewrite plan without touching any rows",
    )
    args = parser.parse_args()
    normalize_sectors(args.dry_run)
    # Exit 0 even when nothing changed — a clean re-run is success, not failure.
    sys.exit(0)


if __name__ == "__main__":
    main()
