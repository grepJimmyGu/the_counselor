"""
Seed the symbols table from FinanceDatabase.

Populates ~8,000 US equities with sector, industry, country, exchange metadata.
Run once on fresh deployments or to refresh sector/industry taxonomy.

Usage:
    cd apps/api
    python -m app.scripts.seed_symbols

Or add to Railway startup by setting SEED_SYMBOLS_ON_STARTUP=true.
"""
from __future__ import annotations

import sys
from typing import Optional

from app.data.sectors import normalize_sector

# Values pandas hands back for an empty cell. `float('nan')` is the important
# one: `bool(float('nan')) is True`, so the obvious `str(cell or "")` idiom
# never short-circuits and stringifies a missing cell into the literal "nan".
# That is how 518 production rows ended up with the sector label "nan".
_EMPTY_CELLS = frozenset({"nan", "nat", "none", "null", "n/a", "na", "<na>"})


def _clean(value: object, limit: int, default: Optional[str] = None) -> Optional[str]:
    """Coerce a pandas cell to a trimmed, truncated string.

    Returns `default` when the cell is missing or a NaN-ish placeholder, rather
    than letting `str()` turn the placeholder into a real-looking label.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_CELLS:
        return default
    return text[:limit]


def _market_cap_category(market_cap: float | None) -> str | None:
    if market_cap is None:
        return None
    if market_cap >= 200e9:
        return "mega"
    if market_cap >= 10e9:
        return "large"
    if market_cap >= 2e9:
        return "mid"
    if market_cap >= 300e6:
        return "small"
    return "micro"


def seed_symbols(batch_size: int = 500, country: str = "United States") -> None:
    try:
        import financedatabase as fd
    except ImportError:
        print("financedatabase not installed — run: pip install financedatabase")
        sys.exit(1)

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from app.db.session import SessionLocal, engine
    from app.db.migrations import run_startup_migrations
    from app.db.session import Base
    from app.models.symbol import SymbolCache  # noqa: F401 — ensure table exists

    # Run migrations first so new columns exist
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    print(f"Loading FinanceDatabase equities for {country}...")
    equities = fd.Equities()
    df = equities.select(country=country)

    if df.empty:
        print("No equities found. Check FinanceDatabase installation.")
        return

    print(f"Found {len(df)} equities — seeding into symbols table...")

    rows = []
    for symbol, row in df.iterrows():
        if not symbol or not isinstance(symbol, str):
            continue
        sector = normalize_sector(row.get("sector"))
        rows.append({
            "symbol": str(symbol).upper()[:16],
            "name": _clean(row.get("name"), 255, default=str(symbol)),
            "sector": sector[:120] if sector else None,
            "industry": _clean(row.get("industry_group"), 120) or _clean(row.get("industry"), 120),
            "country": "US",
            "exchange": _clean(row.get("exchange"), 32),
            "currency": _clean(row.get("currency"), 16, default="USD"),
            "market_cap_category": None,
            "is_active": True,
            "instrument_type": "Equity",
        })

    db = SessionLocal()
    try:
        is_sqlite = engine.dialect.name == "sqlite"
        total_inserted = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            if is_sqlite:
                # SQLite: upsert manually
                from sqlalchemy import text
                for r in batch:
                    db.execute(text("""
                        INSERT INTO symbols (symbol, name, sector, industry, country, exchange,
                            currency, market_cap_category, is_active, instrument_type)
                        VALUES (:symbol, :name, :sector, :industry, :country, :exchange,
                            :currency, :market_cap_category, :is_active, :instrument_type)
                        ON CONFLICT (symbol) DO UPDATE SET
                            sector=excluded.sector,
                            industry=excluded.industry,
                            country=excluded.country,
                            exchange=excluded.exchange
                    """), r)
            else:
                stmt = pg_insert(SymbolCache).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "name": stmt.excluded.name,
                        "sector": stmt.excluded.sector,
                        "industry": stmt.excluded.industry,
                        "country": stmt.excluded.country,
                        "exchange": stmt.excluded.exchange,
                    },
                )
                db.execute(stmt)
            db.commit()
            total_inserted += len(batch)
            print(f"  Seeded {total_inserted}/{len(rows)}...")

        print(f"Done — seeded {total_inserted} symbols.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_symbols()
