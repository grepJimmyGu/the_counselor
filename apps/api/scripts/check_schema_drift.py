"""Schema drift detection CLI — Base.metadata vs the live database.

Catches the trap class that broke production on 2026-05-21: SQLAlchemy
models declared one column type/nullability, but the prod Postgres column
was bootstrapped under an older model version and never migrated. Symptoms
ranged from "uuid = character varying" 500s on every user lookup to
"null value in column oauth_provider" on every password signup.

Severity tags (see app/jobs/qa_jobs.py for full semantics):
    FATAL — ORM operations will 500
    WARN  — silent drift, writes still succeed
    DIFF  — type widens harmlessly
    INFO  — extra columns in prod the model doesn't know about

Exit codes:
    0  no FATAL/WARN drift
    1  drift detected
    2  script error (DB unreachable, etc.)

The same detection runs in-process via the APScheduler job
`check_schema_drift_job` (registered in app/main.py, daily at 03:00 UTC).
This CLI is the operational mirror — run it ad-hoc against any env:

    DATABASE_URL=$(railway variables --service Postgres --json \\
        | python -c "import json,sys;print(json.load(sys.stdin)['DATABASE_PUBLIC_URL'])") \\
        PYTHONPATH=apps/api python apps/api/scripts/check_schema_drift.py
"""
from __future__ import annotations

import os
import sys

from app.jobs.qa_jobs import detect_schema_drift


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set; aborting.", file=sys.stderr)
        return 2

    try:
        code, violations = detect_schema_drift(db_url)
    except Exception as exc:
        print(f"check_schema_drift errored: {exc!r}", file=sys.stderr)
        return 2

    if not violations:
        print("0 drift items")
        return 0

    counts = {sev: sum(1 for v in violations if v.startswith(sev))
              for sev in ("FATAL", "WARN", "DIFF", "INFO")}
    print(f"{len(violations)} schema item(s): "
          f"fatal={counts['FATAL']} warn={counts['WARN']} "
          f"diff={counts['DIFF']} info={counts['INFO']}")
    for v in violations:
        print(f"  {v}")
    return code


if __name__ == "__main__":
    sys.exit(main())
