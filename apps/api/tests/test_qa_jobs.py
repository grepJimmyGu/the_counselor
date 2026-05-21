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
