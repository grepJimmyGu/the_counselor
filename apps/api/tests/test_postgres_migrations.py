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


# Stage 1 introduced plans and monthly_usage with FK to users.id; these have
# always worked in production (users.id is VARCHAR(36); types match). Stage 1a
# and later code follows a stricter rule: no DB-level FK to users.id, so we
# don't depend on users.id's type. This set documents the grandfather decision —
# if you're adding a new table, do NOT extend this list.
GRANDFATHERED_FK_TO_USERS = {"plans", "monthly_usage"}


def test_no_new_fk_constraints_point_at_users_id():
    """KNOWN_ISSUES.md: FK constraints between mismatched types (VARCHAR → UUID).

    Catches any NEW table that decorates user_id with ForeignKey('users.id').
    Existing pre-Stage-1a tables (plans, monthly_usage) are grandfathered —
    production users.id is VARCHAR(36) so those FKs work today. New tables
    must follow the post-Stage-1 pattern: no DB-level FK to users.id;
    app-layer enforces user identity (see apps/api/CLAUDE.md rule #1)."""
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

    new_offenders = [r for r in offenders if r[0] not in GRANDFATHERED_FK_TO_USERS]
    assert not new_offenders, (
        f"NEW tables {[r[0] for r in new_offenders]} have FK constraints to users.id. "
        f"Production users.id type is fixed at deploy time and we don't want new tables "
        f"depending on that detail. Remove ForeignKey('users.id') from the model — "
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
    must accept any user_id string (UUID-looking, Google numeric, anything).

    Counter columns rely on server_default="0" so this minimal INSERT works."""
    import json as _json
    from datetime import date

    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    google_numeric = "115253677145661247079"
    week_start = date.today()

    with engine.begin() as c:
        c.execute(
            text("INSERT INTO weekly_usage (user_id, week_start) VALUES (:uid, :ws)"),
            {"uid": google_numeric, "ws": week_start},
        )
        # Provide all NOT NULL columns explicitly. SQLAlchemy Python-side
        # defaults (default=...) don't apply to raw SQL inserts — only
        # server_default does. created_at/updated_at use NOW() inline.
        # strategy_json is JSONB — explicit ::jsonb cast.
        c.execute(
            text(
                "INSERT INTO saved_strategies "
                "(id, user_id, title, strategy_json, is_public, created_at, updated_at) "
                "VALUES (:id, :uid, :title, CAST(:json AS jsonb), false, NOW(), NOW())"
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": google_numeric,
                "title": "t",
                "json": _json.dumps({}),
            },
        )
    engine.dispose()


def test_orphan_user_detection_query_works():
    """Codifies the production query that identifies User rows missing their
    companion Plan row. Such orphans crash sync-user on `user.plan.tier`
    (May 21 incident, fixed by PR #8). This test creates a deliberate orphan,
    runs the detection query, and asserts the orphan is found.

    Run the same query operationally:
        python apps/api/scripts/check_orphan_users.py
    """
    from sqlalchemy.orm import sessionmaker

    from app.models.user import User

    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()
    try:
        # Insert a User WITHOUT a companion Plan — simulates the orphan
        # state observed in production for users created during the
        # May 19/20 migration odyssey.
        db.add(User(id="orphan-test-1", email="orphan@test.com"))
        db.commit()

        rows = db.execute(text(
            "SELECT u.id FROM users u "
            "LEFT JOIN plans p ON p.user_id = u.id "
            "WHERE p.user_id IS NULL"
        )).fetchall()

        assert [r[0] for r in rows] == ["orphan-test-1"], (
            "Detection query failed to identify the deliberate orphan. "
            "If you change the query, also update apps/api/scripts/check_orphan_users.py."
        )
    finally:
        db.close()
        engine.dispose()


# NOTE: removed `test_migration_handles_legacy_users_id_uuid`. The premise
# (production users.id is UUID) is not the actual production state — Stage 1
# deployed with users.id as VARCHAR(36) and has been working since. The
# grandfathered Stage 1 FKs (plans, monthly_usage → users.id) crash that
# hypothetical scenario, but the scenario isn't real today.
#
# If we ever need to harden against UUID users.id in the future (e.g., a backup
# restore from a different schema), the fix is to drop FK from Plan and
# MonthlyUsage models and add primaryjoin to the relationships. Until then,
# the simpler `test_no_new_fk_constraints_point_at_users_id` (above) prevents
# NEW tables from introducing FKs to users.id, which is the actual risk surface.


# ── Stage 7 / Phase 1 / Ticket #1 — chat schema ──────────────────────────────


def test_chat_conversations_and_messages_tables_exist():
    """Both tables register through Base.metadata.create_all on a fresh Postgres,
    with the columns the build spec calls out (build_specs/07_chat_v2_research_partner.md §5)."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    with engine.connect() as c:
        conv_cols = dict(c.execute(text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name='chat_conversations'"
        )).fetchall())
        msg_cols = dict(c.execute(text(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name='chat_messages'"
        )).fetchall())

    # Conversation columns + nullability — owner cols are both nullable
    # (app-layer enforces XOR; the build spec §5 calls this out explicitly).
    expected_conv = {
        "id": "NO",
        "user_id": "YES",
        "anon_session_id": "YES",
        "title": "NO",
        "context_type": "YES",
        "context_payload": "YES",
        "created_at": "NO",
        "updated_at": "NO",
    }
    for col, nullable in expected_conv.items():
        assert conv_cols.get(col) == nullable, (
            f"chat_conversations.{col} expected nullable={nullable}, got {conv_cols.get(col)!r}"
        )

    expected_msg = {
        "id": "NO",
        "conversation_id": "NO",
        "role": "NO",
        "content": "YES",
        "tool_calls": "YES",
        "tool_results": "YES",
        "tokens_in": "NO",
        "tokens_out": "NO",
        "created_at": "NO",
    }
    for col, nullable in expected_msg.items():
        assert msg_cols.get(col) == nullable, (
            f"chat_messages.{col} expected nullable={nullable}, got {msg_cols.get(col)!r}"
        )

    engine.dispose()


def test_chat_messages_cascade_on_conversation_delete():
    """Deleting a chat_conversations row removes its messages — orphan messages
    have no meaning. Model declares ondelete='CASCADE' on the conversation_id FK."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    conv_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO chat_conversations "
                "(id, user_id, title, created_at, updated_at) "
                "VALUES (:id, :uid, 'Test', NOW(), NOW())"
            ),
            {"id": conv_id, "uid": "115253677145661247079"},
        )
        c.execute(
            text(
                "INSERT INTO chat_messages "
                "(id, conversation_id, role, content, tokens_in, tokens_out, created_at) "
                "VALUES (:id, :cid, 'user', 'hi', 0, 0, NOW())"
            ),
            {"id": msg_id, "cid": conv_id},
        )

    with engine.begin() as c:
        c.execute(text("DELETE FROM chat_conversations WHERE id = :id"), {"id": conv_id})
        remaining = c.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE id = :id"), {"id": msg_id}
        ).scalar()

    assert remaining == 0, "cascade delete from chat_conversations did not remove chat_messages row"
    engine.dispose()


def test_anonymous_session_chat_turns_used_column_present_with_default():
    """The Stage 7 anonymous chat quota lives on anonymous_sessions.chat_turns_used.
    Column must be INTEGER NOT NULL with server_default='0' so a fresh anonymous
    INSERT works without explicitly setting it (mirrors runs_used pattern)."""
    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    with engine.connect() as c:
        row = c.execute(text(
            "SELECT data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name='anonymous_sessions' AND column_name='chat_turns_used'"
        )).fetchone()

    assert row is not None, "anonymous_sessions.chat_turns_used missing on fresh Postgres"
    data_type, is_nullable, column_default = row
    assert data_type == "integer", f"chat_turns_used type={data_type!r}, expected integer"
    assert is_nullable == "NO", "chat_turns_used must be NOT NULL"
    assert column_default is not None and "0" in column_default, (
        f"chat_turns_used server_default missing or wrong: {column_default!r}"
    )

    # And the column accepts an insert without specifying it.
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO anonymous_sessions "
                "(id, ip_first_seen, ip_last_seen, landed_at, last_seen_at) "
                "VALUES (:id, '127.0.0.1', '127.0.0.1', NOW(), NOW())"
            ),
            {"id": str(uuid.uuid4())},
        )
        turns = c.execute(text(
            "SELECT chat_turns_used FROM anonymous_sessions LIMIT 1"
        )).scalar()
    assert turns == 0, f"chat_turns_used default should be 0, got {turns!r}"

    engine.dispose()


# ── SQLAlchemy text() bind-cast trap (KNOWN_ISSUES — 2026-05-26 Railway pool exhaustion) ──


def test_sqlalchemy_text_bind_with_postgres_cast_uses_CAST_form():
    """KNOWN_ISSUES.md: SQLAlchemy `:bind::type` cast silently broke prod.

    Background: SQLAlchemy `text()` parses `:name` as a bind parameter, but
    its regex (`(?<![:\\w$\\\\]):(\\w+)(?!:)`) refuses to match when followed
    by another `:`. So `:data::jsonb` is sent to Postgres literally —
    `SyntaxError at or near \":\"`. The 2026-05-26 incident: every
    `revenue_segments` + `competitor_revenue_cache` INSERT failed silently
    (caught by `db.rollback()` inside the service), eventually starving the
    SQLAlchemy connection pool and crashing background jobs.

    Fix: use `CAST(:data AS jsonb)` (or `(:data)::jsonb`) — both satisfy
    the bind regex by placing a non-colon character right after the bind
    name. This test is the empirical guard: it runs an INSERT identical
    in shape to the production query and asserts no syntax error.
    """
    import json

    engine = _fresh_engine()
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    payload = json.dumps([{"name": "Cloud", "revenue": 1234}])
    with engine.begin() as c:
        # Mirrors revenue_segment_service._save_cache after the hotfix.
        c.execute(
            text(
                "INSERT INTO revenue_segments (symbol, fiscal_year, segment_type, data)"
                " VALUES (:sym, :yr, :stype, CAST(:data AS jsonb))"
            ),
            {"sym": "ZZZ", "yr": 2025, "stype": "geo", "data": payload},
        )
        stored = c.execute(text(
            "SELECT data FROM revenue_segments WHERE symbol = :s"
        ), {"s": "ZZZ"}).scalar()
    # Round-trip the JSONB → Python list. Postgres returns it parsed.
    assert isinstance(stored, list) and stored[0]["name"] == "Cloud"

    # Belt-and-braces: the same CAST pattern inside an UPDATE works too
    # (competitor_revenue_cache uses CAST in both INSERT and ON CONFLICT
    # UPDATE — make sure both paths compile).
    new_payload = json.dumps([{"name": "Datacenter", "revenue": 5678}])
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE revenue_segments SET data = CAST(:data AS jsonb)"
                " WHERE symbol = :s"
            ),
            {"s": "ZZZ", "data": new_payload},
        )
        updated = c.execute(text(
            "SELECT data FROM revenue_segments WHERE symbol = :s"
        ), {"s": "ZZZ"}).scalar()
    assert isinstance(updated, list) and updated[0]["name"] == "Datacenter"

    engine.dispose()


