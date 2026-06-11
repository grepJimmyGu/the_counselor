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

### Railway build fails: `mise` can't install bleeding-edge Python patch
**Date:** 2026-06-11
**Area:** infra
**Symptom:** Three consecutive Railway deploys FAILED at the BUILD step
(not runtime/healthcheck). Build log:
```
mise ERROR Failed to install core:python@3.13.14:
  no precompiled python found for core:python@3.13.14 on x86_64-unknown-linux-gnu
[ERRO] install mise packages: python
Build Failed: process "mise install" did not complete successfully: exit code: 1
```
The failures coincided with a run of cron-related PRs (#186–#189), which
made it *look* like the cron registration broke the deploy. **It did not** —
the build dies before any of our code runs.

**Root cause:** The repo had **no pinned Python version**, so Railway's
railpack/`mise` auto-resolved `python@3.13` to the latest patch CPython had
released — `3.13.14`, published by `astral-sh/python-build-standalone` on
**2026-06-10**. But railpack bundles `mise 2026.6.1` (built **2026-06-06**),
whose precompiled-python index snapshot predates the 3.13.14 publish. mise
therefore had no precompiled binary for 3.13.14 and the build step failed.
Classic bleeding-edge race: CPython tags a patch → standalone publishes it →
mise's bundled index lags by days → an unpinned project grabs the newest
patch and can't install it.

**Why it read as "cron-correlated":** the last SUCCESS was 2026-06-09;
the first FAILED build was after that, landing on the cron PRs purely by
timing. A local `uvicorn app.main:app` boot reached "Application startup
complete" + `/health` 200 in 2 ms with the cron registered — proving the
lifespan/scheduler were innocent. The decisive evidence was
`railway logs --build <deployment-id>`, which showed the `mise install`
failure (not a runtime traceback).

**Fix:** Pin `apps/api/.python-version` to `3.13.13` — the latest 3.13
patch that's IN mise 2026.6.1's index (published 2026-06-02, before the
06-06 snapshot). Semantically identical to 3.13.14 for our code (which
targets 3.9+). With the pin, railpack stops chasing the bleeding edge.

**Prevention rule:** keep `apps/api/.python-version` pinned to a specific
patch and bump it deliberately, lagging the very latest by one patch so
mise's index has caught up. Never run unpinned — an unpinned Python is a
latent build bomb every time CPython ships a patch faster than mise's
index refreshes.

**Diagnostic lesson:** a "failed deployment" is not always a code/runtime
bug. Split build-vs-runtime FIRST: `railway logs --build <id>` (build
phase) vs `railway logs --deployment <id>` (runtime). The pre-push
static-import smoke + a local `uvicorn` boot both passed here — because the
failure was upstream of Python entirely, in the toolchain install.

**Files:** `apps/api/.python-version` (new).

---

### Lifespan warmups blocked the event loop — 14 deploys FAILED in a row, production served by a stale pre-CN container

**Date:** 2026-06-04 (evening — second outage of the day, after the morning's `Base.metadata.create_all` fix)
**Area:** backend / lifespan startup / asyncio
**Severity:** High — every deploy failed for ~3 hours, today's CN feature commits stuck on `main` and unable to reach production
**Resolution PR:** [#134](https://github.com/grepJimmyGu/the_counselor/pull/134) — `fix(main): wrap 5 lifespan warmups in threads`

**Symptom:**
14 consecutive Railway deploys today (between 16:00 and 17:30 UTC+08) marked FAILED. Container logs showed every deploy starting cleanly:

```
Starting Container
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

…and then `/health` never responded within Railway's 600s healthcheck window. The deployment showed FAILED in the Railway dashboard. Production `/health` returned HTTP 000 (curl timeout) until we realized an **older container from earlier in the day** (pre-CN-feature) was still serving traffic — Railway had no SUCCESS deploy to switch to, so it left the old one running. None of today's commits (CN feature, fire-and-forget DB init `ac4d393`, healthcheck timeout bump `6716928`) was actually live in production.

**Root cause:**
The FastAPI `lifespan()` function schedules 5 background warmups:

```python
asyncio.create_task(_warmup_market_etfs())
asyncio.create_task(_warmup_gspc())
asyncio.create_task(_warmup_commodity_spots())
asyncio.create_task(_seed_and_warmup_stock_universe())
asyncio.create_task(_invalidate_stale_bi_caches())
```

All 5 are declared `async def` — Python's type system says they're cooperative coroutines that won't hog the event loop. The function **bodies** call **synchronous** SQLAlchemy:

```python
async def _warmup_market_etfs() -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()
    rows = db.execute(text("SELECT symbol FROM symbols ...")).fetchall()  # ← sync, blocks
    ...
```

`db.execute(...)` is synchronous. It blocks the asyncio event loop until the query returns. Under healthy DB conditions, queries finish in milliseconds and the bug is invisible. Under autovacuum stress (today's CN seed had added 1.5M new `price_bars` rows; autovacuum was scanning them for hours), the same queries took **minutes**. While the warmups blocked the loop, the loop couldn't run anything else — including the dead-simple `/health` endpoint (`return {"status": "ok"}`). Railway's healthcheck timed out at 600s and Stopping Container; the next deploy hit the same wall. Repeat 14 times.

The morning's outage fix (`ac4d393`) moved `Base.metadata.create_all` to a thread, which solved THAT layer. The warmups are an entirely separate layer — they were running fine for weeks because nobody had triggered an autovacuum window long enough to expose the latent bug.

**Why the diagnosis took 3 hours:**

1. Symptom looked like trap #11 (Postgres process wedge). We tried the Postgres add-on restart — Postgres came back fine but deploys kept failing.
2. After the restart, `/health` responded but real endpoints didn't. Misleading — looked like another wedge. Actually was DB acquisition timeouts because the new container's warmups were still blocking the loop.
3. The container logs showed "Application startup complete" + Uvicorn binding cleanly, so the obvious suspect was anything AFTER startup — not realizing `lifespan()` keeps the loop busy via the scheduled `create_task`s.
4. The fact that `/health` was a trivial endpoint with NO DB dependency made the diagnosis harder — "if `/health` doesn't respond, it must be a network or process issue" was wrong; the issue was the event loop having no chance to run the handler.

**Fix sequence (what we actually shipped):**

| Commit | What | Effect |
|---|---|---|
| `7503dcc` | Surgically remove CN seed function from startup | Removed the trigger (1.5M-row seed) |
| `ac4d393` | Fire-and-forget `Base.metadata.create_all` via `asyncio.to_thread(_db_init, engine)` | Fixed the morning's outage; necessary but not sufficient for tonight's |
| `6716928` | Bump Railway healthcheckTimeout 120s → 600s | Bandaid; didn't actually unblock |
| `5fc90a7` | **Emergency comment-out**: disable all 5 warmups | Unblocked deploys at the cost of 12s cold-cache first-user latency |
| PR #134 / `4291a85` | **Permanent fix**: `_run_async_in_thread(coro)` bridge runs each warmup's coroutine in its own thread with its own event loop. Re-enable all 5. | Restored pre-outage UX without re-introducing the block |

**The pattern that fixes it (now in `apps/api/CLAUDE.md` trap #21):**

```python
def _run_async_in_thread(coro) -> None:
    """Run an async coroutine inside a worker thread with its own event loop.
    Sync DB calls inside `coro` block ONLY this thread's loop, not the main loop."""
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("background warmup failed")  # not .warning() — trap #20


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ANTI-PATTERN — blocks the main event loop:
    # asyncio.create_task(_warmup_market_etfs())

    # CORRECT — runs each warmup on its own thread:
    asyncio.create_task(asyncio.to_thread(_run_async_in_thread, _warmup_market_etfs()))
    yield
```

Each warmup gets its own thread. The thread's loop can `await` async client calls AND block on sync DB work. The main event loop stays free for `/health` and user requests.

**Files:** `apps/api/app/main.py` (`_run_async_in_thread` helper + 5 wrapped `create_task` calls)

**Rules going forward:**

1. **Any `async def` lifespan task that opens `SessionLocal()` must use the bridge.** Direct `asyncio.create_task(_my_async_warmup())` is the anti-pattern even if it works today — codified as trap #21.
2. **For new sync `def` startup work, use `asyncio.to_thread(fn, *args)` directly** (the `_db_init` pattern from `ac4d393`).
3. **Audit recipe**: grep `asyncio.create_task(_` in `apps/api/app/main.py`. Every match should either (a) pass a sync `def` to `asyncio.to_thread(fn)`, OR (b) pass an `async def` coroutine to `asyncio.to_thread(_run_async_in_thread, coro_fn())`. Anything else is latent trap #21.
4. **The "async + sync DB collision surface" is now 4 traps**: #13 (async routes can't hold `db: Session` across slow awaits), #17 (intermediate commits expire ORM instances), #20 (warmup failures must surface, not silence), #21 (this entry). Together they describe the entire pattern class.

**What enabled the outage to slip in:**

- The bug existed in the warmups for **weeks** without firing. Today's CN seed (the autovacuum trigger) is what made queries slow enough to expose it.
- Tests don't run the FastAPI lifespan under autovacuum stress. Even Postgres CI tests don't catch this because they spin up a clean DB.
- The morning's outage fix gave the false impression that the deploy-stability work was done. The warmups were the second layer of the same broader problem; we didn't realize there was a second layer until tonight.

**Verification:** Production deploy `4291a85` (PR #134, the permanent fix) succeeded in 1m32s. `/health` responds in 1.7s; Market Pulse responds in 2.0s with warmups populating cache within 30s of deploy. The trap is now structurally impossible — autovacuum can run as aggressively as Postgres wants and `/health` stays available.

---

### ^GSPC warmup silently fails — Postgres `date >= varchar` type mismatch
**Date:** 2026-06-03
**Area:** backend / warmup
**Symptom:**
Sector comparison charts showed stale SPY data ending at May 22. The `^GSPC` warmup (`_warmup_gspc()`) ran at every startup but produced no fresh bars. Railway logs showed:
```
^GSPC warmup failed: (psycopg.errors.UndefinedFunction)
operator does not exist: date >= character varying
```

**Root cause:**
The warmup passed `from_date = (today - timedelta(days=30)).isoformat()` — a Python string like `"2026-05-04"` — to SQLAlchemy's `delete(PriceBar).where(PriceBar.trading_date >= from_date)`. Postgres has no implicit cast from `varchar` to `date` in comparison operators, so `date >= varchar` fails. SQLite accepts this (permissive type system), so 803 tests passed locally while production silently failed.

The warmup was also wrapped in `except Exception as exc: logger.warning(...)` — the error was logged but never surfaced. Three fix attempts (Alpha Vantage warmup, FMP warmup, date type fix) were needed because the first two never checked if the warmup actually ran.

**Fix:**
Keep `from_date` as a Python `date` object. Convert to ISO format only for the FMP HTTP call (which needs a string), and pass the `date` object directly to SQLAlchemy.

```python
# WRONG — string triggers Postgres type error
from_date = (today - timedelta(days=30)).isoformat()
d.execute(delete(T).where(T.col >= from_date))

# CORRECT — date object, SQLAlchemy binds correctly
from_date = today - timedelta(days=30)
d.execute(delete(T).where(T.col >= from_date))
```

**Files:** `apps/api/app/main.py:_warmup_gspc`
**Rule:** Never pass Python strings to SQLAlchemy `where()` comparisons against date columns. SQLite won't catch it; Postgres will fail silently if the error is swallowed. Same family as trap #5 in `CLAUDE.md` (no `INTERVAL` in raw SQL) — cross-dialect type safety requires using Python native types and letting SQLAlchemy handle the binding.

**Secondary rule — don't silence warmup failures:** background warmup tasks that `except Exception: logger.warning(...)` hide type errors, network errors, and API key issues behind a single log line that nobody reads. All three ^GSPC fix iterations would have been one if the warmup had raised visibly or the log had been checked before deploying. Warmup failures should at minimum increment a metric or surface in the healthcheck — not just log.

---

### Anonymous backtest 500 — AttributeError: module 'engine' has no attribute 'run'
**Date:** 2026-06-01
**Area:** backend / anonymous routes
**Symptom:**
`POST /api/anonymous/backtest/run` → 500 Internal Server Error
Railway log: `AttributeError: module 'app.services.backtester.engine' has no attribute 'run'`
Browser showed CORS error because 500 responses from Railway don't include CORS headers.

**Root cause:**
The anonymous route imported `from app.services.backtester import engine` — this imports the **module** `engine.py`, not the `BacktestEngine` class. `engine.run()` doesn't exist on a module. The authed route correctly imports `from app.services.backtester.engine import BacktestEngine` and creates `engine = BacktestEngine()` at module level. The two routes had diverged.

**Fix:**
Change `from app.services.backtester import engine` to `from app.services.backtester.engine import BacktestEngine` and add `engine = BacktestEngine()` at module level, matching the authed route's pattern.

**Files:** `apps/api/app/api/routes/anonymous.py`
**Rule:** When two route files call the same service the same way, prefer a shared helper or at minimum verify the import patterns match. The divergence was invisible to tests because tests mock at the client level.

---

### FlowBacktest brick 401 — mode-agnostic brick didn't pass auth token
**Date:** 2026-06-01
**Area:** frontend / flow runtime
**Symptom:**
Signed-in users clicking through the `one_asset_mode` or `portfolio_mode` flow saw "Backtest failed. Try again." at the backtest step. Network tab showed 401 Unauthorized on `POST /api/backtest/run`. The legacy workspace's backtest worked fine for the same user.

**Root cause:**
`FlowBacktest` (the mode-agnostic adapter brick) called `runBacktest(strategyJson)` without passing the user's `backendToken`. The workspace page reads `backendToken` from `useSession()` and passes it to `runBacktest()`, but the flow brick never imported `useSession`. Signed-in users sent unauthenticated requests → 401.

The brick also didn't route anonymous users to `anonymousBacktestRun()`, so anonymous users got the same 401 (see next entry).

**Fix:**
Import `useSession` from `next-auth/react`. Read `backendToken` and `sessionStatus`. Pass `backendToken` to `runBacktest()`. Guard against firing during the NextAuth loading window. For anonymous users, call `anonymousBacktestRun()` instead.

**Files:** `apps/web/src/lib/flows/bricks/flow-backtest.tsx`
**Rule:** Mode-agnostic bricks that call authenticated endpoints must read `backendToken` from `useSession()` — same pattern as `PortfolioDiagnosis` (trap #19 in `apps/api/CLAUDE.md`). The brick didn't have this because it was extracted from a portfolio-specific brick that also never had it.

---

### FlowBacktest brick 401 for anonymous — didn't route to anonymous endpoint
**Date:** 2026-06-01
**Area:** frontend / flow runtime
**Symptom:**
Same as above — "Backtest failed. Try again." — but for anonymous users. The fix for signed-in users (#1) still left anonymous users broken because `runBacktest()` with no auth hits the authed endpoint.

**Root cause:**
`FlowBacktest` always called `runBacktest()`, never `anonymousBacktestRun()`. The workspace page branches on `isAnonymous = sessionStatus === "unauthenticated"` and calls the appropriate endpoint. The flow brick had no such branch.

**Fix:**
Add `isAnonymous = sessionStatus === "unauthenticated"`. When anonymous, call `anonymousBacktestRun()` with `template_id` from context. When authenticated, call `runBacktest()` with `backendToken`.

**Files:** `apps/web/src/lib/flows/bricks/flow-backtest.tsx`
**Rule:** Any brick that calls a backtest endpoint must handle both auth states. The branching pattern (anonymous → anonymous endpoint, signed-in → authed endpoint + token) is the canonical approach; every new mode must implement it.
**Test gap:** No test exercises the anonymous backtest path end-to-end through the flow runtime. The bug was found via live production testing. A cypress/vitest integration test that walks the flow as an anonymous user would have caught it.

---

### Production wedged 16h — FastAPI `lifespan` hung on `Base.metadata.create_all` even though `pg_stat_activity` was empty
**Date:** 2026-05-26
**Area:** infra / backend startup

**Symptom:**
Every Railway deploy from 20:15 PT May 25 onward failed healthcheck at the
2-minute mark. Live `/health` returned HTTP 000 (curl timeout, 10s+). The
container log showed exactly three lines and then nothing:
```
Starting Container
INFO:     Started server process [1]
INFO:     Waiting for application startup.
```
No exception, no traceback, no `Application startup complete.` line. The
hang is INSIDE the FastAPI `lifespan` context manager — specifically the
first synchronous Postgres operation (`Base.metadata.create_all(bind=engine)`).

Earlier in the runtime of the last-good deploy (`b7f50bb1`), Railway logs
showed accumulating SQLAlchemy pool errors:
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached,
  connection timed out, timeout 30.00
expire_trials_job failed: QueuePool limit of size 5 overflow 10 reached...
dunning_expiry_job failed: QueuePool limit of size 5 overflow 10 reached...
```
But by the time the outage was diagnosed, `pg_stat_activity` showed **zero
non-system connections to Postgres**, and a query run via Railway's
Postgres dashboard returned instantly. The DB itself was answering — but
new app connections silently hung.

**Root cause:**
The Postgres process state was wedged at the connection-handling layer
(socket queue / TCP stack inside the Postgres container), NOT the
database itself. The dashboard's connection went through a separate
internal path that happened to still work, while new app-container
connections hung indefinitely.

The original *trigger* (what got us to that state) is harder to pin down
precisely, but the chain of events maps cleanly to:
1. `dunning_expiry_job` (`apps/api/app/jobs/billing_jobs.py:83`) calls
   `cancel_subscription(row.stripe_subscription_id)` **inside an open DB
   transaction**. The Stripe API call holds the DB connection during the
   external HTTP round-trip.
2. If Stripe is slow / hung at any point, the DB conn sits idle-in-tx
   in the pool.
3. Repeat 14×/day (hourly) for weeks → idle-in-tx conns accumulate.
4. Eventually the SQLAlchemy pool drains, every new request times out
   waiting 30s for a conn from the pool, and the container hits a state
   where its Postgres TCP socket queue is full of broken/half-open conns.
5. Railway's healthcheck times out → Railway tries to deploy a new
   container → new container can't open new connections to Postgres
   because the Postgres process is itself wedged on socket accounting.

**Fix:**
Click **Restart** on the Postgres service in Railway's dashboard.
~15 seconds of downtime, Postgres comes back with a fresh process and
clean socket state. Next app redeploy passed healthcheck in 26 seconds.

**Diagnostic discipline (added this incident):**
When troubleshooting "container hangs at `Waiting for application
startup.`":
1. Check Railway's logs for the LATEST deployment ID (`railway logs
   --deployment <id>`). If you see only "Started server process" and
   no "Application startup complete", the lifespan hook is wedging.
2. Open Railway's Postgres → Data tab. Run:
   ```sql
   SELECT state, count(*) FROM pg_stat_activity
   WHERE pid <> pg_backend_pid()
   GROUP BY state;
   ```
3. If this query returns 0 rows but a fresh container still can't
   connect → **Postgres process is wedged; restart from the dashboard**.
4. If you see lots of `idle in transaction` rows → kill them with
   `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state
   ILIKE 'idle%' AND application_name NOT ILIKE '%postgres%';`.

**False trails chased (cost ~3 hours):**
A Railway *deployment ID* (`11686d26`) was misread as a git commit SHA,
which led to a series of unnecessary reverts (PRs #99, #100, #88, #97).
The reverts didn't fix anything — the issue was always on the Postgres
side. **When debugging a Railway outage, always cross-check whether a
SHA-looking string is a git commit (`git cat-file -t <sha>`) or a
Railway deployment ID (`railway deployment list`).**

**Files:**
- Post-mortem: this entry
- Underlying bug (Stripe call inside DB tx): `apps/api/app/jobs/billing_jobs.py`
  lines 83-107. Tracked separately for a follow-up PR.
- Diagnostic guidance also added to `apps/api/CLAUDE.md` as trap #11.

---

### Top Movers "Top losers" sort surfaces +3.99% gainer as worst loser
**Date:** 2026-05-23
**Area:** backend / Market Pulse + frontend / TopMovers
**Symptom:**
On the production `/stocks` page, toggling the Top Movers sort
dropdown to "Top losers" produced rows like AMD `+3.99%` at the top.
The frontend sort comparator looked correct on inspection (ascending
by `perf_1d`), but it was ordering the *least gainers* instead of
real losers.

**Root cause:**
The backend `_build_top_assets()` in
`apps/api/app/services/market_pulse_service.py` pre-sorted the
candidate pool by `cmf_20` descending and limited to top-10. CMF
descending = money flowing IN = gainer-biased. So the client-side
"losers" sort was operating on a pool of only gainers.

The frontend comparator was correct; the constraint was the
upstream universe.

**Fix:**
Two-layer fix:
  1. **Widen the pool** (PR #69) — backend stops pre-sorting; returns
     a wider candidate pool (~50 by market_cap initially, then ~500
     after PR #77 swap to `SP500_TICKERS`). Frontend client-side sort
     comparators are unchanged.
  2. **Use the SPX universe** (PR #77) — `_build_top_assets` now
     filters `WHERE s.symbol IN SP500_TICKERS`. Final pool size: 497
     after the operational backfill (PR #78). 145 of those are
     losers on a typical day — plenty of variance for the sort to
     surface real ones.

**Files:**
- `apps/api/app/services/market_pulse_service.py` — `_build_top_assets`
- `apps/api/app/data/sp500_tickers.py` — canonical universe
- `apps/api/tests/test_market_pulse_top_assets.py` — regression tests
  (`test_pool_contains_both_gainers_and_losers` is the literal
  codification of this bug)

**Rule:** when the frontend's behavior is correct but the visible
output looks wrong, suspect the upstream universe / candidate set.
Pre-sorting on the backend constrains what the frontend can do.

---

### `510300.SH` (Shanghai A-share) leaking into US Top Movers
**Date:** 2026-05-23
**Area:** backend / Market Pulse
**Symptom:**
Jimmy's production review found a Chinese fund (`510300.SH`, Huatai
PineBridge) in the Top Movers grid on `/stocks` (which has the US
toggle selected). The market toggle was clearly "US."

**Root cause:**
`_build_top_assets()` had no positive region filter — it took the
top-200 US-listed equities by market_cap. The `symbols.region`
column was NULL for `510300.SH`, so the implicit "is it US?" check
failed silently. The query saw a non-ETF with market_cap data and
recent price_bars and let it through.

**Fix:**
PR #68 added defensive belt-and-suspenders filters:
  - `region IS NULL OR region = 'US'`
  - `symbol NOT LIKE '%.SH' / '%.SZ' / '%.HK'`

PR #77 superseded this with a positive universe filter:
`s.symbol IN SP500_TICKERS`. CN listings can never appear in the SPX
set, so the leak is structurally impossible.

**Files:**
- `apps/api/app/services/market_pulse_service.py:_build_top_assets`
- `apps/api/tests/test_market_pulse_top_assets.py:test_us_top_assets_excludes_cn_a_share_implicitly_via_sp500`

**Rule:** prefer positive universe filters (whitelist) over negative
exclusions (blacklist). A whitelist is a contract; a blacklist is a
running tally of "things we noticed."

---

### Railway Postgres ran out of disk mid-backfill
**Date:** 2026-05-23
**Area:** infra / Postgres storage
**Symptom:**
The SP500 universe backfill script (`backfill_sp500_universe.py`)
was running cleanly through ~370 of 525 symbols, then suddenly:
```
psycopg.errors.DiskFull: could not extend file "base/16384/16492":
  No space left on device
HINT:  Check free disk space.
```
~275 inserts in a single batch failed. Concurrently the production
`/api/market/pulse?bypass_cache=true` started returning 500s; the
60-min cache kept serving 130 names for a while but the page would
have gone fully broken at cache rollover.

**Root cause:**
Railway Postgres had a finite volume size. The backfill ingested
~395 symbols × ~750 daily bars + sparkline metadata = several
hundred thousand new rows. Combined with existing data, the volume
filled. Postgres failed every subsequent extent allocation, including
the warmup jobs (commodity spot, gold spot all logged the same
DiskFull error).

**Fix:**
1. Killed the running script (it was failing every insert)
2. Jimmy expanded the Railway Postgres volume from the dashboard
3. Re-ran the backfill (idempotent — already-loaded symbols skip
   via `ensure_history()`'s cache check). Second pass: 517 loaded,
   8 failed (delisted names like `ABC` → `COR`, no longer recoverable
   via Alpha Vantage)

**Prevention:** see [`apps/api/CLAUDE.md`](../apps/api/CLAUDE.md)
rule #10 — check disk headroom on the Railway dashboard BEFORE
running any backfill that touches >10k rows.

**Files:**
- `apps/api/scripts/backfill_sp500_universe.py` — the script (idempotent)
- `apps/api/CLAUDE.md` — disk-headroom rule

---

### Sector comparison chart labeled "vs S&P 500" but data was SPY ETF
**Date:** 2026-05-23
**Area:** backend / sector_comparison_service
**Symptom:**
The MarketPulse sector heatmap's click-expansion chart was titled
"TECHNOLOGY STOCKS VS. S&P 500" but `sector_comparison_service.py`
read `price_bars WHERE symbol = 'SPY'` — the ETF tracking the index,
not the index itself. The two diverge slightly (SPY pays dividends,
the index doesn't; mechanical drag). The label was technically wrong
even though the visual was close.

**Root cause:**
Original implementation (PR #62 / Phase 1d) hardcoded SPY because
the codebase already had SPY bars in `price_bars` from the existing
warmup pipeline; ^GSPC was never ingested.

**Fix:**
PR #73 + operational backfill (`apps/api/scripts/backfill_gspc.py`).
The service now prefers `^GSPC` from `price_bars`; falls back
transparently to SPY (with a WARN log) when ^GSPC has no bars. The
backfill ran cleanly in production — ^GSPC now has 1004 bars (4y).
SPY is still used for the `rs_vs_spy_5d` internal RS calculation
and the strategy backtester benchmark — those are tradeable-asset
comparators, not user-visible "vs S&P 500" claims.

**Files:**
- `apps/api/app/services/sector_comparison_service.py:_load_benchmark`
- `apps/api/scripts/backfill_gspc.py`
- `apps/api/app/services/fmp_client.py:get_historical_eod` (new
  method to support the backfill)

**Rule:** the *label* and the *data source* are independent
artifacts — they can drift apart silently. Audit scripts should
explicitly verify benchmark identity (see PR #75's audit script,
"Benchmark identity" check).

---

### StreamingResponse drops Set-Cookie from injected Response → anon chat fresh-session per turn → 403 "Conversation not found"
**Date:** 2026-05-23
**Area:** backend / streaming endpoints
**Symptom:**
```
POST /api/anonymous/chat/conversations/<id>/messages → 200 OK  (first POST)
POST /api/anonymous/chat/conversations/<id>/messages → 403 Forbidden
POST /api/anonymous/chat/conversations/<id>/messages → 403 Forbidden
```
Same conversation UUID, first POST works, every subsequent POST 403s with detail "Conversation not found." Frontend symptom: widget responds once, then every follow-up message displays a red "Conversation not found" error banner.

**Root cause:**
The anonymous endpoint depends on `get_or_create_anonymous_session(request, response, db)`, which calls `response.set_cookie("livermore_anon_id", ...)` on the **injected** `Response` parameter to set the cookie that identifies the anon session across requests.

But when the route handler returns a `StreamingResponse` (the SSE body), **FastAPI discards the injected Response entirely** — the actual response sent to the client is the StreamingResponse, and the cookie set on the injected Response never reaches the browser.

Consequence: every POST is treated as a fresh visit. `get_or_create_anonymous_session` finds no cookie, creates a new `AnonymousSession` with a new UUID, sets the cookie on the injected Response (which is then discarded again). The conversation row created on POST #1 has `anon_session_id = OLD_UUID`. POST #2 arrives with NEW_UUID; `_get_or_create_anon_conversation` finds the existing row but `existing.anon_session_id != anon_session_id` → raises 403.

This is the second variant of "StreamingResponse drops state the route handler set" in two days (the first was the 2026-05-22 `DetachedInstanceError` entry below). Same family: any side effect the route handler performs on the injected Response is lost when returning a Response instance directly.

**Fix:**
Introduce `_propagate_cookies(src: Response, dst: StreamingResponse)` in `apps/api/app/api/routes/chat.py`. After building the StreamingResponse, copy every `Set-Cookie` header from the injected Response onto it:

```python
def _propagate_cookies(src: Response, dst: StreamingResponse) -> None:
    for name_bytes, value_bytes in src.raw_headers:
        if name_bytes.lower() == b"set-cookie":
            dst.raw_headers.append((name_bytes, value_bytes))

# In the anon route, just before return:
streaming = StreamingResponse(event_stream(), media_type="text/event-stream", headers={...})
_propagate_cookies(response, streaming)
return streaming
```

Uses `raw_headers` (a list of bytes-tuples) rather than the higher-level `headers` MultiDict so multiple Set-Cookie headers (one per cookie name) are all preserved — `headers["set-cookie"]` would collapse them.

The authed route doesn't currently mint cookies in its dep chain, so it doesn't need the call yet. Documented inline so a future cookie-setting dep doesn't reintroduce the bug.

**Regression test:**
`tests/test_anonymous_chat.py::test_anon_session_cookie_set_on_streaming_response` — sends a fresh request (no cookie), asserts the injected Response has a `Set-Cookie` for `livermore_anon_id=...`, then asserts the StreamingResponse we returned also carries that header. Before the fix the second assertion fails with an empty list.

**Files:** `apps/api/app/api/routes/chat.py`, `apps/api/tests/test_anonymous_chat.py`.

**Rule:**
**Any FastAPI route that returns a `Response` (incl. `StreamingResponse`) AND uses a dependency that sets cookies on the injected `Response` parameter MUST copy those cookies onto the returned Response before returning.** FastAPI discards the injected Response; cookies set on it never reach the browser. Pair with the lifecycle rule from the 2026-05-22 entry below — together they form the canonical pre-flight checklist for any streaming endpoint.

---

### stock_lookup chat tool always failed for real prod data — Pydantic v2 won't coerce date → str
**Date:** 2026-05-23
**Area:** backend / chat tools / schemas
**Symptom:**
User asks the chat widget any stock-specific question ("what's AAPL health valuation"). LLM picks `stock_lookup`, calls it twice (retry after first failure), then composes a graceful apology to the user:
> "It seems there is a temporary issue retrieving the health and valuation metrics for Apple Inc. (AAPL). I recommend checking back later..."

Persisted tool message in `chat_messages.tool_results`:
```json
{"error": "Tool stock_lookup failed: 1 validation error for StockLookupResponse
as_of  Input should be a valid string [type=string_type, input_value=datetime.date(2026, 5, 23), input_type=date]"}
```

**Root cause:**
`CompanyOverviewService.get_overview()` returns a `CompanyOverviewResponse` whose `as_of_date` field is a `datetime.date` instance. My `stock_lookup` tool projects that response into `StockLookupResponse`, which has `as_of: Optional[str] = None`. Pydantic v2 is strict — it refuses to coerce `date → str` on construction.

The `ValidationError` raised inside `lookup_stock()`. It propagated up to `dispatch_tool_call()`, then to the dispatch loop in `_run_tool_loop_inner` which has a defensive `except Exception:` that serializes the exception as `{"error": "Tool {name} failed: {exc!r}"}`. The LLM consumed that JSON as the tool result, interpreted it as a transient backend issue, retried once (got the same error), then apologized.

Existing pytest mock used `as_of_date="2026-05-21"` (already-a-string) — Pydantic accepts strings, so the test passed. The bug only surfaced in production where the underlying service returns real `date` instances.

**Fix:**
Coerce at the seam in `lookup_stock()`. Defensive about the input type so the existing string-passing tests and the production date-passing path both work:

```python
as_of_raw = getattr(overview, "as_of_date", None)
if as_of_raw is None:
    as_of_str = None
elif hasattr(as_of_raw, "isoformat"):
    as_of_str = as_of_raw.isoformat()
else:
    as_of_str = str(as_of_raw)
```

**Regression test:**
`tests/test_chat_tools_heavy.py::test_lookup_stock_coerces_date_as_of_to_isoformat_string` — explicitly constructs the MagicMock overview with `as_of_date=date(2026, 5, 23)` (the actual production shape) and asserts the response's `as_of` is the string `"2026-05-23"`. Before the fix this test would raise the same `ValidationError` the production code did.

**Files:** `apps/api/app/services/chat_tools/stock_lookup.py`, `apps/api/tests/test_chat_tools_heavy.py`.

**Rule:**
**When a Pydantic v2 response model field is typed as a primitive (e.g. `Optional[str]`) and the producing service returns a richer type (e.g. `datetime.date`), coerce at the seam.** Pydantic v2 deliberately doesn't auto-coerce non-string scalars into strings — it surfaces type drift instead of hiding it. The defensive `if hasattr(..., "isoformat") else str(...)` pattern handles both date instances and pre-formatted strings, keeping any old test fixtures green.

A related catch: the dispatch loop's defensive `except Exception:` swallows the underlying Pydantic error into a generic `{"error": "Tool failed: ..."}` payload that the LLM interprets as a runtime backend issue — the user never sees the real cause. Worth considering a separate `ValidationError` branch in the dispatch loop that logs a specific `tool_schema_mismatch` event so these don't disappear into LLM-friendly apology copy.

---

### Chat SSE returns 200 + empty body — DetachedInstanceError inside StreamingResponse
**Date:** 2026-05-22
**Area:** backend / streaming endpoints
**Symptom:**
```
POST /api/anonymous/chat/conversations/<id>/messages
  HTTP/2 200 OK
  content-type: text/event-stream; charset=utf-8
  x-accel-buffering: no
  (response body: zero bytes, connection stays open until client times out)

Railway log:
  ERROR:    Exception in ASGI application
  | sqlalchemy.orm.exc.DetachedInstanceError: Instance <AnonymousSession ...>
  |   is not bound to a Session; attribute refresh operation cannot proceed
```
Frontend symptom: widget posts a message, shows the user bubble + streaming dots placeholder, never receives any `data:` SSE frame. Loading state persists forever.

Both the authed (`/api/chat/conversations/...`) and anonymous (`/api/anonymous/chat/conversations/...`) endpoints hit identical failure modes.

**Root cause:**
FastAPI's `Depends(get_db)` provides a **request-scoped** SQLAlchemy session. It closes the moment the route handler `return`s. `StreamingResponse(event_stream(), ...)` is the value the handler returns — but the `event_stream()` async generator runs **after** the handler completes, driven by the ASGI server pulling chunks.

By the time `event_stream` executes its first `yield`, `db` is already closed. Any ORM-bound attribute access on objects the handler captured into the generator's closure (`session.chat_turns_used`, `conv.id`, `user.plan.tier`, etc.) raises `DetachedInstanceError`. Starlette wraps the ASGI app in a TaskGroup that catches and absorbs the exception, ending the response — but by then headers (200 + content-type) have already been flushed, and the body silently terminates with zero bytes.

The bug was invisible to the existing pytest suite because tests call `post_message()` and iterate `response.body_iterator` synchronously while the test's `db` fixture is still alive. Production differs: FastAPI closes the dep-session as soon as the handler returns, before the ASGI server begins iterating.

**Fix:**
Two coupled changes in `apps/api/app/api/routes/chat.py`:

1. **Snapshot every ORM attribute to a plain local BEFORE the generator yields.** Both `event_stream()` definitions (authed + anon) now read `conv.id`, `user.id`, `user.plan.tier`, `session.chat_turns_used`, `session.id`, `body.content` into `*_snap` locals immediately above the `async def event_stream()`. The generator references only the snapped values.

2. **Open a fresh DB session inside `_run_tool_loop`.** The loop persists assistant + tool messages as it iterates; those writes need a live session. The fresh session is bound to the **same engine** as the caller's `db`:
   ```python
   from sqlalchemy.orm import sessionmaker
   StreamMaker = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, future=True)
   stream_db = StreamMaker()
   try:
       async for frame in _run_tool_loop_inner(stream_db, ...): yield frame
   finally:
       stream_db.close()
   ```
   Using `db.get_bind()` instead of the global `SessionLocal` lets tests drive the loop against their in-memory SQLite engine without monkey-patching. Production binds to the production Postgres engine. Same code, both surfaces.

The outer `_run_tool_loop` is now a thin context manager owning the new session's lifecycle. The original loop body moved verbatim to `_run_tool_loop_inner` so callers (and the loop's existing tests) didn't need to change.

**Regression test:**
`tests/test_chat_endpoint.py::test_streaming_survives_request_session_close`. Calls `post_message()`, **explicitly closes the test's db session**, then iterates the `StreamingResponse`. Before the fix it produces an empty `frames` list (matching production). After: `started` → `token` → `done` as expected. The simulate-close-then-iterate pattern is the canonical pattern for any future streaming endpoint that touches ORM state.

**Files:** `apps/api/app/api/routes/chat.py`, `apps/api/tests/test_chat_endpoint.py`. Forward defense PR #53.

**Rule:**
**Any FastAPI route that returns a `StreamingResponse` whose generator touches ORM-bound objects MUST snapshot the values into plain locals before the first yield, AND open a fresh session inside the generator for any in-stream DB writes.** The `Depends(get_db)` session is closed by the time the generator runs — treat captured ORM objects as dead. The session-from-`db.get_bind()` pattern makes the fix testable without monkey-patching.

A related catch: this failure mode is **silent** — the browser sees a valid 200 + correct content-type, and only the lack of body bytes (and a Railway log message most people aren't watching) hints at the cause. Any future streaming endpoint should be exercised end-to-end with the close-then-iterate test pattern.

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
