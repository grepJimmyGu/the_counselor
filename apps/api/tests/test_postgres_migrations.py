"""Postgres-only migration smoke test.

Catches dialect-specific failures that SQLite tests can't see:
  - InFailedSqlTransaction (failed DDL poisoning shared transactions)
  - text=uuid operator mismatches on community joins
  - FK constraint type mismatches (e.g., VARCHAR(36) → UUID users.id)
  - non-idempotent ALTER statements
  - DELETE/UPDATE against tables that don't exist on a fresh DB

Each `test_*` here corresponds to a row in `docs/KNOWN_ISSUES.md` —
if you trip the assertion, the test name tells you which trap you hit
and the docstring points at the post-mortem.

Skipped unless PG_TEST_URL is set (e.g. in CI). To run locally:
  PG_TEST_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
    pytest apps/api/tests/test_postgres_migrations.py
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.db.session import Base
from app.db.migrations import run_startup_migrations

import app.models  # noqa: F401 — populate Base.metadata

PG_URL = os.environ.get("PG_TEST_URL")
pytestmark = pytest.mark.skipif(PG_URL is None, reason="PG_TEST_URL not set")

COMMUNITY_TABLES = (
    "user_watchlists",
    "user_votes",
    "strategy_upvotes",
    "strategy_comments",
    "stock_theses",
)

# Stage 1a tables that also hold a user_id column.
STAGE_1A_USER_ID_TABLES = (
    "weekly_usage",
    "saved_strategies",
    "monthly_usage",
    "plans",
)


def _fresh_engine():
    """Engine pointed at a brand-new Postgres schema (drops everything first)."""
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    return engine


# ── Fresh-DB happy path ──────────────────────────────────────────────────────


def test_fresh_postgres_migration_succeeds():
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    engine.dispose()


def test_migration_is_idempotent():
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    run_startup_migrations(engine)  # second run must not raise
    engine.dispose()


# ── Schema invariants (regression assertions) ─────────────────────────────────


def test_community_user_id_columns_are_text_compatible():
    """KNOWN_ISSUES.md: Community JOIN fails — operator does not exist: text = uuid"""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    with engine.connect() as c:
        for tbl in COMMUNITY_TABLES:
            row = c.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'user_id'"
                ),
                {"t": tbl},
            ).fetchone()
            assert row is not None, f"{tbl}.user_id missing on fresh Postgres"
            assert row[0] in ("text", "character varying"), (
                f"{tbl}.user_id is {row[0]!r}; must be text/varchar so non-UUID "
                f"provider IDs (e.g. Google numeric) and the JOIN u.id::text = t.user_id work"
            )
    engine.dispose()


def test_all_user_id_columns_across_schema_are_text_compatible():
    """Catches any new table introducing user_id as UUID by mistake.

    Generalizes the community check to every `user_id` column in the schema —
    so when Stage 3/4/5 adds new tables, this test enforces the pattern."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT table_name, data_type FROM information_schema.columns "
            "WHERE column_name = 'user_id' AND table_schema = 'public'"
        )).fetchall()

    assert rows, "no user_id columns found — schema build is broken"
    bad = [(t, dt) for (t, dt) in rows if dt not in ("text", "character varying")]
    assert not bad, (
        f"user_id must be text/varchar in every table; found UUID/other: {bad}. "
        f"Production users.id may be UUID — joins and inserts break with mismatched types."
    )
    engine.dispose()


def test_no_new_fk_constraints_point_at_users_id():
    """KNOWN_ISSUES.md: FK constraints between mismatched types (VARCHAR → UUID).

    Production users.id may have been created as UUID. Any new FK constraint
    pointing at users.id from a VARCHAR(36) column makes Base.metadata.create_all
    fail at startup. The whole codebase pattern is now: no DB-level FK to
    users.id; app-layer enforces user identity."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    with engine.connect() as c:
        # Find any FK whose target column is users.id
        offenders = c.execute(text("""
            SELECT
                tc.table_name AS source_table,
                kcu.column_name AS source_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'users'
              AND ccu.column_name = 'id'
              AND tc.table_schema = 'public'
        """)).fetchall()

    assert not offenders, (
        f"Tables {[r[0] for r in offenders]} have FK constraints pointing at users.id. "
        f"This will crash Base.metadata.create_all in production if users.id is UUID type "
        f"and the source column is VARCHAR. Remove ForeignKey('users.id') from the model — "
        f"app-layer enforces user identity (see apps/api/CLAUDE.md rule #1)."
    )
    engine.dispose()


def test_community_accepts_non_uuid_user_id():
    """KNOWN_ISSUES.md: Google numeric provider ID rejected by Postgres UUID columns."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    google_numeric_id = "115253677145661247079"
    hyphenated_uuid = str(uuid.uuid4())

    with engine.begin() as c:
        for uid in (google_numeric_id, hyphenated_uuid):
            c.execute(
                text(
                    "INSERT INTO user_watchlists (user_id, symbol) "
                    "VALUES (:uid, :sym)"
                ),
                {"uid": uid, "sym": "AAPL"},
            )
    engine.dispose()


def test_stage_1a_tables_accept_non_uuid_user_id():
    """Regression: Stage 1a's weekly_usage / saved_strategies / anonymous_sessions
    must accept any user_id string (UUID-looking, Google numeric, anything)."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    from datetime import date
    google_numeric = "115253677145661247079"
    week_start = date.today()

    with engine.begin() as c:
        c.execute(
            text("INSERT INTO weekly_usage (user_id, week_start) VALUES (:uid, :ws)"),
            {"uid": google_numeric, "ws": week_start},
        )
        c.execute(
            text(
                "INSERT INTO saved_strategies (id, user_id, title, strategy_json) "
                "VALUES (:id, :uid, :title, :json)"
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": google_numeric,
                "title": "t",
                "json": "{}",
            },
        )
    engine.dispose()


def test_migration_handles_legacy_users_id_uuid():
    """The exact production scenario that crashed deploy cf3e048b (2026-05-19).

    Simulates a legacy database where users.id was created as UUID (PR #5).
    Running Base.metadata.create_all + run_startup_migrations against that
    shape must NOT fail with FK type-mismatch errors when creating new
    Stage 1a tables.

    This is the canonical regression test for the FK trap. If any future
    table inadvertently adds ForeignKey('users.id'), this test fails."""
    engine = _fresh_engine()

    # Create a minimal users table with UUID id — simulating the legacy state.
    # We bypass Base.metadata.create_all for users specifically, then let
    # create_all build everything else around it.
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                email VARCHAR(320) NOT NULL UNIQUE,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))

    # Now create the rest of the schema. SQLAlchemy's checkfirst=True skips
    # the existing users table. If any other table still has a FK to users.id,
    # this raises because the FK column is VARCHAR(36) and users.id is UUID.
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    engine.dispose()
