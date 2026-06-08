from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _col_exists(conn, table: str, col: str) -> bool:
    """Check column existence via information_schema (Postgres) or PRAGMA (SQLite)."""
    row = conn.execute(
        text("SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
        {"t": table, "c": col},
    ).fetchone()
    return row is not None


def _run_stage1_isolated_ddl(engine: Engine, is_sqlite: bool) -> None:
    """Stage 1 risky DDL — each statement gets its own transaction.

    In Postgres, a failed ALTER TABLE inside a transaction puts the entire
    transaction into ABORTED state, causing every subsequent SQL to fail with
    InFailedSqlTransaction. By using a fresh engine.begin() per statement we
    isolate failures so one no-op (e.g., column already renamed) never poisons
    the startup migration.
    """
    # ── 1. Rename provider → oauth_provider, provider_user_id → oauth_subject ──
    for old_col, new_col in [
        ("provider", "oauth_provider"),
        ("provider_user_id", "oauth_subject"),
    ]:
        if is_sqlite:
            # SQLite doesn't abort the whole transaction on DDL failure, try/except is safe
            try:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE users RENAME COLUMN {old_col} TO {new_col}"))
            except Exception:
                pass
        else:
            # Postgres: check existence before renaming to avoid any exception at all
            with engine.begin() as c:
                if _col_exists(c, "users", old_col):
                    c.execute(text(f"ALTER TABLE users RENAME COLUMN {old_col} TO {new_col}"))

    # ── 2. Add new columns to users table ──────────────────────────────────────
    users_new_cols = [
        ("handle",            "VARCHAR(32)"),
        ("locale",            "VARCHAR(8) DEFAULT 'en'"),
        ("email_verified_at", "TIMESTAMP"),
        ("password_hash",     "VARCHAR(255)"),
        ("last_login_at",     "TIMESTAMP"),
    ]
    for col_name, col_type in users_new_cols:
        try:
            with engine.begin() as c:
                if is_sqlite:
                    c.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                else:
                    # Postgres 9.6+ supports IF NOT EXISTS — no exception, no abort risk
                    c.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
        except Exception:
            pass  # SQLite: column already exists

    # ── 3. Add nullable user_id to backtests and robustness_jobs ──────────────
    for table in ("backtests", "robustness_jobs"):
        try:
            with engine.begin() as c:
                if is_sqlite:
                    c.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(36)"))
                else:
                    c.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"))
        except Exception:
            pass

    # ── 3b. Stage 5a: Plan.comped column ─────────────────────────────────────
    # Idempotent ADD COLUMN — isolated tx so a re-add doesn't poison the conn.
    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "ALTER TABLE plans ADD COLUMN comped BOOLEAN NOT NULL DEFAULT 0"
                ))
            else:
                c.execute(text(
                    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS comped BOOLEAN NOT NULL DEFAULT FALSE"
                ))
    except Exception:
        pass  # column already exists

    # ── 3c. Stage 7 (chat v2 Phase 1): AnonymousSession.chat_turns_used ──────
    # Caps anonymous chat at 5 turns per session — see
    # build_specs/07_chat_v2_research_partner.md §2.
    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "ALTER TABLE anonymous_sessions "
                    "ADD COLUMN chat_turns_used INTEGER NOT NULL DEFAULT 0"
                ))
            else:
                c.execute(text(
                    "ALTER TABLE anonymous_sessions "
                    "ADD COLUMN IF NOT EXISTS chat_turns_used INTEGER NOT NULL DEFAULT 0"
                ))
    except Exception:
        pass  # column already exists

    # ── 3d. Stage 8 (signals v0): User.has_seen_signal_intro ──────────────────
    # Tracks whether the first-time signal-alert opt-in modal has been shown —
    # see build_specs/research_execution_v0_signals_and_alerts.md §10 #9.
    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "ALTER TABLE users "
                    "ADD COLUMN has_seen_signal_intro BOOLEAN NOT NULL DEFAULT 0"
                ))
            else:
                c.execute(text(
                    "ALTER TABLE users "
                    "ADD COLUMN IF NOT EXISTS has_seen_signal_intro BOOLEAN NOT NULL DEFAULT FALSE"
                ))
    except Exception:
        pass  # column already exists

    # ── 3e. PRD-13b: weekly_usage portfolio-diagnose rate-limit columns ───────
    # Tracks per-hour usage of the expensive POST /api/portfolio/diagnose
    # endpoint (~2-5s of CPU per call). Counter resets on the next call after
    # `last_reset_hour` rolls over an hour boundary.
    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "ALTER TABLE weekly_usage "
                    "ADD COLUMN portfolio_diagnose_runs_hourly INTEGER NOT NULL DEFAULT 0"
                ))
            else:
                c.execute(text(
                    "ALTER TABLE weekly_usage "
                    "ADD COLUMN IF NOT EXISTS portfolio_diagnose_runs_hourly INTEGER NOT NULL DEFAULT 0"
                ))
    except Exception:
        pass  # column already exists

    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "ALTER TABLE weekly_usage ADD COLUMN last_reset_hour TIMESTAMP"
                ))
            else:
                c.execute(text(
                    "ALTER TABLE weekly_usage "
                    "ADD COLUMN IF NOT EXISTS last_reset_hour TIMESTAMP"
                ))
    except Exception:
        pass  # column already exists

    # ── 4. Indexes that depend on columns added above ─────────────────────────
    # These live here (not in main conn) because IF NOT EXISTS still aborts a Postgres
    # transaction if the referenced COLUMN is missing — even though the INDEX might not exist.

    for stmt in [
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_handle ON users (handle)",
        "CREATE INDEX IF NOT EXISTS ix_plans_stripe_customer ON plans (stripe_customer_id)",
        "CREATE INDEX IF NOT EXISTS ix_plans_stripe_sub ON plans (stripe_subscription_id)",
        "CREATE INDEX IF NOT EXISTS ix_monthly_usage_period ON monthly_usage (period_start)",
        "CREATE INDEX IF NOT EXISTS ix_backtests_user_id ON backtests (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_robustness_jobs_user_id ON robustness_jobs (user_id)",
    ]:
        try:
            with engine.begin() as c:
                c.execute(text(stmt))
        except Exception:
            pass  # index already exists or referenced table/column not yet present

    # ── 5. Seed legacy-anon synthetic user and plan ────────────────────────────
    # Runs in its own connection so a DataError (e.g., 'legacy-anon-0000' is not a
    # valid UUID in production Postgres) cannot abort the main migration transaction.
    # The get_current_user_or_anonymous dep has a transient fallback so this seed
    # is non-fatal if the users.id column is UUID type (production pre-Stage-1 schema).
    _LEGACY_ID = "legacy-anon-0000"
    _LEGACY_EMAIL = "legacy@livermore.app"
    try:
        with engine.begin() as c:
            exists = c.execute(
                text("SELECT 1 FROM users WHERE id = :id"), {"id": _LEGACY_ID}
            ).fetchone()
            if not exists:
                c.execute(
                    text(
                        "INSERT INTO users (id, email, locale, oauth_provider, created_at, updated_at)"
                        " VALUES (:id, :email, 'en', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": _LEGACY_ID, "email": _LEGACY_EMAIL},
                )
    except Exception:
        pass  # non-fatal: DataError if users.id is UUID and 'legacy-anon-0000' is invalid

    try:
        with engine.begin() as c:
            exists = c.execute(
                text("SELECT 1 FROM plans WHERE user_id = :uid"), {"uid": _LEGACY_ID}
            ).fetchone()
            if not exists:
                c.execute(
                    text(
                        "INSERT INTO plans (user_id, tier, status, updated_at)"
                        " VALUES (:uid, 'scout', 'active', CURRENT_TIMESTAMP)"
                    ),
                    {"uid": _LEGACY_ID},
                )
    except Exception:
        pass  # non-fatal

    # ── 6. Fix community tables: user_id UUID → TEXT (Postgres only) ───────────
    # Community tables were created with user_id UUID REFERENCES users(id).
    # The frontend passes string user identifiers (including Google numeric IDs)
    # that are not valid UUIDs, causing INSERT/SELECT failures.
    # We drop the FK constraint and widen the column to TEXT.
    if not is_sqlite:
        community_tables = [
            "user_watchlists",
            "user_votes",
            "strategy_upvotes",
            "strategy_comments",
            "stock_theses",
        ]
        for tbl in community_tables:
            # Drop FK constraint (Postgres auto-names it {table}_user_id_fkey)
            try:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_user_id_fkey"))
            except Exception:
                pass
            # Widen column from UUID to TEXT (USING casts existing UUID values to their text representation)
            try:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN user_id TYPE TEXT USING user_id::text"))
            except Exception:
                pass  # Already TEXT or table doesn't exist


def run_startup_migrations(engine: Engine) -> None:
    """Idempotent DDL for columns added after initial deploy. Safe to run every startup."""
    is_sqlite = engine.dialect.name == "sqlite"

    # Stage 1 risky DDL runs BEFORE the main transaction block using isolated connections.
    # This prevents Postgres transaction-abort pollution from try/except DDL failures.
    _run_stage1_isolated_ddl(engine, is_sqlite)

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

        # price column on symbols table (added post-initial-deploy)
        try:
            conn.execute(text("ALTER TABLE symbols ADD COLUMN IF NOT EXISTS price FLOAT"))
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
        if is_sqlite:
            # SQLite <3.35 doesn't support IF NOT EXISTS on ALTER TABLE — check via PRAGMA
            existing_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(symbols)")).fetchall()
            }
            for col_name, col_type in fundamental_columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(
                            text(f"ALTER TABLE symbols ADD COLUMN {col_name} {col_type}")
                        )
                    except Exception:
                        pass
        else:
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

        # PRD-08b: company_business_intelligence (10-K LLM extraction, 90-day TTL)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_business_intelligence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                filing_type VARCHAR(10) DEFAULT '10-K',
                filing_date DATE,
                filing_url TEXT,
                one_line_summary TEXT,
                revenue_model TEXT,
                customer_types TEXT DEFAULT '[]',
                pricing_power_implication TEXT,
                market_category VARCHAR(120),
                market_size_estimate TEXT,
                market_growth_label VARCHAR(40),
                competitive_position_label VARCHAR(60),
                market_share_notes TEXT,
                key_growth_drivers TEXT DEFAULT '[]',
                key_risks TEXT DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                source_notes TEXT DEFAULT '[]',
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS company_business_intelligence (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                filing_type VARCHAR(10) DEFAULT '10-K',
                filing_date DATE,
                filing_url TEXT,
                one_line_summary TEXT,
                revenue_model TEXT,
                customer_types JSONB DEFAULT '[]',
                pricing_power_implication TEXT,
                market_category VARCHAR(120),
                market_size_estimate TEXT,
                market_growth_label VARCHAR(40),
                competitive_position_label VARCHAR(60),
                market_share_notes TEXT,
                key_growth_drivers JSONB DEFAULT '[]',
                key_risks JSONB DEFAULT '[]',
                confidence VARCHAR(20) DEFAULT 'partial',
                source_notes JSONB DEFAULT '[]',
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        # PRD-11: users table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) NOT NULL UNIQUE,
                display_name VARCHAR(100),
                avatar_url TEXT,
                provider VARCHAR(20) NOT NULL DEFAULT 'google',
                provider_user_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                display_name VARCHAR(100),
                avatar_url TEXT,
                provider VARCHAR(20) NOT NULL DEFAULT 'google',
                provider_user_id VARCHAR(100),
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        # PRD-12: user_watchlists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS user_watchlists (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                added_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (user_id, symbol)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_watchlists_user ON user_watchlists (user_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_watchlists_symbol ON user_watchlists (symbol)"
            ))
        except Exception:
            pass

        # PRD-13: user_votes
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                vote VARCHAR(10) NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, symbol)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS user_votes (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                vote VARCHAR(10) NOT NULL CHECK (vote IN ('bull','bear','hold')),
                voted_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (user_id, symbol)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_votes_symbol ON user_votes (symbol)"
            ))
        except Exception:
            pass

        # PRD-13: community_signal_scores (pre-computed, refreshed every 5 min)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS community_signal_scores (
                symbol VARCHAR(20) PRIMARY KEY,
                watchlist_count INTEGER DEFAULT 0,
                bull_votes INTEGER DEFAULT 0,
                bear_votes INTEGER DEFAULT 0,
                hold_votes INTEGER DEFAULT 0,
                total_votes INTEGER DEFAULT 0,
                strategy_run_count INTEGER DEFAULT 0,
                signal_score REAL DEFAULT 0,
                signal_label VARCHAR(40) DEFAULT 'Neutral',
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS community_signal_scores (
                symbol VARCHAR(20) PRIMARY KEY,
                watchlist_count INT DEFAULT 0,
                bull_votes INT DEFAULT 0,
                bear_votes INT DEFAULT 0,
                hold_votes INT DEFAULT 0,
                total_votes INT DEFAULT 0,
                strategy_run_count INT DEFAULT 0,
                signal_score FLOAT DEFAULT 0,
                signal_label VARCHAR(40) DEFAULT 'Neutral',
                computed_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        # PRD-14: strategy_comments
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS strategy_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                strategy_slug VARCHAR(128) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS strategy_comments (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_slug VARCHAR(128) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_comments_slug ON strategy_comments (strategy_slug)"
            ))
        except Exception:
            pass

        # PRD-14: strategy_upvotes
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS strategy_upvotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                strategy_slug VARCHAR(128) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, strategy_slug)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS strategy_upvotes (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_slug VARCHAR(128) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (user_id, strategy_slug)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_upvotes_slug ON strategy_upvotes (strategy_slug)"
            ))
        except Exception:
            pass

        # Community v2: structured stock theses
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_theses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                stance VARCHAR(10) NOT NULL,
                timeframe VARCHAR(40) NOT NULL,
                thesis TEXT NOT NULL,
                risks TEXT NOT NULL,
                evidence_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS stock_theses (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                stance VARCHAR(10) NOT NULL CHECK (stance IN ('bull','bear','hold')),
                timeframe VARCHAR(40) NOT NULL,
                thesis TEXT NOT NULL,
                risks TEXT NOT NULL,
                evidence_url TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_stock_theses_symbol"
                " ON stock_theses (symbol, created_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_stock_theses_user"
                " ON stock_theses (user_id)"
            ))
        except Exception:
            pass

        # PRD-08d: revenue_segments (product + geo, 24h TTL) — CREATE first, then cleanup
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS revenue_segments (
                symbol VARCHAR(20) NOT NULL,
                fiscal_year INT NOT NULL,
                segment_type VARCHAR(10) NOT NULL,
                data TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, fiscal_year, segment_type)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS revenue_segments (
                symbol VARCHAR(20) NOT NULL,
                fiscal_year INT NOT NULL,
                segment_type VARCHAR(10) NOT NULL,
                data JSONB NOT NULL,
                fetched_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (symbol, fiscal_year, segment_type)
            )
        """))

        # PRD-08e: competitor_groups and competitor_revenue_cache
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS competitor_groups (
                symbol VARCHAR(20) NOT NULL,
                segment VARCHAR(100) NOT NULL,
                peer_symbol VARCHAR(20) NOT NULL,
                peer_name VARCHAR(200),
                PRIMARY KEY (symbol, segment, peer_symbol)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS competitor_groups (
                symbol VARCHAR(20) NOT NULL,
                segment VARCHAR(100) NOT NULL,
                peer_symbol VARCHAR(20) NOT NULL,
                peer_name VARCHAR(200),
                PRIMARY KEY (symbol, segment, peer_symbol)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS competitor_revenue_cache (
                symbol VARCHAR(20) NOT NULL,
                segment VARCHAR(100) NOT NULL,
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                rankings TEXT NOT NULL,
                PRIMARY KEY (symbol, segment)
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS competitor_revenue_cache (
                symbol VARCHAR(20) NOT NULL,
                segment VARCHAR(100) NOT NULL,
                computed_at TIMESTAMPTZ DEFAULT now(),
                expires_at TIMESTAMPTZ NOT NULL,
                rankings JSONB NOT NULL,
                PRIMARY KEY (symbol, segment)
            )
        """))

        # PRD-08e: supply chain columns on company_business_intelligence
        for col_name, col_type in [
            ("upstream_suppliers", "TEXT"),
            ("downstream_customers", "TEXT"),
        ]:
            try:
                conn.execute(
                    text(f"ALTER TABLE company_business_intelligence ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT '[]'")
                )
            except Exception:
                pass

        # PRD-08c: symbol_health_scores (Piotroski + Altman Z, sector percentile)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS symbol_health_scores (
                symbol VARCHAR(20) PRIMARY KEY,
                sector VARCHAR(120),
                piotroski_score SMALLINT,
                piotroski_signals TEXT DEFAULT '{}',
                altman_z_score REAL,
                altman_z_label VARCHAR(20),
                sector_piotroski_pct REAL,
                sector_piotroski_n INTEGER,
                insight_quality TEXT,
                insight_safety TEXT,
                insight_value TEXT,
                ev_ebitda REAL,
                fcf_yield REAL,
                roic REAL,
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS symbol_health_scores (
                symbol VARCHAR(20) PRIMARY KEY,
                sector VARCHAR(120),
                piotroski_score SMALLINT,
                piotroski_signals JSONB DEFAULT '{}',
                altman_z_score FLOAT,
                altman_z_label VARCHAR(20),
                sector_piotroski_pct FLOAT,
                sector_piotroski_n INT,
                insight_quality TEXT,
                insight_safety TEXT,
                insight_value TEXT,
                ev_ebitda FLOAT,
                fcf_yield FLOAT,
                roic FLOAT,
                computed_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_health_scores_sector"
                " ON symbol_health_scores (sector)"
            ))
        except Exception:
            pass

        # strategy_live_performance: daily-computed return since publish date (24h TTL)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS strategy_live_performance (
                slug VARCHAR(128) PRIMARY KEY,
                published_at DATE NOT NULL,
                computed_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                total_return REAL,
                days_tracked INTEGER DEFAULT 0,
                current_signal VARCHAR(20),
                last_price_date DATE,
                equity_curve TEXT DEFAULT '[]',
                error TEXT
            )
        """) if is_sqlite else text("""
            CREATE TABLE IF NOT EXISTS strategy_live_performance (
                slug VARCHAR(128) PRIMARY KEY,
                published_at DATE NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                total_return FLOAT,
                days_tracked INT DEFAULT 0,
                current_signal VARCHAR(20),
                last_price_date DATE,
                equity_curve JSONB DEFAULT '[]',
                error TEXT
            )
        """))

        # ── Stage 1: Identity + Entitlements ─────────────────────────────────
        # CREATE TABLE IF NOT EXISTS is always safe (never raises in Postgres).
        # All index creates and the legacy-anon seed are in _run_stage1_isolated_ddl()
        # which runs BEFORE this block using per-statement isolated connections.

        # plans table — safe (CREATE TABLE IF NOT EXISTS)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plans (
                user_id VARCHAR(36) PRIMARY KEY,
                tier VARCHAR(16) NOT NULL DEFAULT 'scout',
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                billing_cycle VARCHAR(8),
                stripe_customer_id VARCHAR(64),
                stripe_subscription_id VARCHAR(64),
                trial_end TIMESTAMP,
                current_period_end TIMESTAMP,
                canceled_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # monthly_usage table — safe (CREATE TABLE IF NOT EXISTS)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS monthly_usage (
                user_id VARCHAR(36) NOT NULL,
                period_start DATE NOT NULL,
                backtest_runs INTEGER NOT NULL DEFAULT 0,
                robustness_runs INTEGER NOT NULL DEFAULT 0,
                chat_prompts INTEGER NOT NULL DEFAULT 0,
                saved_strategies INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, period_start)
            )
        """))

        # ── Stage 2: Billing + Trials ─────────────────────────────────────────
        # stripe_events table for webhook idempotency (handled by Base.metadata.create_all
        # via StripeEvent model — this block is a safety net for production upgrades)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stripe_events (
                id VARCHAR(64) PRIMARY KEY,
                type VARCHAR(64) NOT NULL,
                received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                payload TEXT NOT NULL,
                error TEXT
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_stripe_events_type ON stripe_events (type)"
            ))
        except Exception:
            pass

        # ── Stage 1a: Simplifications + Anonymous ─────────────────────────────
        # All three tables are also defined as SQLAlchemy models and created by
        # Base.metadata.create_all. The explicit DDL below is a safety net for
        # production upgrades where create_all has already run once. All use
        # CREATE TABLE IF NOT EXISTS — safe in shared conn (never raises in Postgres).

        # weekly_usage — Scout 5-runs-per-week meter + PRD-13b portfolio
        # diagnose hourly counter. Fresh-install path; for upgrades the
        # two extra columns are also added idempotently in
        # _run_stage1_isolated_ddl §3e.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS weekly_usage (
                user_id VARCHAR(36) NOT NULL,
                week_start DATE NOT NULL,
                backtest_runs INTEGER NOT NULL DEFAULT 0,
                custom_backtest_runs INTEGER NOT NULL DEFAULT 0,
                template_backtest_runs INTEGER NOT NULL DEFAULT 0,
                portfolio_diagnose_runs_hourly INTEGER NOT NULL DEFAULT 0,
                last_reset_hour TIMESTAMP,
                PRIMARY KEY (user_id, week_start)
            )
        """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_weekly_usage_week ON weekly_usage (week_start)"
            ))
        except Exception:
            pass

        # anonymous_sessions — one-shot taste + attribution preservation
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS anonymous_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    fingerprint_hash VARCHAR(64),
                    ip_first_seen VARCHAR(64) NOT NULL,
                    ip_last_seen VARCHAR(64) NOT NULL,
                    user_agent VARCHAR(500),
                    locale VARCHAR(8) NOT NULL DEFAULT 'en',
                    runs_used INTEGER NOT NULL DEFAULT 0,
                    last_backtest_id VARCHAR(64),
                    via_handle VARCHAR(32),
                    landed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    converted_to_user_id VARCHAR(36),
                    converted_at TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS anonymous_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    fingerprint_hash VARCHAR(64),
                    ip_first_seen VARCHAR(64) NOT NULL,
                    ip_last_seen VARCHAR(64) NOT NULL,
                    user_agent VARCHAR(500),
                    locale VARCHAR(8) NOT NULL DEFAULT 'en',
                    runs_used INTEGER NOT NULL DEFAULT 0,
                    last_backtest_id VARCHAR(64),
                    via_handle VARCHAR(32),
                    landed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    converted_to_user_id VARCHAR(36),
                    converted_at TIMESTAMPTZ
                )
            """))
        for stmt in (
            "CREATE INDEX IF NOT EXISTS ix_anonymous_sessions_fingerprint ON anonymous_sessions (fingerprint_hash)",
            "CREATE INDEX IF NOT EXISTS ix_anonymous_sessions_via_handle ON anonymous_sessions (via_handle)",
            "CREATE INDEX IF NOT EXISTS ix_anonymous_sessions_converted_to ON anonymous_sessions (converted_to_user_id)",
        ):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # saved_strategies — Path A: canonical user-owned strategy definition
        # (replaces the PRD-02 mechanism of storing saved strategies as `backtests`
        # rows with slug != null). Legacy backtests.slug != null rows are NOT
        # backfilled in this migration — the historical strategy_json cannot be
        # reconstructed from result_payload. Users with legacy saves will need to
        # re-save from the workspace.
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS saved_strategies (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    strategy_json TEXT NOT NULL,
                    is_public BOOLEAN NOT NULL DEFAULT 0,
                    backtest_record_id VARCHAR(64),
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS saved_strategies (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    strategy_json JSONB NOT NULL,
                    is_public BOOLEAN NOT NULL DEFAULT FALSE,
                    backtest_record_id VARCHAR(64),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_saved_strategies_user ON saved_strategies (user_id)"
            ))
        except Exception:
            pass

        # ── Stage 4: Community + Sharing ──────────────────────────────────────
        # published_strategies — frozen public copy of a saved strategy.
        # No FK to users.id (Stage 1a rule). app-layer enforces ownership.
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS published_strategies (
                    id VARCHAR(36) PRIMARY KEY,
                    slug VARCHAR(64) NOT NULL UNIQUE,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    description TEXT,
                    strategy_json TEXT NOT NULL,
                    backtest_record_id VARCHAR(64),
                    metrics_snapshot TEXT NOT NULL,
                    universe_snapshot TEXT NOT NULL,
                    benchmark_snapshot VARCHAR(32) NOT NULL,
                    strategy_type VARCHAR(64) NOT NULL,
                    equity_curve_snapshot TEXT NOT NULL DEFAULT '[]',
                    is_hidden BOOLEAN NOT NULL DEFAULT 0,
                    is_deleted BOOLEAN NOT NULL DEFAULT 0,
                    locale VARCHAR(8) NOT NULL DEFAULT 'en',
                    follow_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS published_strategies (
                    id VARCHAR(36) PRIMARY KEY,
                    slug VARCHAR(64) NOT NULL UNIQUE,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    description TEXT,
                    strategy_json JSONB NOT NULL,
                    backtest_record_id VARCHAR(64),
                    metrics_snapshot JSONB NOT NULL,
                    universe_snapshot JSONB NOT NULL,
                    benchmark_snapshot VARCHAR(32) NOT NULL,
                    strategy_type VARCHAR(64) NOT NULL,
                    equity_curve_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
                    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    locale VARCHAR(8) NOT NULL DEFAULT 'en',
                    follow_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
        for stmt in (
            "CREATE INDEX IF NOT EXISTS ix_published_user ON published_strategies (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_published_type ON published_strategies (strategy_type)",
            "CREATE INDEX IF NOT EXISTS ix_published_created ON published_strategies (created_at DESC)",
        ):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # attribution_visits — share-URL clicks → referrer + conversion tracking.
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS attribution_visits (
                    id VARCHAR(36) PRIMARY KEY,
                    visitor_session_id VARCHAR(64) NOT NULL,
                    referrer_handle VARCHAR(32) NOT NULL,
                    referrer_user_id VARCHAR(36) NOT NULL,
                    landed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    landed_url VARCHAR(500) NOT NULL,
                    converted_to_user_id VARCHAR(36),
                    converted_at TIMESTAMP,
                    converted_to_paid_at TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS attribution_visits (
                    id VARCHAR(36) PRIMARY KEY,
                    visitor_session_id VARCHAR(64) NOT NULL,
                    referrer_handle VARCHAR(32) NOT NULL,
                    referrer_user_id VARCHAR(36) NOT NULL,
                    landed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    landed_url VARCHAR(500) NOT NULL,
                    converted_to_user_id VARCHAR(36),
                    converted_at TIMESTAMPTZ,
                    converted_to_paid_at TIMESTAMPTZ
                )
            """))
        for stmt in (
            "CREATE INDEX IF NOT EXISTS ix_attribution_vsid ON attribution_visits (visitor_session_id)",
            "CREATE INDEX IF NOT EXISTS ix_attribution_referrer_handle ON attribution_visits (referrer_handle)",
            "CREATE INDEX IF NOT EXISTS ix_attribution_referrer_user ON attribution_visits (referrer_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_attribution_converted ON attribution_visits (converted_to_user_id)",
        ):
            try:
                conn.execute(text(stmt))
            except Exception:
                pass

        # ── Stage 5a: SEO + Creator Program ──────────────────────────────────
        # stripe_invoices — ledger of paid invoices for revshare calc.
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_invoices (
                    id VARCHAR(64) PRIMARY KEY,
                    customer_user_id VARCHAR(36) NOT NULL,
                    subscription_id VARCHAR(64) NOT NULL,
                    amount_paid_cents INTEGER NOT NULL,
                    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                    status VARCHAR(16) NOT NULL,
                    paid_at TIMESTAMP NOT NULL,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    raw TEXT NOT NULL
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stripe_invoices (
                    id VARCHAR(64) PRIMARY KEY,
                    customer_user_id VARCHAR(36) NOT NULL,
                    subscription_id VARCHAR(64) NOT NULL,
                    amount_paid_cents INTEGER NOT NULL,
                    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                    status VARCHAR(16) NOT NULL,
                    paid_at TIMESTAMPTZ NOT NULL,
                    period_start TIMESTAMPTZ NOT NULL,
                    period_end TIMESTAMPTZ NOT NULL,
                    raw JSONB NOT NULL
                )
            """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_stripe_invoices_customer ON stripe_invoices (customer_user_id)"
            ))
        except Exception:
            pass

        # creator_applications
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creator_applications (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    handle_link VARCHAR(200) NOT NULL,
                    follower_count INTEGER,
                    content_format VARCHAR(32) NOT NULL,
                    sample_url VARCHAR(500) NOT NULL,
                    pitch TEXT NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    reviewed_by_user_id VARCHAR(36),
                    reviewed_at TIMESTAMP,
                    reviewed_note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creator_applications (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    handle_link VARCHAR(200) NOT NULL,
                    follower_count INTEGER,
                    content_format VARCHAR(32) NOT NULL,
                    sample_url VARCHAR(500) NOT NULL,
                    pitch TEXT NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    reviewed_by_user_id VARCHAR(36),
                    reviewed_at TIMESTAMPTZ,
                    reviewed_note TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_creator_apps_user ON creator_applications (user_id)"
            ))
        except Exception:
            pass

        # creators
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creators (
                    user_id VARCHAR(36) PRIMARY KEY,
                    application_id VARCHAR(36) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'active',
                    activated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    suspended_at TIMESTAMP,
                    payout_email VARCHAR(320) NOT NULL,
                    payout_country VARCHAR(2) NOT NULL DEFAULT 'US',
                    stripe_connect_account_id VARCHAR(64),
                    notes TEXT
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creators (
                    user_id VARCHAR(36) PRIMARY KEY,
                    application_id VARCHAR(36) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'active',
                    activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    suspended_at TIMESTAMPTZ,
                    payout_email VARCHAR(320) NOT NULL,
                    payout_country VARCHAR(2) NOT NULL DEFAULT 'US',
                    stripe_connect_account_id VARCHAR(64),
                    notes TEXT
                )
            """))

        # creator_payouts
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creator_payouts (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    paid_at TIMESTAMP NOT NULL,
                    method VARCHAR(16) NOT NULL,
                    external_reference VARCHAR(120),
                    note TEXT
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS creator_payouts (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    paid_at TIMESTAMPTZ NOT NULL,
                    method VARCHAR(16) NOT NULL,
                    external_reference VARCHAR(120),
                    note TEXT
                )
            """))
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_creator_payouts_user ON creator_payouts (user_id)"
            ))
        except Exception:
            pass

        # ── Stage 6a: email preferences ───────────────────────────────────────
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_preferences (
                    user_id VARCHAR(36) PRIMARY KEY,
                    transactional BOOLEAN NOT NULL DEFAULT 1,
                    weekly_digest BOOLEAN NOT NULL DEFAULT 1,
                    upsell_nudges BOOLEAN NOT NULL DEFAULT 1,
                    creator_program BOOLEAN NOT NULL DEFAULT 1,
                    unsubscribed_at TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_preferences (
                    user_id VARCHAR(36) PRIMARY KEY,
                    transactional BOOLEAN NOT NULL DEFAULT TRUE,
                    weekly_digest BOOLEAN NOT NULL DEFAULT TRUE,
                    upsell_nudges BOOLEAN NOT NULL DEFAULT TRUE,
                    creator_program BOOLEAN NOT NULL DEFAULT TRUE,
                    unsubscribed_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))


        # PRD-19 — notification banner entries (in-app surface)
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_banner_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(280) NOT NULL,
                    body VARCHAR(500) NOT NULL,
                    strategy_slug VARCHAR(120),
                    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                    acknowledged_at DATETIME
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_banner_user_unack "
                "ON notification_banner_entries (user_id, acknowledged_at)"
            ))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_banner_entries (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(280) NOT NULL,
                    body VARCHAR(500) NOT NULL,
                    strategy_slug VARCHAR(120),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    acknowledged_at TIMESTAMPTZ
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_banner_user_unack "
                "ON notification_banner_entries (user_id, acknowledged_at)"
            ))

        # PRD-19 — notification banner entries (in-app surface)
        if is_sqlite:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_banner_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(280) NOT NULL,
                    body VARCHAR(500) NOT NULL,
                    strategy_slug VARCHAR(120),
                    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
                    acknowledged_at DATETIME
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_banner_user_unack "
                "ON notification_banner_entries (user_id, acknowledged_at)"
            ))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notification_banner_entries (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(280) NOT NULL,
                    body VARCHAR(500) NOT NULL,
                    strategy_slug VARCHAR(120),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    acknowledged_at TIMESTAMPTZ
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_banner_user_unack "
                "ON notification_banner_entries (user_id, acknowledged_at)"
            ))

    # ── Post-create cleanup (isolated; runs AFTER all CREATE TABLE statements) ──
    # Purge bad revenue_segments rows from PRD-08d parser bug. Isolated so a
    # missing table on fresh DB can't poison the shared transaction above.
    try:
        with engine.begin() as c:
            if is_sqlite:
                c.execute(text(
                    "DELETE FROM revenue_segments WHERE data LIKE '%fiscalYear%'"
                ))
            else:
                c.execute(text(
                    "DELETE FROM revenue_segments WHERE data::text = '{\"fiscalYear\": null}'"
                    " OR data::text LIKE '%fiscalYear%'"
                ))
    except Exception:
        pass
