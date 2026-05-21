from __future__ import annotations

"""QA tripwire jobs.

check_schema_drift_job  — runs daily at 03:00 UTC, compares Base.metadata
                          column types/nullability against the live DB.

Each violation logs `INVARIANT_BROKEN: schema_drift ...` so the existing
`railway logs | grep INVARIANT_BROKEN` workflow surfaces them with zero
new infrastructure. The pattern mirrors `DEFERRED_TRIGGER:` already in
the codebase.

The check is non-destructive — it reads `information_schema` (Postgres)
or sqlite_master (SQLite) and compares against the model. The orphan-heal
in `sync_user` is the only place we mutate; tripwires only report.

Severity tags inside each violation:
  FATAL — incompatible: ORM operations will 500.
  WARN  — silent drift: writes still succeed but invariants are weakened.
  DIFF  — type widens harmlessly (model VARCHAR(500) vs prod TEXT).
  INFO  — prod has columns the model doesn't know about (zombies).
"""

import logging
import os
from typing import Any, Optional

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.dialects import postgresql, sqlite

logger = logging.getLogger(__name__)

_LOG_PREFIX = "INVARIANT_BROKEN: schema_drift"
_FATAL = "FATAL"
_WARN = "WARN"
_DIFF = "DIFF"
_INFO = "INFO"


def _normalize_db_url(url: str) -> str:
    """Mirror the rewrite in app/db/session.py — Railway hands us `postgresql://`
    but the app ships psycopg3, not psycopg2 (SQLAlchemy's default driver)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def _compile_type(t: Any, dialect: Any) -> str:
    """Compile a SQLAlchemy type to its dialect SQL form, lower-cased.

    Examples (postgresql dialect):
      String(36)              -> "varchar(36)"
      DateTime(timezone=True) -> "timestamp with time zone"
      Boolean                 -> "boolean"
    """
    try:
        return t.compile(dialect=dialect).lower()
    except Exception:
        return str(t).lower()


def _is_harmless_widening(model_type: str, prod_type: str) -> bool:
    """Return True if prod's type strictly accepts every value the model writes.

    Writes succeed; drift is cosmetic. Cases:
      model=varchar(500) prod=text           text accepts anything
      model=varchar(80)  prod=varchar(100)   prod accepts longer strings
      model=float        prod=double precision  SQLAlchemy `Float` always
                                                compiles to FLOAT; Postgres
                                                always stores as double
                                                precision. Numerically
                                                equivalent, pure noise.
    """
    if prod_type == "text" and model_type.startswith("varchar"):
        return True
    if model_type.startswith("varchar(") and prod_type.startswith("varchar("):
        try:
            m_len = int(model_type[len("varchar("):-1])
            p_len = int(prod_type[len("varchar("):-1])
            return p_len > m_len
        except ValueError:
            return False
    if model_type == "float" and prod_type == "double precision":
        return True
    return False


def detect_schema_drift(
    db_url: str,
    metadata: Optional[MetaData] = None,
) -> tuple[int, list[str]]:
    """Compare *metadata* (defaults to Base.metadata) to the live DB at *db_url*.

    Returns (exit_code, violations). The metadata override exists so tests can
    pin a known schema instead of importing the full app model graph.
    """
    if metadata is None:
        from app.db.session import Base
        import app.models  # noqa: F401  triggers SQLAlchemy class registration
        metadata = Base.metadata

    engine = create_engine(_normalize_db_url(db_url), future=True)
    dialect = postgresql.dialect() if engine.dialect.name == "postgresql" else sqlite.dialect()
    insp = inspect(engine)
    prod_tables = set(insp.get_table_names())
    violations: list[str] = []

    for table_name, table in metadata.tables.items():
        if table_name not in prod_tables:
            violations.append(
                f"{_FATAL} table=`{table_name}` missing in DB (model declares it; "
                f"create_all should have made it)"
            )
            continue

        prod_cols = {c["name"]: c for c in insp.get_columns(table_name)}
        model_cols = {c.name: c for c in table.columns}

        for cname in model_cols.keys() - prod_cols.keys():
            violations.append(
                f"{_FATAL} table=`{table_name}` column=`{cname}` missing in DB "
                f"(model declares it)"
            )

        for cname in prod_cols.keys() - model_cols.keys():
            violations.append(
                f"{_INFO} table=`{table_name}` column=`{cname}` exists in DB but "
                f"not in model (legacy column? zombie from a removed feature?)"
            )

        for cname in model_cols.keys() & prod_cols.keys():
            model_col = model_cols[cname]
            prod_col = prod_cols[cname]

            expected = _compile_type(model_col.type, dialect)
            actual = _compile_type(prod_col["type"], dialect)
            if expected != actual:
                severity = _DIFF if _is_harmless_widening(expected, actual) else _WARN
                violations.append(
                    f"{severity} table=`{table_name}` column=`{cname}` "
                    f"type: model={expected} prod={actual}"
                )

            model_nullable = bool(model_col.nullable)
            prod_nullable = bool(prod_col["nullable"])
            if model_nullable != prod_nullable:
                if model_nullable and not prod_nullable:
                    violations.append(
                        f"{_FATAL} table=`{table_name}` column=`{cname}` "
                        f"nullable: model=YES prod=NO (NULL writes will 500)"
                    )
                else:
                    violations.append(
                        f"{_WARN} table=`{table_name}` column=`{cname}` "
                        f"nullable: model=NO prod=YES (silent data integrity gap)"
                    )

    has_blocker = any(v.startswith((_FATAL, _WARN)) for v in violations)
    return (1 if has_blocker else 0), violations


def check_schema_drift_job() -> None:
    """APScheduler entry point. Logs INVARIANT_BROKEN lines for FATAL/WARN drift.

    Safe to call repeatedly — read-only, idempotent.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.warning("%s skipped — DATABASE_URL not set", _LOG_PREFIX)
        return

    try:
        _, violations = detect_schema_drift(db_url)
    except Exception as exc:
        logger.warning("%s errored: %r", _LOG_PREFIX, exc)
        return

    for v in violations:
        if v.startswith((_FATAL, _WARN)):
            logger.warning("%s %s", _LOG_PREFIX, v)
