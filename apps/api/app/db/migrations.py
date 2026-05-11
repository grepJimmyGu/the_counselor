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

        # PRD-08a: fundamental analysis tables (CREATE IF NOT EXISTS)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_business_maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                one_line_summary TEXT,
                primary_value_chain_role VARCHAR(60),
                secondary_value_chain_roles TEXT DEFAULT '[]',
                margin_implication TEXT,
                cyclicality_implication TEXT,
                raw_json TEXT,
                source_notes TEXT DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (symbol, as_of_date)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS company_business_maps (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                one_line_summary TEXT,
                primary_value_chain_role VARCHAR(60),
                secondary_value_chain_roles JSONB DEFAULT '[]',
                margin_implication TEXT,
                cyclicality_implication TEXT,
                raw_json JSONB,
                source_notes JSONB DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (symbol, as_of_date)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_market_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                market_category TEXT,
                market_size_estimate TEXT DEFAULT 'estimate unavailable',
                key_competitors TEXT DEFAULT '[]',
                raw_json TEXT,
                source_notes TEXT DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (symbol, as_of_date)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS company_market_positions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                market_category TEXT,
                market_size_estimate TEXT DEFAULT 'estimate unavailable',
                key_competitors JSONB DEFAULT '[]',
                raw_json JSONB,
                source_notes JSONB DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (symbol, as_of_date)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_financial_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                financial_validation_label VARCHAR(60),
                financial_validation_score INTEGER,
                valuation_risk_score INTEGER,
                overall_score INTEGER,
                growth_summary TEXT,
                profitability_summary TEXT,
                cash_flow_summary TEXT,
                balance_sheet_summary TEXT,
                valuation_summary TEXT,
                metrics_json TEXT,
                warnings_json TEXT DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'high',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (symbol, as_of_date)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS company_financial_validations (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_date DATE NOT NULL,
                financial_validation_label VARCHAR(60),
                financial_validation_score SMALLINT,
                valuation_risk_score SMALLINT,
                overall_score SMALLINT,
                growth_summary TEXT,
                profitability_summary TEXT,
                cash_flow_summary TEXT,
                balance_sheet_summary TEXT,
                valuation_summary TEXT,
                metrics_json JSONB,
                warnings_json JSONB DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'high',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (symbol, as_of_date)
            )
        """))
