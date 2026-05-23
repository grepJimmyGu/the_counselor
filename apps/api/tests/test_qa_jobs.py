"""Unit tests for QA tripwire jobs.

Covers `_is_harmless_widening` directly and `detect_schema_drift` against
deliberately-drifted in-memory SQLite databases. SQLite is fine for the unit
test surface — the Postgres-specific `Float` → `double precision` quirk is
covered separately by the `_is_harmless_widening` unit test.
"""
from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table, create_engine

from app.jobs.qa_jobs import _is_harmless_widening, detect_schema_drift


# ── _is_harmless_widening ─────────────────────────────────────────────────────

def test_widening_float_to_double_precision():
    """SQLAlchemy `Float` compiles to FLOAT; Postgres stores as double precision.
    Always silenced to DIFF — pure noise, every float column hits this."""
    assert _is_harmless_widening("float", "double precision")


def test_widening_varchar_to_text():
    """`String(500)` model vs `TEXT` prod: TEXT accepts anything, harmless."""
    assert _is_harmless_widening("varchar(500)", "text")


def test_widening_varchar_longer_in_prod():
    """`String(80)` model vs `varchar(100)` prod: prod accepts longer, harmless."""
    assert _is_harmless_widening("varchar(80)", "varchar(100)")


def test_widening_varchar_shorter_in_prod_is_not_widening():
    """`String(320)` model vs `varchar(255)` prod: model writes will overflow.
    Real drift — must NOT be classified as harmless."""
    assert not _is_harmless_widening("varchar(320)", "varchar(255)")


def test_widening_unrelated_types_is_not_widening():
    assert not _is_harmless_widening("integer", "varchar(36)")


# ── detect_schema_drift — happy path ──────────────────────────────────────────

def _make_db(tmp_path, name: str, metadata: MetaData) -> str:
    """Materialize *metadata* into a fresh SQLite file, return its URL."""
    url = f"sqlite:///{tmp_path}/{name}.db"
    engine = create_engine(url, future=True)
    metadata.create_all(engine)
    engine.dispose()
    return url


def test_clean_schema_reports_zero(tmp_path):
    """Same metadata used to build the DB AND check it → no drift."""
    m = MetaData()
    Table(
        "qa_users", m,
        Column("id", String(36), primary_key=True),
        Column("email", String(320), nullable=False),
    )
    url = _make_db(tmp_path, "clean", m)
    code, violations = detect_schema_drift(url, metadata=m)
    assert code == 0
    assert violations == []


# ── detect_schema_drift — type drifts ─────────────────────────────────────────

def test_type_drift_narrower_in_prod_is_warn(tmp_path):
    """Prod has `varchar(255)`, model says `String(320)` — model writes can overflow."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True),
          Column("email", String(255), nullable=False))
    url = _make_db(tmp_path, "narrow", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True),
          Column("email", String(320), nullable=False))

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 1
    assert any(v.startswith("WARN") and "email" in v for v in violations), violations


def test_type_drift_wider_in_prod_is_diff(tmp_path):
    """Prod has `varchar(100)`, model says `String(80)` — harmless widening."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True),
          Column("display_name", String(100), nullable=True))
    url = _make_db(tmp_path, "wide", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True),
          Column("display_name", String(80), nullable=True))

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 0  # DIFF doesn't bump exit code
    assert any(v.startswith("DIFF") and "display_name" in v for v in violations), violations


# ── detect_schema_drift — nullability drifts ──────────────────────────────────

def test_nullable_fatal_when_prod_not_null_but_model_nullable(tmp_path):
    """The May-21 oauth_provider bug class: writing None will 500."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True),
          Column("oauth_provider", String(32), nullable=False))  # prod NOT NULL
    url = _make_db(tmp_path, "notnull", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True),
          Column("oauth_provider", String(32), nullable=True))  # model allows None

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 1
    assert any(v.startswith("FATAL") and "oauth_provider" in v for v in violations), violations


def test_nullable_warn_when_prod_nullable_but_model_not_null(tmp_path):
    """Reverse direction: prod is lenient, model is strict. Silent gap, not a crash."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True),
          Column("locale", String(8), nullable=True))  # prod permits NULL
    url = _make_db(tmp_path, "lenient", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True),
          Column("locale", String(8), nullable=False))  # model expects always set

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 1
    assert any(v.startswith("WARN") and "locale" in v for v in violations), violations


# ── detect_schema_drift — column / table existence ────────────────────────────

def test_missing_column_in_prod_is_fatal(tmp_path):
    """Model declares a column the DB doesn't have. ORM inserts will fail."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True))
    url = _make_db(tmp_path, "missing", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True),
          Column("email", String(320), nullable=False))

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 1
    assert any(v.startswith("FATAL") and "email" in v for v in violations), violations


def test_missing_table_in_prod_is_fatal(tmp_path):
    """Model declares a table the DB doesn't have at all."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True))
    url = _make_db(tmp_path, "no_table", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True))
    Table("qa_plans", model_meta,
          Column("user_id", String(36), primary_key=True))

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 1
    assert any(v.startswith("FATAL") and "qa_plans" in v for v in violations), violations


def test_extra_column_in_prod_is_info_only(tmp_path):
    """DB has a legacy column the model doesn't know about. Reports INFO, no 500."""
    db_meta = MetaData()
    Table("qa_users", db_meta,
          Column("id", String(36), primary_key=True),
          Column("legacy_zombie", String(50), nullable=True))
    url = _make_db(tmp_path, "zombie", db_meta)

    model_meta = MetaData()
    Table("qa_users", model_meta,
          Column("id", String(36), primary_key=True))

    code, violations = detect_schema_drift(url, metadata=model_meta)
    assert code == 0  # INFO doesn't bump exit code
    assert any(v.startswith("INFO") and "legacy_zombie" in v for v in violations), violations


# ── audit_chat_tool_errors_job (2026-05-23) ──────────────────────────────────


def test_audit_chat_tool_errors_job_aggregates_and_logs(db, caplog):
    """The job scans the last 24h of chat_messages where role='tool', parses
    each row's `{"error": "Tool <name> failed: ..."}` envelope (the dispatch
    loop's defensive serialization), aggregates by (tool_name, normalized
    error excerpt), and emits one CHAT_TOOL_ERROR log line per pair.

    Regression mechanic: seed three rows — two stock_lookup failures with
    the same error shape, one backtest_execute failure with a different
    one. Run the job. Assert the aggregated log lines fire with the right
    counts."""
    import json as _json
    import logging as _logging
    from datetime import datetime, timezone

    from app.jobs.qa_jobs import audit_chat_tool_errors_job
    from app.models.chat import ChatConversation, ChatMessage

    # Patch the SessionLocal the job opens internally to point at our test db.
    from unittest.mock import patch

    # Seed conversation + tool rows with prod-shape error envelopes.
    conv = ChatConversation(
        id="conv-tool-err",
        user_id="u-1",
        title="t",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)

    # Same error twice — different input_value substring to verify the
    # normalization collapses them into one bucket.
    err_template = (
        "Tool stock_lookup failed: 1 validation error for StockLookupResponse "
        "as_of\\n  Input should be a valid string [type=string_type, "
        "input_value=datetime.date(2026, 5, {day}), input_type=date]"
    )
    for day in (22, 23):
        db.add(ChatMessage(
            id=f"m-stock-{day}",
            conversation_id=conv.id,
            role="tool",
            content=None,
            tool_results={
                "call_id": f"c{day}",
                "name": "stock_lookup",
                "content": _json.dumps({"error": err_template.format(day=day)}),
            },
            created_at=datetime.now(timezone.utc),
        ))
    # A different tool, different error — should land in its own bucket.
    db.add(ChatMessage(
        id="m-bt-1",
        conversation_id=conv.id,
        role="tool",
        content=None,
        tool_results={
            "call_id": "cbt",
            "name": "backtest_execute",
            "content": _json.dumps({"error": "Tool backtest_execute failed: RuntimeError('engine blew up')"}),
        },
        created_at=datetime.now(timezone.utc),
    ))
    # A successful tool row (not a failure envelope) — must be ignored.
    db.add(ChatMessage(
        id="m-ok",
        conversation_id=conv.id,
        role="tool",
        content=None,
        tool_results={
            "call_id": "cok",
            "name": "concept_explainer",
            "content": _json.dumps({"query": "Sharpe Ratio", "match": {"explanation": "..."}}),
        },
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()

    # Patch the job's SessionLocal to return our test session (instead of
    # opening a prod one). The job's `finally: db.close()` is fine — our
    # fixture session can be closed independently.
    class _StaticSessionLocal:
        def __init__(self, real_db): self._db = real_db
        def __call__(self): return self._db

    with patch(
        "app.db.session.SessionLocal",
        new=_StaticSessionLocal(db),
    ):
        with caplog.at_level(_logging.WARNING, logger="app.jobs.qa_jobs"):
            audit_chat_tool_errors_job()

    msgs = [r.getMessage() for r in caplog.records]
    digest_line = next((m for m in msgs if "CHAT_TOOL_ERROR_DIGEST" in m), None)
    assert digest_line is not None, f"expected DIGEST line, saw: {msgs}"
    # 3 total tool errors (2 stock_lookup variants collapse into 1 bucket
    # via input_value normalization, plus 1 backtest_execute = 2 unique).
    assert "total=3" in digest_line
    assert "unique=2" in digest_line

    # One per-bucket line per (tool, excerpt). stock_lookup count=2 because
    # the normalization collapses the input_value=date(...) variants.
    stock_line = next((m for m in msgs if "tool=stock_lookup" in m and "count=2" in m), None)
    assert stock_line is not None, f"expected stock_lookup count=2 line, saw: {msgs}"
    assert "input_value=<…>" in stock_line, "normalization should collapse input_value"

    bt_line = next((m for m in msgs if "tool=backtest_execute" in m and "count=1" in m), None)
    assert bt_line is not None, f"expected backtest_execute count=1 line, saw: {msgs}"


def test_audit_chat_tool_errors_job_empty_window_logs_zero(db, caplog):
    """No tool failures in window → one DIGEST line with total=0 + no
    per-bucket lines. The job should not surface a false alarm."""
    import logging as _logging
    from unittest.mock import patch

    from app.jobs.qa_jobs import audit_chat_tool_errors_job

    # No rows seeded — empty window.
    class _StaticSessionLocal:
        def __init__(self, real_db): self._db = real_db
        def __call__(self): return self._db

    with patch(
        "app.db.session.SessionLocal",
        new=_StaticSessionLocal(db),
    ):
        with caplog.at_level(_logging.INFO, logger="app.jobs.qa_jobs"):
            audit_chat_tool_errors_job()

    msgs = [r.getMessage() for r in caplog.records]
    # Single info-level "no tool errors" line, no warnings.
    assert any("total=0" in m and "no tool errors" in m for m in msgs), msgs
    assert not any("CHAT_TOOL_ERROR tool=" in m for m in msgs), msgs
