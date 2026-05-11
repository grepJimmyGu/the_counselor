from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_startup_migrations(engine: Engine) -> None:
    """Idempotent DDL for columns added after initial deploy. Safe to run every startup."""
    is_sqlite = engine.dialect.name == "sqlite"

    # New columns for the symbols table (already exists in production)
    new_columns = [
        ("exchange", "VARCHAR(32)"),
        ("timezone", "VARCHAR(64)"),
        ("alpha_vantage_match_score", "FLOAT"),
        ("is_active", "BOOLEAN"),
        ("last_validated_at", "TIMESTAMP"),
        ("created_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ]

    with engine.begin() as conn:
        for col_name, col_type in new_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE symbols ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                )
            except Exception:
                # Older SQLite builds (< 3.35) don't support IF NOT EXISTS on ALTER TABLE;
                # catch the "duplicate column" error and continue.
                pass

        # Backfill so is_active is never NULL going forward
        conn.execute(text("UPDATE symbols SET is_active = TRUE WHERE is_active IS NULL"))

        # PostgreSQL: enforce NOT NULL + default retroactively
        if not is_sqlite:
            try:
                conn.execute(
                    text("ALTER TABLE symbols ALTER COLUMN is_active SET DEFAULT TRUE")
                )
            except Exception:
                pass

        # A-share volumes exceed INTEGER range — widen to BIGINT
        if not is_sqlite:
            try:
                conn.execute(
                    text("ALTER TABLE price_bars ALTER COLUMN volume TYPE BIGINT")
                )
            except Exception:
                pass

        # PRD-02: strategy storage columns on backtests table
        backtest_new_columns = [
            ("slug",      "VARCHAR(128)"),
            ("name",      "VARCHAR(255)"),
            ("is_public", "BOOLEAN DEFAULT FALSE"),
            ("saved_at",  "TIMESTAMP"),
        ]
        for col_name, col_type in backtest_new_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE backtests ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                )
            except Exception:
                pass

        # Partial unique index on slug (only for non-NULL values)
        if not is_sqlite:
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_backtests_slug_partial "
                    "ON backtests (slug) WHERE slug IS NOT NULL"
                ))
            except Exception:
                pass

        # PRD-06: fundamental metadata columns on symbols table
        fundamental_columns = [
            ("sector", "VARCHAR(120)"),
            ("industry", "VARCHAR(120)"),
            ("country", "VARCHAR(8)"),
            ("description", "TEXT"),
            ("market_cap", "FLOAT"),
            ("pe_ratio", "FLOAT"),
            ("dividend_yield", "FLOAT"),
            ("beta", "FLOAT"),
            ("week_52_high", "FLOAT"),
            ("week_52_low", "FLOAT"),
            ("employees", "INTEGER"),
            ("market_cap_category", "VARCHAR(16)"),
            ("fundamentals_updated_at", "TIMESTAMP"),
        ]
        for col_name, col_type in fundamental_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE symbols ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                )
            except Exception:
                pass
