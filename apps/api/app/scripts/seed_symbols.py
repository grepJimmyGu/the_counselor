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
        rows.append({
            "symbol": str(symbol).upper()[:16],
            "name": str(row.get("name") or symbol)[:255],
            "sector": str(row.get("sector") or "")[:120] or None,
            "industry": str(row.get("industry_group") or row.get("industry") or "")[:120] or None,
            "country": "US",
            "exchange": str(row.get("exchange") or "")[:32] or None,
            "currency": str(row.get("currency") or "USD")[:16],
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
