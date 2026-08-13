"""Null the `symbols.dividend_yield` values that cannot be yields.

**Why there is anything to clean.** The column holds a fraction — 0.0116 is
SPY's ~1.16%. An earlier version of `fmp_adapter` stored FMP's `lastDividend`
instead, which is annual *dollars per share*, so SPY went in as 7.525. That
was fixed at the adapter, and the Russell 3000 backfill rewrote the stocks —
but ETFs are not in the Russell 3000, so nothing ever rewrote them. On
2026-08-13 production still held 25 such rows:

    ALT 566.89   DIA 8.411   SPY 7.525   TLT 3.914   QQQ 3.034   IWM 2.656

A `min_dividend_yield` screen ranked every one of them above every real payer.

**Nulls rather than rescales.** 7.525 / 100 would present SPY as a confident
7.5% yielder when the real figure is ~1.16% — a wrong number that looks right,
which is the failure this column already shipped once. A NULL simply drops the
name out of a min-yield screen until the next fundamentals refresh writes a
real value through `sane_dividend_yield`.

**This is optional hygiene, not the fix.** `sane_dividend_yield` stops new bad
rows and the screener's read guard stops the existing ones from being reported,
so the user-visible bug is closed by deploying. This just tidies the data.

    python3 scripts/fix_dividend_yield_units.py            # dry run, lists them
    python3 scripts/fix_dividend_yield_units.py --apply    # writes

Needs `DATABASE_URL` pointed at the target database.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, update  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.symbol import SymbolCache  # noqa: E402
from app.services.fundamental_service import MAX_PLAUSIBLE_YIELD  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = db.execute(
            select(SymbolCache.symbol, SymbolCache.name, SymbolCache.dividend_yield)
            .where(SymbolCache.dividend_yield.isnot(None))
            .where(SymbolCache.dividend_yield >= MAX_PLAUSIBLE_YIELD)
            .order_by(SymbolCache.dividend_yield.desc())
        ).all()

        if not rows:
            print("nothing to fix — every stored yield is below 1.0")
            return 0

        print(f"{len(rows)} rows hold a value that cannot be a yield:\n")
        for symbol, name, value in rows:
            print(f"  {symbol:8s} {value:>14.5f}   {(name or '')[:40]}")

        if not args.apply:
            print("\ndry run. re-run with --apply to null these.")
            return 0

        db.execute(
            update(SymbolCache)
            .where(SymbolCache.dividend_yield.isnot(None))
            .where(SymbolCache.dividend_yield >= MAX_PLAUSIBLE_YIELD)
            .values(dividend_yield=None)
        )
        db.commit()
        print(f"\nnulled {len(rows)} rows. The next fundamentals refresh will "
              "write real fractions through sane_dividend_yield().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
