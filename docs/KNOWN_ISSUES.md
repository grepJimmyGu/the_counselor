# Livermore Alpha — Known Issues & Fixes

A running log of bugs encountered, root causes, and confirmed fixes. Add new entries at the top.

> **Backend agents:** the TL;DR of this doc is duplicated in
> [`apps/api/CLAUDE.md`](../apps/api/CLAUDE.md) so it's loaded automatically
> when editing backend files. The full post-mortems stay here.
>
> **Automated guards:** every trap in §"High-frequency traps" of `CLAUDE.md`
> has a corresponding test in `apps/api/tests/test_postgres_migrations.py`
> or `apps/api/tests/test_app_invariants.py`. If you trip an assertion in
> CI, the test name tells you which entry to read.

---

## Format

```
### [SHORT TITLE]
**Date:** YYYY-MM-DD
**Area:** backend | frontend | migrations | infra
**Symptom:** What the error looked like (log line, HTTP status, etc.)
**Root cause:** Why it happened
**Fix:** What changed and where
**Files:** Specific files modified
```

---

## Entries

---

### Production schema drift — UUID columns, oauth_provider NOT NULL, orphan Plan rows
**Date:** 2026-05-21
**Area:** backend / migrations / data
**Symptom:**
```
POST /api/auth/password/signup
  psycopg.errors.DatatypeMismatch: column "id" is of type uuid but expression
  is of type character varying
  LINE 1: ... VALUES ($1::VARCHAR, ...

GET /api/company/AAPL/overview          (anonymous and signed-in alike)
GET /api/fundamental/overview/AAPL
  psycopg.errors.UndefinedFunction: operator does not exist:
    uuid = character varying
  LINE 3: WHERE users.id = $1::VARCHAR

POST /api/auth/sync-user                (real Google-OAuth users)
  AttributeError: 'NoneType' object has no attribute 'tier'
```
Every backend code path that wrote to or queried `users` 500'd. Market Pulse listing stayed up (no `users` query) but every per-ticker detail page, fundamental page, sentiment page, and signup attempt failed. The only reason production looked alive was the few endpoints that don't query `users`.

**Root cause:**
Three independent drifts between the SQLAlchemy model (source of truth) and the live Postgres schema (bootstrapped under prior model versions and never migrated):

1. **`users.id` / `plans.user_id` / `monthly_usage.user_id` type drift.** Model = `String(36)`, prod = `uuid`. Introduced when an earlier model revision used `Uuid(as_uuid=False)` (see the 2026-05-19 entry below); the model was reverted to `String(36)` but the existing prod column was never altered. Every `WHERE users.id = $1::VARCHAR` query 500'd. The two `*.user_id` columns drifted via FK relationships to `users.id`.

2. **`users.oauth_provider` NOT NULL drift.** Model = `nullable=True` (added when password signup landed alongside Google OAuth), prod = `NOT NULL` (column originally created when Google was the only provider, never relaxed). Every password signup attempted to insert `None` → `NotNullViolation`.

3. **Orphaned User rows.** Both pre-existing users had a `User` row but no companion `Plan` row, so `sync_user`'s `user.plan.tier` access raised `AttributeError`. Likely created during a partial-failure path in the May 19/20 migration odyssey.

Why it surfaced on 2026-05-21 specifically: that day's QA work was the first attempt at password signup since these drifts were introduced. Until then no flow that exercised these write paths had run, so the bugs sat dormant — manifesting only as the user-visible "Failed to fetch" on stock detail pages that triggered the investigation.

**Fix:**
Single transaction against production:
```sql
ALTER TABLE plans         DROP CONSTRAINT plans_user_id_fkey;
ALTER TABLE monthly_usage DROP CONSTRAINT monthly_usage_user_id_fkey;
ALTER TABLE users         ALTER COLUMN id      TYPE VARCHAR(36) USING id::text;
ALTER TABLE plans         ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::text;
ALTER TABLE monthly_usage ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::text;
ALTER TABLE users         ALTER COLUMN oauth_provider DROP NOT NULL;
ALTER TABLE plans         ADD CONSTRAINT plans_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE monthly_usage ADD CONSTRAINT monthly_usage_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
INSERT INTO plans (user_id, tier, status, comped, updated_at)
SELECT u.id, 'scout', 'active', false, NOW()
  FROM users u LEFT JOIN plans p ON p.user_id = u.id
 WHERE p.user_id IS NULL;
```

Code-level defenses already merged in parallel:
- PR #7 — workspace anonymous-routing fix
- PR #8 — `sync_user` heals orphans on the fly (the runtime mirror of #3 above)
- PR #9 — `apps/api/scripts/check_orphan_users.py` + `test_orphan_user_detection_query_works` + the orphan invariant codified as rule #9 in `apps/api/CLAUDE.md`

No idempotent ALTER was added to `migrations.py`. Fresh DBs bootstrapped from the current model already produce the correct schema (`String(36)`, `nullable=True`, etc.) — the ALTERs above only matter for the specific prod row whose history this entry documents. If a stale snapshot ever needs to be reconciled, the transaction above is the canonical recipe.

**Files:** Direct DB writes against production. Forward defense added in this session:
- `apps/api/app/jobs/qa_jobs.py` — new, holds `check_schema_drift_job`
- `apps/api/scripts/check_schema_drift.py` — CLI mirror
- `apps/api/app/main.py` — registers the job in `_start_scheduler` (daily 03:00 UTC)

**Rule:**
1. **Schema drift is a category, not an incident.** Any model column-type change (`Uuid` → `String(36)`, `nullable=False` → `True`, length tweaks) requires an explicit prod migration on the same deploy. `Base.metadata.create_all` only creates missing tables — it never alters existing columns.
2. **The new tripwire is the long-term guard.** `check_schema_drift_job` runs daily at 03:00 UTC and logs `INVARIANT_BROKEN: schema_drift ...` for every FATAL/WARN drift. Surface via `railway logs --service the_counselor | grep INVARIANT_BROKEN`. CLI mirror: `DATABASE_URL=... PYTHONPATH=apps/api python apps/api/scripts/check_schema_drift.py`. Run before any auth-touching change.
3. **Pre-existing drift is expected output.** First run against prod reports ~8 WARN items unrelated to this incident (e.g., `users.email` is `varchar(255)` in prod vs `varchar(320)` in the model — a separate legacy drift). Triage individually, don't bulk-migrate; the tripwire's job is to make this drift visible and refuse to grow.

---

### Uuid(as_uuid=False) strips hyphens in SQLite — breaks raw SQL queries
**Date:** 2026-05-19
**Area:** backend / models
**Symptom:**
```
assert row is not None  # AssertionError in billing_jobs tests
# Raw SQL: SELECT ... FROM plans WHERE user_id = :uid → returns None
# But ORM query finds the row fine
```
**Root cause:**
SQLAlchemy's `Uuid(as_uuid=False)` type stores UUIDs in SQLite as 32-character hex strings **without hyphens** (e.g. `6daa23a46ab844a4...`). Python `uuid4()` generates hyphenated strings (e.g. `6daa23a4-6ab8-44a4-...`). The ORM attribute returns the hyphenated form; raw SQL queries using that value find nothing because the stored form has no hyphens. Postgres was not affected (native UUID type handles both formats).

Remote PR #5 introduced `Uuid(as_uuid=False)` to `User.id` and `Plan.user_id` aiming to fix a Postgres type mismatch, but broke SQLite test queries.

**Fix:**
Revert `User.id` and `Plan.user_id` from `Uuid(as_uuid=False)` → `String(36)`. `String(36)` stores UUIDs as-is (with hyphens) in both SQLite and Postgres VARCHAR columns. Postgres UUID columns accept hyphenated UUID strings on insert.

**Files:** `apps/api/app/models/user.py`

**Rule:** Never use `Uuid(as_uuid=False)` on columns that are queried via raw SQL in tests. Use `String(36)` for cross-dialect compatibility.

---

### Postgres transaction aborts on try/except DDL — startup crash
**Date:** 2026-05-19
**Area:** backend / migrations
**Symptom:**
```
sqlalchemy.exc.InternalError: (psycopg.errors.InFailedSqlTransaction)
current transaction is aborted, commands ignored until end of transaction block
[SQL: INSERT INTO users ... VALUES ('legacy-anon-0000', ...)]
ERROR: Application startup failed. Exiting.
```
**Root cause:**
In Postgres, **any failed SQL statement inside a transaction puts the entire connection into ABORTED state**. Subsequent SQL on the same connection raises `InFailedSqlTransaction` regardless of intervening `try/except` blocks. The Python exception is caught, but Postgres still aborts the transaction.

The migration ran all DDL inside a single `with engine.begin() as conn:` block. Several `try/except` statements wrapped operations that could legitimately fail (e.g., `SELECT WHERE id = 'legacy-anon-0000'` fails because `users.id` is UUID type in production and `legacy-anon-0000` is not a valid UUID). The try/except caught the DataError in Python, but the transaction was already poisoned. Every subsequent call on `conn` then failed with `InFailedSqlTransaction`, including the legacy-anon user seed INSERT that had no error handling.

SQLite does NOT exhibit this behaviour — failed statements don't abort the transaction — which is why the bug only appeared in production Postgres.

**Fix:**
Move all `try/except` DDL operations into `_run_stage1_isolated_ddl()` where each statement gets its own `engine.begin()` context. A failure in one connection cannot affect any other. Only `CREATE TABLE IF NOT EXISTS` (which truly cannot raise in Postgres) remains in the shared `conn` block.

```python
# WRONG — one try/except failure aborts all subsequent SQL in the same conn
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE users RENAME COLUMN provider TO oauth_provider"))
    except Exception:
        pass  # caught in Python, but Postgres conn is now ABORTED
    conn.execute(text("INSERT INTO users ..."))  # raises InFailedSqlTransaction

# CORRECT — each statement in its own connection
def _run_isolated_ddl(engine):
    try:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE users RENAME COLUMN provider TO oauth_provider"))
    except Exception:
        pass  # only this mini-transaction is rolled back; other connections unaffected
```

**Files:** `apps/api/app/db/migrations.py` (function `_run_stage1_isolated_ddl`)

**Rule:** In Postgres, never mix try/except DDL with non-DDL SQL in the same `engine.begin()` block. Put every risky DDL in its own connection.

---

### RENAME COLUMN try/except aborts Postgres migration transaction
**Date:** 2026-05-19
**Area:** backend / migrations
**Symptom:** Same `InFailedSqlTransaction` as above — specifically triggered by `ALTER TABLE users RENAME COLUMN provider TO oauth_provider` on the second deployment (column already renamed).
**Root cause:** Sub-case of the Postgres transaction abort issue above. `RENAME COLUMN` has no `IF EXISTS` syntax in Postgres. The try/except catches Python but aborts the shared transaction.
**Fix:** Use `information_schema.columns` to check existence before renaming:
```python
with engine.begin() as c:
    exists = c.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name=:col"
    ), {"col": old_col}).fetchone()
    if exists:
        c.execute(text(f"ALTER TABLE users RENAME COLUMN {old_col} TO {new_col}"))
```
**Files:** `apps/api/app/db/migrations.py`

---

### Community JOIN fails — `operator does not exist: text = uuid`
**Date:** 2026-05-19
**Area:** backend / community routes
**Symptom:**
```
sqlalchemy.exc.ProgrammingError: operator does not exist: text = uuid
LINE 1: ...OM stock_theses t LEFT JOIN users u ON u.id::text = t.user_id
```
**Root cause:**
`stock_theses.user_id` and `strategy_comments.user_id` are `UUID` type in Postgres (created with `user_id UUID NOT NULL REFERENCES users(id)`). The JOIN `u.id::text = t.user_id` casts `u.id` (UUID) to text, but `t.user_id` is still UUID. Postgres has no `text = uuid` operator.

**Fix:**
Run `ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_user_id_fkey` then `ALTER TABLE {tbl} ALTER COLUMN user_id TYPE TEXT USING user_id::text` for all community tables. This widens the column from UUID to TEXT so the JOIN `u.id::text = t.user_id` becomes `text = text` — valid in Postgres.

**Files:** `apps/api/app/db/migrations.py` (in `_run_stage1_isolated_ddl`, community table fix block)

---

### Google numeric provider ID rejected by Postgres UUID columns
**Date:** 2026-05-19
**Area:** backend / community routes
**Symptom:**
```
sqlalchemy.exc.DataError: invalid input syntax for type uuid: "115253677145661247079"
[SQL: SELECT 1 FROM strategy_upvotes WHERE user_id = %(uid)s AND strategy_slug = %(slug)s]
```
**Root cause:**
Community tables (`user_watchlists`, `user_votes`, `strategy_upvotes`, `strategy_comments`, `stock_theses`) were created with `user_id UUID NOT NULL`. The frontend passed Google's numeric OAuth provider ID (`115253677145661247079`) directly to community endpoints as `user_id`. Postgres rejected the non-UUID string.

**Fix:** Same as above — widen `user_id` columns from `UUID` to `TEXT` in all community tables. Accepts any string identifier including Google numeric IDs and proper UUIDs.

---

### `useSearchParams()` without Suspense crashes Vercel build (prerender error)
**Date:** 2026-05-19
**Area:** frontend / Next.js
**Symptom:**
```
Error occurred prerendering page "/login". Read more: https://nextjs.org/docs/messages/prerender-error
Export encountered an error on /login/page: /login, exiting the build.
npm error command failed
```
**Root cause:**
Next.js App Router statically prerenders pages at build time. `useSearchParams()` reads the URL at runtime — using it directly in a page component (outside a `Suspense` boundary) causes Next.js to bail out with a prerender error during `next build`.

**Fix:** Two changes required:
1. Extract the component that calls `useSearchParams()` into a child component and wrap it in `<Suspense>` in the page shell.
2. Add `export const dynamic = "force-dynamic"` to opt the page out of static generation.

```tsx
// WRONG — useSearchParams at top level of page
export default function LoginPage() {
  const searchParams = useSearchParams();  // ← crashes build
  ...
}

// CORRECT — wrapped in Suspense
function LoginForm() {
  const searchParams = useSearchParams();  // ← safe inside Suspense
  ...
}
export default function LoginPage() {
  return (
    <Suspense fallback={<Loader2 />}>
      <LoginForm />
    </Suspense>
  );
}
```

**Files:** `apps/web/src/app/login/page.tsx`, `apps/web/src/app/signup/page.tsx`, `apps/web/src/app/account/page.tsx`

**Rule:** Any page using `useSearchParams()`, `usePathname()`, or other dynamic navigation hooks in Next.js App Router must be wrapped in `Suspense` and/or use `export const dynamic = "force-dynamic"`.

---

### SQLite doesn't support `INTERVAL` syntax in date arithmetic
**Date:** 2026-04 (earlier in project)
**Area:** backend / queries
**Symptom:**
```
sqlite3.OperationalError: near "INTERVAL": syntax error
```
**Root cause:**
PostgreSQL supports `WHERE created_at > now() - INTERVAL '30 days'` inline syntax. SQLite does not. Queries used this syntax unconditionally.

**Fix:** Use a bound parameter for the cutoff date computed in Python:
```python
# WRONG
conn.execute(text("SELECT ... WHERE created_at > now() - INTERVAL '30 days'"))

# CORRECT
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=30)).isoformat()
conn.execute(text("SELECT ... WHERE created_at > :cutoff"), {"cutoff": cutoff})
```

**Rule:** All date arithmetic in raw SQL must use Python-computed bound parameters, not inline dialect-specific functions like `INTERVAL`, `now()`, or `datetime('now')` (unless wrapped in an `is_sqlite` conditional).

---

### `ADD COLUMN IF NOT EXISTS` not supported in older SQLite
**Date:** 2026-04 (earlier in project)
**Area:** backend / migrations
**Symptom:**
```
sqlite3.OperationalError: near "IF": syntax error
```
**Root cause:**
`ALTER TABLE symbols ADD COLUMN IF NOT EXISTS ...` is a PostgreSQL-only extension. SQLite < 3.35 doesn't support it; SQLite ≥ 3.35 does, but the behaviour is inconsistent across environments.

**Fix:** Use `try/except` for SQLite; use `IF NOT EXISTS` for Postgres. Combined pattern:
```python
try:
    with engine.begin() as c:
        if is_sqlite:
            c.execute(text(f"ALTER TABLE t ADD COLUMN {col} {type}"))
        else:
            c.execute(text(f"ALTER TABLE t ADD COLUMN IF NOT EXISTS {col} {type}"))
except Exception:
    pass  # column already exists
```

**Rule:** Never assume `IF NOT EXISTS` on `ALTER TABLE ADD COLUMN` works in SQLite. Always branch on `is_sqlite`.

---

### `price_bars` INSERT crashes — missing NOT NULL columns
**Date:** 2026-03 (earlier in project)
**Area:** backend / price data service
**Symptom:**
```
sqlalchemy.exc.IntegrityError: NOT NULL constraint failed: price_bars.source
```
**Root cause:**
`price_bars` has several NOT NULL columns without defaults (`dividend_amount`, `split_coefficient`, `source`, `fetched_at`). New INSERT code didn't include them.

**Fix:** All INSERTs into `price_bars` must include every NOT NULL column. Use `source='commodity_spot'` or the appropriate source string; `fetched_at=datetime.utcnow()`.

---

### AMD price wrong — ETFs leaking into Stocks tab
**Date:** 2026-05 (earlier in project)
**Area:** backend / market pulse
**Symptom:** AMD showed $360.54 (incorrect); ETF symbols (DBC, QQQ, USO) appeared in the Stocks tab.
**Root cause:**
`_build_top_assets()` and `_build_featured_etfs()` both ignored the `market` parameter. ETF symbols were not excluded from the stocks query.

**Fix:**
- Created `ETF_SYMBOLS` frozenset (33 known ETF tickers) and added `instrument_type != 'ETF'` filter to stocks SQL.
- Made `_build_featured_etfs()` market-aware.
- WTI price was fetched from a stale/wrong source; replaced with `CommoditySpotService`.

**Files:** `apps/api/app/services/market_pulse_service.py`, `apps/api/app/services/commodity_spot_service.py`

---

### `RuntimeWarning: invalid value encountered in divide` in multi_factor_composite
**Date:** 2026-05 (earlier in project)
**Area:** backend / backtester engine
**Symptom:** `RuntimeWarning: invalid value encountered in divide` printed during backtest runs; NaN propagation in composite factor scores.
**Root cause:** Division by zero when computing weighted nanmean of cross-sectional z-scores when `denominator = 0` for some cells.
**Fix:**
```python
np.errstate(invalid="ignore", divide="ignore"):
    score = np.where(denominator > 0, numerator / denominator, np.nan)
```
**Files:** `apps/api/app/services/backtester/engine.py`

---

## Quick Reference: Cross-Dialect SQL Rules

| Operation | SQLite | Postgres | Safe pattern |
|---|---|---|---|
| Date arithmetic | `datetime('now', '-30 days')` | `now() - INTERVAL '30 days'` | Compute in Python, pass as `:cutoff` |
| UUID primary key | TEXT / VARCHAR | UUID | Use `String(36)` in SQLAlchemy model |
| ADD COLUMN idempotent | `try/except` | `IF NOT EXISTS` | Branch on `is_sqlite` |
| RENAME COLUMN idempotent | `try/except` (3.25+) | `information_schema` check | Separate `engine.begin()` per step |
| JSON columns | TEXT | JSONB | `is_sqlite` conditional in DDL |
| Auto PK | `AUTOINCREMENT` | `SERIAL` / `gen_random_uuid()` | `is_sqlite` conditional in DDL |
| try/except DDL | Safe (no tx abort) | **NEVER in shared conn** | Always use isolated `engine.begin()` |
