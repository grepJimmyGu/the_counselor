# Backend rules — read before editing migrations.py or models/*.py

This codebase has stepped on the same Postgres / SQLAlchemy traps multiple
times. Each one cost a failed Railway deploy and a rollback. The full
post-mortems live in [`docs/KNOWN_ISSUES.md`](../../docs/KNOWN_ISSUES.md); the
TL;DR is here so it's loaded automatically when you work on backend code.

**The Postgres CI smoke test** (`tests/test_postgres_migrations.py`) is the
automated guard for items 1–5 below. If it fails on your PR, read the
test name — it tells you which trap you hit. Run it locally with:
`PG_TEST_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest tests/test_postgres_migrations.py`

---

## High-frequency traps

### 1. No FK constraints on `user_id` columns in new tables

Production `users.id` may have been created as `UUID` (PR #5 introduced
`Uuid(as_uuid=False)` before we reverted the model to `String(36)`).
A new table with `user_id VARCHAR(36) REFERENCES users(id)` makes
`Base.metadata.create_all` fail at startup — Postgres rejects FK
constraints between mismatched types.

**Pattern:** `user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)` — no `ForeignKey("users.id")`. App-layer enforces user identity. Same rule for community tables (`user_watchlists`, `user_votes`, `strategy_*`, `stock_theses`) and Stage 1a tables (`weekly_usage`, `anonymous_sessions`, `saved_strategies`).

FKs *between non-user tables* are fine if both columns are the same type. E.g., `SavedStrategy.backtest_record_id` → `backtests.id` works because both have always been `VARCHAR(64)`.

### 2. Never use `Uuid(as_uuid=False)` on ID columns

Stores UUIDs as 32-char hex *without hyphens* in SQLite. Python `uuid4()`
returns hyphenated strings. Raw SQL queries using the hyphenated value
return nothing because the stored form is different. Use `String(36)`
everywhere; works in both SQLite and Postgres VARCHAR columns. Postgres
UUID columns also accept hyphenated strings, so `String(36)` is the safe
cross-dialect choice.

### 3. No try/except DDL in shared `engine.begin()` blocks

In Postgres, **any failed SQL inside a transaction aborts the entire
connection**, even if Python catches the exception. Every subsequent
statement on that connection raises `InFailedSqlTransaction`. SQLite does
NOT exhibit this — it's a Postgres-only landmine that only shows up in
production.

```python
# WRONG — failure poisons the whole conn
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE users RENAME COLUMN ..."))
    except Exception:
        pass
    conn.execute(text("INSERT ..."))  # → InFailedSqlTransaction

# CORRECT — each risky statement in its own mini-transaction
def _isolated_ddl(engine):
    try:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE users RENAME COLUMN ..."))
    except Exception:
        pass  # only this mini-tx rolls back
```

**Only `CREATE TABLE IF NOT EXISTS`** (which truly cannot raise in
Postgres) belongs in the shared `with engine.begin() as conn:` block in
`migrations.py`. Everything else goes in `_run_stage1_isolated_ddl()`
(or a similar helper). See [`migrations.py`](app/db/migrations.py) for
the canonical pattern.

### 4. `RENAME COLUMN` has no `IF EXISTS` in Postgres — check `information_schema` first

```python
with engine.begin() as c:
    exists = c.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:col"
    ), {"t": "users", "col": old_col}).fetchone()
    if exists:
        c.execute(text(f"ALTER TABLE users RENAME COLUMN {old_col} TO {new_col}"))
```

### 5. No `INTERVAL`, `now()`, or `datetime('now')` in raw SQL

PostgreSQL has `now() - INTERVAL '30 days'`; SQLite does not. Always
compute dates in Python and pass as a bound parameter:

```python
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=30)).isoformat()
conn.execute(text("SELECT ... WHERE created_at > :cutoff"), {"cutoff": cutoff})
```

### 6. `ALTER TABLE ADD COLUMN IF NOT EXISTS` is Postgres-only

SQLite < 3.35 doesn't support it. Branch on `is_sqlite`:

```python
try:
    with engine.begin() as c:
        if is_sqlite:
            c.execute(text(f"ALTER TABLE t ADD COLUMN {col} {type}"))
        else:
            c.execute(text(f"ALTER TABLE t ADD COLUMN IF NOT EXISTS {col} {type}"))
except Exception:
    pass  # column already exists (the SQLite case)
```

### 7. FastAPI `status_code=204` routes must NOT have a response body

FastAPI 0.115+ asserts at import time: routes coded 204 cannot serialize
a body. A function with `-> None` makes FastAPI try to write `null`,
which trips the assertion and the entire app fails to start.

```python
# WRONG — crashes app startup
@router.delete("/{id}", status_code=204)
def delete_thing(...) -> None:
    ...

# CORRECT
from fastapi import Response

@router.delete("/{id}", status_code=204, response_class=Response)
def delete_thing(...) -> Response:
    ...
    return Response(status_code=204)
```

### 8. `INSERT INTO price_bars` must include every NOT NULL column

`source`, `fetched_at`, `dividend_amount`, `split_coefficient` are NOT
NULL without defaults. Use `source='commodity_spot'` (or the appropriate
ingestion source) and `fetched_at=datetime.utcnow()`.

### 9. A User row without a Plan row crashes sync-user

`sync_user` ends with `create_session_token(user.id, user.plan.tier)`. If
the User row exists but `user.plan` is `None`, that's an `AttributeError`
and the route 500s — the May 21 incident.

`_create_user_with_plan` does both inserts in one `db.commit()` so the
ORM path is atomic. The orphan state only appears for users created
during partial-failure paths (e.g. the May 19/20 migration odyssey).

**Pattern:** before reading `user.plan.tier` anywhere, branch on the
absence:

```python
if user.plan is None:
    db.add(Plan(user_id=user.id, tier="scout", status="active"))
    db.commit()
    db.refresh(user)
    logging.getLogger("livermore.auth").warning(
        "healed orphaned user without plan: user_id=%s email=%s",
        user.id, user.email,
    )
```

`tests/test_postgres_migrations.py::test_orphan_user_detection_query_works`
guards the detection query. `apps/api/scripts/check_orphan_users.py` is
the operational mirror — run before any auth-related change to confirm
the production DB has no orphans.

### 10. Check Railway Postgres disk headroom before any large backfill

Backfills that ingest thousands of rows (e.g.
`apps/api/scripts/backfill_sp500_universe.py` — 525 SPX × ~750 daily
bars = ~395k new rows) can fill the database disk silently. The
failure mode is **mid-script**: Postgres returns
`psycopg.errors.DiskFull: could not extend file "base/.../...": No
space left on device`. At that point every subsequent insert + every
read on the affected table fails with a 500, including the public
Market Pulse API. The 2026-05-23 SP500 backfill tripped this — the
DB went into recovery mode for ~10 seconds and ~275 inserts failed.

**Pattern (before any backfill >10k rows):**

1. Check current usage via the Railway dashboard (Storage tab on the
   Postgres service) — note free space
2. Estimate row payload × row count for the planned ingest
3. If estimated growth > 50% of free space, request a storage bump
   FIRST, then run the backfill
4. The backfill scripts (`backfill_gspc.py`, `backfill_sp500_universe.py`)
   are intentionally idempotent — safe to re-run partial progress
   after the disk is expanded; already-loaded rows are skipped via
   `ensure_history()`'s cache check

If a disk-full event DOES fire mid-run: kill the script, expand the
volume, re-run. Do NOT delete the partial inserts — they're correct;
the script's idempotent skip-fresh logic will pick up where you left
off.

### 11. Production hangs at "Waiting for application startup." → restart Postgres add-on

**Symptom:** Railway deploy succeeds the build phase but the container
log freezes after exactly three lines:

```
Starting Container
INFO:     Started server process [1]
INFO:     Waiting for application startup.
```

No "Application startup complete" line ever appears. Healthcheck times
out at the 2-minute mark and Railway marks the deploy failed. The
PREVIOUS deploy stays "Online" but `/health` returns HTTP 000 (curl
timeout).

**Root cause:** The lifespan hook is hanging on its first synchronous
Postgres call — `Base.metadata.create_all(bind=engine)` (`main.py:316`).
Postgres can be "fine" from the dashboard's perspective (queries return
instantly, `pg_stat_activity` shows 0 conns) AND still refuse new app
connections, because its process-level socket queue / TCP accounting is
wedged. The dashboard's connection goes through a different internal
route than app containers do.

**Diagnostic procedure:**

1. Latest failed deployment's logs:
   ```bash
   railway deployment list | head -3
   railway logs --deployment <latest-id> | tail -20
   ```
   If you see only the three "Starting Container / Started server / Waiting"
   lines and nothing else, you're in this trap.

2. Open Railway → Postgres service → Data tab. Run:
   ```sql
   SELECT state, count(*) FROM pg_stat_activity
   WHERE pid <> pg_backend_pid()
   GROUP BY state;
   ```
   - If many `idle in transaction` rows → kill them first:
     ```sql
     SELECT pg_terminate_backend(pid) FROM pg_stat_activity
     WHERE pid <> pg_backend_pid()
       AND state ILIKE 'idle%'
       AND application_name NOT ILIKE '%postgres%';
     ```
     Then retry deploy. If it succeeds, you're done.
   - If query returns 0 rows AND the new container still hangs →
     the Postgres process itself is wedged. Continue to step 3.

3. **Restart the Postgres add-on from the Railway dashboard.** Postgres
   → Deployments tab → three-dot menu → Restart. Takes ~15s.

4. After Postgres restart: `railway redeploy --from-source --yes`. The
   new container should hit "Application startup complete" within ~30s
   and pass healthcheck.

**The amplifier (real underlying bug):** `dunning_expiry_job` in
`apps/api/app/jobs/billing_jobs.py` calls `cancel_subscription()` (a
Stripe API call) inside an open DB transaction. Every slow Stripe
request leaks one idle-in-tx connection. Over weeks of hourly runs, the
pool drains. Fix in progress — move the Stripe call outside the
transaction so the conn is released before the external HTTP wait.

**Don't:** assume the symptom-time hash is a git commit. The
``11686d26`` reference in the 2026-05-26 incident turned out to be a
Railway *deployment* ID, not a git SHA. Three hours of unnecessary
reverts later, the actual fix was a 15-second dashboard restart. Always
disambiguate first with `git cat-file -t <sha>` (errors → not a git
object → probably a Railway deploy ID; verify with `railway deployment
list`).

Full post-mortem: `docs/KNOWN_ISSUES.md` (entry dated 2026-05-26,
"Production wedged 16h — FastAPI lifespan hung on Base.metadata.create_all").

### 12. `:bind::type` Postgres casts in SQLAlchemy `text()` silently fail

SQLAlchemy's `text()` bind-parameter regex is approximately:

```python
re.compile(r"(?<![:\w\$\\]):(\w+)(?!:)")  # `(?!:)` lookahead rejects `:`
```

The negative lookahead `(?!:)` means **`:data` followed by `:` is NOT
recognised as a bind parameter**. So `:data::jsonb` is sent to
Postgres literally → `SyntaxError at or near ":"`. The author thinks
the SQL says `INSERT ... VALUES (..., <bound_data>::jsonb)` but
Postgres sees `INSERT ... VALUES (..., :data::jsonb)` and rejects.

**Worse**: when the failing INSERT is wrapped in try/except + db.rollback()
(common cache-write pattern), the SQL error is silently logged and the
service "appears" to work. The bug only surfaces under traffic, when
enough failed-then-rolled-back writes accumulate to starve the
SQLAlchemy connection pool — at which point background jobs start
timing out (the 2026-05-26 Railway pool-exhaustion incident).

**Pattern:**

```python
# WRONG — silently broken on Postgres
db.execute(
    text("INSERT INTO t (data) VALUES (:data::jsonb)"),
    {"data": json.dumps(payload)},
)

# CORRECT — use SQL-standard CAST
db.execute(
    text("INSERT INTO t (data) VALUES (CAST(:data AS jsonb))"),
    {"data": json.dumps(payload)},
)

# ALSO CORRECT — wrap the bind in parens so the `(` separates from `::`
db.execute(
    text("INSERT INTO t (data) VALUES ((:data)::jsonb)"),
    {"data": json.dumps(payload)},
)
```

`tests/test_sqlalchemy_bind_cast_safety.py` is the static guard
(runs on every PR, no Postgres needed). If it fails on your PR, the
output names the offending file + line; replace `:bind::type` with
`CAST(:bind AS type)`.

### 13. Async route handlers must not hold DB sessions across long awaits

The 2026-05-26 Railway pool exhaustion was *triggered* by trap #12 above
but *amplified* by async routes that hold a `Session = Depends(get_db)`
across `await self._fmp.get_revenue_segments(...)` calls (slow external
HTTP). During the await the DB connection sits idle but stays checked
out from the pool. If 15 concurrent users hit the same slow upstream,
the pool (5 + 10 overflow = 15) drains entirely and every subsequent
DB request times out at 30s.

**Pattern to avoid:**

```python
# RISKY — DB conn held during the slow external fetch
async def get(self, symbol: str, db: Session):
    if _is_stale(symbol, db):
        raw = await self._fmp.get_revenue_segments(symbol)  # conn idle but checked out
        _save_cache(symbol, raw, db)
```

**Safer:**

```python
async def get(self, symbol: str, db: Session):
    stale = _is_stale(symbol, db)
    db.close()  # release the conn during the slow fetch
    if stale:
        raw = await self._fmp.get_revenue_segments(symbol)
        # re-acquire a fresh session for the write
        with SessionLocal() as write_db:
            _save_cache(symbol, raw, write_db)
```

OR raise the pool size + use a dedicated fetch-and-cache job that
runs outside the request path. Pre-merge, audit any async route
that takes `db: Session` and `await`s on network — those are
candidates for the same trap.

---

## Cross-dialect quick reference

| Operation | SQLite | Postgres | Safe pattern |
|---|---|---|---|
| Date arithmetic | `datetime('now', '-30 days')` | `now() - INTERVAL '30 days'` | Compute in Python, pass as `:cutoff` |
| UUID primary key | TEXT / VARCHAR | UUID | Use `String(36)` in SQLAlchemy model |
| `user_id` column type | VARCHAR | TEXT or VARCHAR | Always `String(36)` in model; never FK to `users.id` |
| ADD COLUMN idempotent | `try/except` | `IF NOT EXISTS` | Branch on `is_sqlite` |
| RENAME COLUMN idempotent | `try/except` (3.25+) | `information_schema` check | Separate `engine.begin()` per step |
| JSON columns | TEXT | JSONB | `is_sqlite` conditional in DDL |
| Auto PK | `AUTOINCREMENT` | `SERIAL` / `gen_random_uuid()` | `is_sqlite` conditional in DDL |
| try/except DDL | Safe (no tx abort) | **NEVER in shared conn** | Always use isolated `engine.begin()` |

---

## Where the patterns live in code

- **`app/db/migrations.py`** — `_run_stage1_isolated_ddl()` is the canonical "isolated risky DDL" pattern. `run_startup_migrations()`'s shared block holds only safe `CREATE TABLE IF NOT EXISTS`.
- **`app/api/entitlement_errors.py`** — Standard 402 envelope. Add new codes here when expanding gating.
- **`tests/test_postgres_migrations.py`** — Postgres-only regression tests. Skipped locally without `PG_TEST_URL`; run in CI against a Postgres 16 service container.

## When in doubt

1. Search `docs/KNOWN_ISSUES.md` for the symptom — chances are it's documented.
2. Mirror the pattern in `_run_stage1_isolated_ddl` for any new risky DDL.
3. Run the full suite with `pytest -q` before pushing; the SQLite suite catches most things and `test_postgres_migrations.py` catches Postgres-specific issues in CI.
