"""Postgres-only migration smoke test.

Catches dialect-specific failures that SQLite tests can't see:
  - InFailedSqlTransaction (failed DDL poisoning shared transactions)
  - text=uuid operator mismatches on community joins
  - non-idempotent ALTER statements
  - DELETE/UPDATE against tables that don't exist on a fresh DB

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


def _fresh_engine():
    """Engine pointed at a brand-new Postgres schema (drops everything first)."""
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    return engine


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


def test_community_user_id_columns_are_text_compatible():
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


def test_community_accepts_non_uuid_user_id():
    """Real-world regression: Google numeric provider IDs were rejected by UUID columns."""
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
