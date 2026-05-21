"""Detect User rows missing their companion Plan row.

Orphaned users crash `/api/auth/sync-user` on `user.plan.tier`
(AttributeError: 'NoneType' object has no attribute 'tier') and leave the
affected user with `backendToken=null` in their NextAuth JWT — the
May 21 incident, healed by PR #8 inside sync-user itself.

This script is the operational mirror of the
`test_orphan_user_detection_query_works` test. Run against any environment:

    DATABASE_URL=$(railway variables --service the_counselor --json | jq -r '.DATABASE_URL') \
        python apps/api/scripts/check_orphan_users.py

Exits 0 with the orphan list (or "0 orphans" if clean). Non-destructive —
the heal lives in sync-user; this script only reports.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set; aborting.", file=sys.stderr)
        return 2

    engine = create_engine(db_url, future=True)
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT u.id, u.email, u.created_at FROM users u "
            "LEFT JOIN plans p ON p.user_id = u.id "
            "WHERE p.user_id IS NULL "
            "ORDER BY u.created_at"
        )).fetchall()

    if not rows:
        print("0 orphans")
        return 0

    print(f"{len(rows)} orphan user(s) without a Plan row:")
    for r in rows:
        print(f"  - id={r[0]}  email={r[1]}  created_at={r[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
