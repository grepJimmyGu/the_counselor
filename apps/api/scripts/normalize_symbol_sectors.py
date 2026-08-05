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

from app.data.sectors import is_placeholder, normalize_sector  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.symbol import SymbolCache  # noqa: E402

# The seed bug that produced the "nan" sector labels hit these columns on
# adjacent lines too — `GET /api/screener/filters` currently offers "nan" as a
# selectable *industry*. They only need the placeholder cleared, not aliasing.
_SIBLING_COLUMNS = (
    ("industry", SymbolCache.industry),
    ("exchange", SymbolCache.exchange),
)

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


def _clear_placeholders(db: Session, name: str, column, dry_run: bool) -> int:
    """NULL out NaN-ish placeholder labels in a sibling metadata column."""
    rows = db.execute(
        select(column, func.count()).where(column.isnot(None)).group_by(column)
    ).all()
    junk = [(value, count) for value, count in rows if is_placeholder(value)]
    if not junk:
        log.info("%s: clean, nothing to clear.", name)
        return 0

    for value, count in junk:
        log.info("  %s %-20s -> NULL (%d rows)", name, _label(value), count)
    if dry_run:
        return sum(count for _, count in junk)

    cleared = 0
    for value, _count in junk:
        try:
            result = db.execute(
                update(SymbolCache).where(column == value).values(**{name: None})
            )
            db.commit()
            cleared += result.rowcount or 0
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed clearing %s %s: %r", name, _label(value), exc)
            db.rollback()
            continue
    return cleared


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

        updated = 0
        if not plan:
            log.info("sector: already canonical, nothing to rewrite.")
        else:
            for label, target, count in plan:
                log.info("  %-26s -> %-26s (%d rows)", _label(label), _label(target), count)

            if dry_run:
                updated += sum(count for _, _, count in plan)
            else:
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

        # The same seed bug polluted these columns; 'nan' is currently offered
        # as a selectable *industry* by GET /api/screener/filters.
        for name, column in _SIBLING_COLUMNS:
            updated += _clear_placeholders(db, name, column, dry_run)

        if dry_run:
            log.info("--dry-run: would rewrite %d rows (no changes made)", updated)
            return updated

        after = _distinct_sectors(db)
        log.info("Done — rewrote %d rows.", updated)
        log.info("After: %d distinct sector labels", len(after))
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
