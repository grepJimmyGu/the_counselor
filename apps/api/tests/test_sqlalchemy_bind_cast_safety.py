"""Static guard against the `:bind::type` SQLAlchemy text() trap.

Runs on EVERY pytest invocation (no Postgres needed) so a regression is
caught at PR-CI time on the SQLite test path. The runtime version of
this test lives in `test_postgres_migrations.py` and exercises a real
Postgres roundtrip — but it's skipped without PG_TEST_URL, so without
this static guard a regression would only be caught by Railway's deploy
healthcheck (the very thing this fix is recovering from).

See `docs/KNOWN_ISSUES.md` and `apps/api/CLAUDE.md` for the post-mortem.
"""
from __future__ import annotations

import re
from pathlib import Path


# Postgres casts that this static guard knows about. The list is open — add
# new ones as the codebase starts using them (e.g. interval, numeric).
_CAST_TARGETS = (
    "jsonb", "json", "int", "integer", "bigint", "smallint",
    "text", "varchar", "uuid", "date", "timestamp", "timestamptz",
    "numeric", "boolean", "bool",
)
_OFFENDER_REGEX = re.compile(r":\w+::(?:" + "|".join(_CAST_TARGETS) + r")\b")


def test_no_double_colon_cast_in_text_binds_services():
    """`:bind::type` silently fails on Postgres — see CLAUDE.md.

    SQLAlchemy's `text()` bind regex uses a negative lookahead `(?!:)`
    that refuses to match `:name` when followed by `:`. So `:data::jsonb`
    is sent to Postgres LITERALLY, which raises:

        syntax error at or near \":\"
        LINE 1: ...VALUES ($1, $2, $3, :data::jsonb)

    The 2026-05-26 incident: every `revenue_segments` +
    `competitor_revenue_cache` INSERT failed silently (caught by
    `db.rollback()`), eventually starving the SQLAlchemy connection
    pool and crashing background jobs → Railway healthcheck failed.

    Fix: use `CAST(:bind AS type)` or `(:bind)::type` — both satisfy
    the bind regex by placing a non-colon character between the bind
    name and the cast operator.
    """
    services_dir = Path(__file__).parent.parent / "app" / "services"
    offenders = []
    for py in sorted(services_dir.rglob("*.py")):
        try:
            text_body = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for ln, line in enumerate(text_body.splitlines(), start=1):
            # Skip the docstrings / comments that explain the bug.
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if _OFFENDER_REGEX.search(line):
                rel = py.relative_to(services_dir.parent.parent)
                offenders.append(f"{rel}:{ln}: {line.strip()}")
    assert not offenders, (
        "Found `:bind::type` Postgres cast(s) in service code — these silently "
        "fail on Postgres. Replace with CAST(:bind AS type) or (:bind)::type. "
        "See apps/api/CLAUDE.md (SQLAlchemy text() bind-cast trap).\n  "
        + "\n  ".join(offenders)
    )


def test_no_double_colon_cast_in_text_binds_routes():
    """Same guard, but for `apps/api/app/api/routes/` (route-layer SQL is
    less common but possible)."""
    routes_dir = Path(__file__).parent.parent / "app" / "api" / "routes"
    if not routes_dir.exists():
        return
    offenders = []
    for py in sorted(routes_dir.rglob("*.py")):
        try:
            text_body = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for ln, line in enumerate(text_body.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if _OFFENDER_REGEX.search(line):
                rel = py.relative_to(routes_dir.parent.parent.parent)
                offenders.append(f"{rel}:{ln}: {line.strip()}")
    assert not offenders, (
        "Found `:bind::type` Postgres cast(s) in route code. Replace with "
        "CAST(:bind AS type).\n  " + "\n  ".join(offenders)
    )
