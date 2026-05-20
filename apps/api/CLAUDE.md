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
