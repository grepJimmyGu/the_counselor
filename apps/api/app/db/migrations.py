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

        # PRD-09: news_articles
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider VARCHAR(40) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                source_name VARCHAR(120),
                url TEXT,
                published_at TIMESTAMP,
                topics TEXT DEFAULT '[]',
                ticker_sentiment_score REAL,
                ticker_sentiment_label VARCHAR(30),
                overall_sentiment_score REAL,
                overall_sentiment_label VARCHAR(30),
                relevance_score REAL,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (provider, url)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id SERIAL PRIMARY KEY,
                provider VARCHAR(40) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                source_name VARCHAR(120),
                url TEXT,
                published_at TIMESTAMPTZ,
                topics JSONB DEFAULT '[]',
                ticker_sentiment_score FLOAT,
                ticker_sentiment_label VARCHAR(30),
                overall_sentiment_score FLOAT,
                overall_sentiment_label VARCHAR(30),
                relevance_score FLOAT,
                raw_json JSONB,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (provider, url)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_news_articles_symbol_published"
                " ON news_articles (symbol, published_at DESC)"
            ))
        except Exception:
            pass

        # PRD-09: community_mentions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS community_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider VARCHAR(40) NOT NULL,
                platform VARCHAR(40) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                title TEXT,
                text TEXT,
                author VARCHAR(120),
                community_name VARCHAR(120),
                url TEXT,
                published_at TIMESTAMP,
                upvotes INTEGER,
                downvotes INTEGER,
                comments INTEGER,
                reposts INTEGER,
                likes INTEGER,
                views INTEGER,
                sentiment_score REAL,
                sentiment_label VARCHAR(30),
                relevance_score REAL,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (provider, url)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS community_mentions (
                id SERIAL PRIMARY KEY,
                provider VARCHAR(40) NOT NULL,
                platform VARCHAR(40) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                title TEXT,
                text TEXT,
                author VARCHAR(120),
                community_name VARCHAR(120),
                url TEXT,
                published_at TIMESTAMPTZ,
                upvotes INT,
                downvotes INT,
                comments INT,
                reposts INT,
                likes INT,
                views INT,
                sentiment_score FLOAT,
                sentiment_label VARCHAR(30),
                relevance_score FLOAT,
                raw_json JSONB,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (provider, url)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_community_mentions_symbol"
                " ON community_mentions (symbol, published_at DESC)"
            ))
        except Exception:
            pass

        # PRD-09: sentiment_signal_summaries (LLM output + scores, 3h TTL)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sentiment_signal_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                as_of_datetime TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                news_catalyst TEXT,
                news_sentiment TEXT,
                community_pulse TEXT,
                signal_quality_risk TEXT,
                takeaway TEXT,
                catalyst_score INTEGER,
                catalyst_materiality_score INTEGER,
                information_source_quality_score INTEGER,
                news_sentiment_score INTEGER,
                community_sentiment_score INTEGER,
                attention_score INTEGER,
                signal_quality_score INTEGER,
                risk_score INTEGER,
                overall_sentiment_signal_score INTEGER,
                overall_label VARCHAR(60),
                confidence VARCHAR(20),
                provider_status TEXT DEFAULT '{}',
                warnings TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS sentiment_signal_summaries (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                as_of_datetime TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                news_catalyst JSONB,
                news_sentiment JSONB,
                community_pulse JSONB,
                signal_quality_risk JSONB,
                takeaway JSONB,
                catalyst_score SMALLINT,
                catalyst_materiality_score SMALLINT,
                information_source_quality_score SMALLINT,
                news_sentiment_score SMALLINT,
                community_sentiment_score SMALLINT,
                attention_score SMALLINT,
                signal_quality_score SMALLINT,
                risk_score SMALLINT,
                overall_sentiment_signal_score SMALLINT,
                overall_label VARCHAR(60),
                confidence VARCHAR(20),
                provider_status JSONB DEFAULT '{}',
                warnings JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_summaries_symbol_expires"
                " ON sentiment_signal_summaries (symbol, expires_at DESC)"
            ))
        except Exception:
            pass

        # PRD-09: sentiment_toolkit_runs
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sentiment_toolkit_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                toolkit_id VARCHAR(40),
                query TEXT,
                provider_status TEXT,
                result_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS sentiment_toolkit_runs (
                id SERIAL PRIMARY KEY,
                toolkit_id VARCHAR(40),
                query JSONB,
                provider_status JSONB,
                result_summary JSONB,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        # PRD-09: sentiment_toolkit_candidates
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sentiment_toolkit_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                symbol VARCHAR(20) NOT NULL,
                rank INTEGER,
                overall_sentiment_signal_score INTEGER,
                labels_json TEXT,
                takeaway_json TEXT,
                key_news TEXT DEFAULT '[]',
                bullish_themes TEXT DEFAULT '[]',
                bearish_themes TEXT DEFAULT '[]',
                risks TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS sentiment_toolkit_candidates (
                id SERIAL PRIMARY KEY,
                run_id INT REFERENCES sentiment_toolkit_runs(id) ON DELETE CASCADE,
                symbol VARCHAR(20) NOT NULL,
                rank SMALLINT,
                overall_sentiment_signal_score SMALLINT,
                labels_json JSONB,
                takeaway_json JSONB,
                key_news JSONB DEFAULT '[]',
                bullish_themes JSONB DEFAULT '[]',
                bearish_themes JSONB DEFAULT '[]',
                risks JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
