# PRD-23a: Market Screener — Backend Spine (universe resolver + signal snapshot + scan + rank)

**Status**: Ready to build (pending Jimmy's review of the packet)
**Phase**: Market Screener mode (PRD-23 packet) — phase 1 of 3
**Depends on** (on `main`): PRD-22c slice a (#207 — the rule evaluator `_apply_rule_threshold`), PRD-16a/b (catalog + `StrategyJSON` + `BacktestEngine`), the universe standard `SP500_TICKERS`, cached daily `price_bars` + `PriceDataService`.
**Blocks**: PRD-23b (UI consumes scan/count + rank), PRD-23c.
**Effort**: ~1.5 weeks, single owner.
**Owner**: TBD
**Read first**: `HANDOFF-livermore-market-screener.md` (the packet plan + four principles + brick map).

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api). Read CLAUDE.md + apps/api/CLAUDE.md
(auto-loaded), then agent-system/plans/HANDOFF-livermore-market-screener.md.

Goal: build the backend spine of the Market Screener — the machinery that turns a
composed reading + a universe into a ranked basket. Five new bricks:

  1. universe_resolver(universe_id, user) -> list[str]  (default set + tier gate)
  2. signal_snapshot table + a daily warm cron + SignalSnapshotService
     (latest value of every catalog primitive for every universe symbol, from
      cached price_bars — NOT a live AV/FMP fetch)
  3. scan_service: evaluate a composed StrategyJSON rule-set as a boolean filter
     over the snapshot → matched symbols + per-symbol satisfied readings
  4. POST /api/screen/scan + POST /api/screen/count   (count = the live funnel)
  5. rank_service: backtest the MATCHED SUBSET via BacktestEngine, rank by return,
     cache (symbol, rule_hash, as_of_date); top-K cap with a cheap proxy pre-order

The rule evaluator is already on main (PRD-22c slice a) — reuse
engine._apply_rule_threshold's operator semantics so the scan filter matches the
backtest exactly.

PREREQUISITES (must be on main): PRD-22c slice a (#207), PRD-16a/b.

OUT OF SCOPE: the UI (PRD-23b), save/track (PRD-23c), intraday snapshot (PRD-23c),
net-new primitives (catalog frozen at ~72).

DEFINITION OF DONE: see §7 — including a REAL end-to-end demo on the live S&P 500
snapshot (a composed reading → a ranked basket), not just unit tests.
```

---

## 1. The problem

The catalog + composer can express a rich reading, but it can only point that reading at a user-supplied symbol. There is no engine that takes a reading + a broad universe and returns *which stocks match it now*. This PRD builds that engine: resolve a universe → pre-warm every primitive's latest value across it → filter to the matched basket at scan time → backtest + rank the survivors.

The expensive step (rank-by-backtest) operates on the **matched subset** (≪ universe) by construction — the rule does the narrowing first.

---

## 2. Design constraints

1. **Reuse the rule evaluator.** The scan filter and the rank backtest must evaluate a rule the *same way* — via the `_apply_rule_threshold` operator semantics shipped in PRD-22c slice a. Don't fork the logic.
2. **Pre-warm primitives, not rules.** The snapshot holds `~72 × ~500 ≈ 36k` primitive values, refreshed once/day. Any composed rule is then a cheap boolean filter over it. Never recompute a primitive per scan (HANDOFF pitfall A).
3. **No fabricated data.** Null cells for un-computable (symbol, primitive); excluded from referencing rules; loud logs (trap #20).
4. **Additive + no-regression.** No new `strategy_type`; `BacktestEngine` is reused read-only. The full backtest suite stays byte-identical.
5. **Postgres-safe + event-loop-safe.** `CREATE TABLE IF NOT EXISTS`; warm cron via `_run_async_in_thread`, no shared asyncio primitives (traps #1/#3/#21/#22).
6. **Python 3.9 compat.** `Optional[X]`, `List[X]`.

---

## 3. Implementation

### 3.1 Universe resolver — `app/services/screener/universe_resolver.py`

```python
def resolve_universe(universe_id: str, user) -> list[str]:
    # "sp500"        -> SP500_TICKERS
    # "sector_<key>" -> the sector basket (reuse US_SECTORS membership)
    # "watchlist"    -> the user's saved watchlist symbols
    # "portfolio"    -> the user's uploaded holdings (Portfolio Mode inherited_universe)
```

Pure (no entitlement logic — that gates at the endpoint, §3.4). A test asserts `sp500` returns ≥ a floor (expand-only invariant).

### 3.2 `signal_snapshot` table — `app/models/signal_snapshot.py`

```
signal_snapshot(
  symbol        VARCHAR(16),
  primitive_id  VARCHAR(64),
  resolution    VARCHAR(8)  DEFAULT 'daily',  -- 'intraday' lands in PRD-23c
  value         DOUBLE,                        -- encoding by output_kind, §3.3
  as_of_date    DATE,
  computed_at   TIMESTAMP,
  PRIMARY KEY (symbol, primitive_id, resolution)
)
```

`CREATE TABLE IF NOT EXISTS` in the shared migrations block. No FK to `users`. ~36k rows — log the count (#10); upsert idempotently (one row per key).

### 3.3 Snapshot value encoding (by `output_kind`)

The scan filter reads `value` consistently per kind:

| output_kind | `value` stored | scan reads |
|---|---|---|
| VALUE | the scalar (RSI = 28.4) | `< / >` threshold |
| EVENT | fired state at latest bar (1.0 / 0.0) | `fires` → `!= 0` |
| CROSS | directional state (+1 / 0 / −1) | `crosses_up` → `== +1` |
| LEVEL | boolean as 0/1 | `is_true` → bool |
| REGIME | category code (0/1, or small int) | `equals` → `== code` |
| DISTANCE | the signed pct | `in_range` → between |

Computed from cached bars: for each symbol, fetch the price frame once (`PriceDataService.get_price_frame`) and evaluate each primitive's provider at the **last bar**. No live AV/FMP fetch for the daily snapshot.

### 3.4 Warm cron + `SignalSnapshotService` — `app/jobs/signal_snapshot_job.py`

Runs once post-close. MUST use the `_run_async_in_thread` bridge (trap #21), not touch singletons holding shared asyncio primitives (trap #22), and `logger.exception` on failure (trap #20). Writes the snapshot for the full universe. `SignalSnapshotService` exposes `get_snapshot(universe, resolution='daily')` → an in-memory frame for the scan.

### 3.5 Scan + rank

**`scan_service.scan(universe_id, strategy_json, as_of)`** →
1. `symbols = resolve_universe(...)`
2. load the snapshot rows for those symbols (one indexed query → in-memory frame)
3. compile each rule to a boolean mask over its `primitive_id` column, honoring the operator (reuse `_apply_rule_threshold` semantics), fold with the rule's AND/OR `logic_with_prior`
4. return matched symbols + **per-symbol satisfied readings** + the snapshot `as_of_date`

**`POST /api/screen/scan`** wraps it; **`POST /api/screen/count`** returns `len(matched)` only (the live funnel — < 100ms). Both are pure reads over the snapshot — no backtest.

**`rank_service.rank(matched, strategy_json)`** → backtest each matched symbol via `BacktestEngine` (matches ≪ universe), rank by total return / CAGR, cache `(symbol, rule_hash, as_of_date)`, cap to top-K (cheap-proxy pre-order; `log()` the cap). Streams/paginates so 23b renders the basket first and fills metrics progressively.

### 3.6 Entitlement (gate at the endpoint)

`POST /api/screen/scan` via `require_entitlement` — Scout → capped universe or N scans/day; Strategist/Quant → full set. `allow_anonymous=True` with a demo universe (one sector) so the mode is explorable pre-sign-in (trap #18); rank-by-backtest is sign-in-gated.

---

## 4. Testing

- **Snapshot**: warm job writes one row per (symbol, primitive_id), idempotent on re-run (no dupes); value encoding per `output_kind` correct; a symbol with no bars → null cell, excluded (no-fake-data); `as_of_date` = latest cached bar's date (backend TZ).
- **Scan/rank**: filter correctness per `output_kind` on a hand-seeded snapshot → known matches; AND/OR fold matches the engine's `logic_with_prior`; `/count` == `len(scan().matched)`; rank orders by return; `(symbol, rule_hash)` cache hit on the second call; top-K cap logs what it dropped.
- **No-regression**: full backtest suite byte-identical (additive; no new strategy_type).
- **Perf**: scan over a 500-symbol snapshot < 300ms; `/count` < 100ms.
- **Static-import smoke**: new route + model + job resolve (`from app.main import app`).

---

## 5. Pre-merge checklist

1. `cd apps/api && python3 -m pytest -q` — green.
2. Static-import smoke resolves the new route/model/job.
3. Postgres-safe DDL (`CREATE TABLE IF NOT EXISTS`; `String(36)` user cols, no FK to users).
4. Warm-cron event-loop audit (`_run_async_in_thread`; no shared asyncio primitives; `logger.exception`).
5. Py3.9 compat (`grep "| None"` empty); env-var audit if any added.
6. **The live demo** (§7 DoD) recorded in the PR — a real scan → ranked basket on the S&P 500 snapshot.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Snapshot stale / silently old | `as_of_date` stamped + shown; freshness check in `/health`; warm failure via `logger.exception` (trap #20) |
| Scan recomputes per request (slow) | Pre-warm primitives; scan is an in-memory filter over the snapshot |
| Rank cost explodes on a loose rule | Only matches backtested (≪ universe); top-K cap + `(symbol, rule_hash)` cache; cheap-proxy pre-order |
| Warm cron blocks loop / wedges deploy | `_run_async_in_thread` (trap #21); no singleton asyncio primitives (trap #22) |
| Fabricated snapshot values | Null cells, never placeholders; excluded from referencing rules |
| Universe silently shrinks | Read-only over `SP500_TICKERS`; a test asserts size ≥ floor |

---

## 7. Definition of done

- [ ] `universe_resolver` with the default set + tier gate (+ expand-only test)
- [ ] `signal_snapshot` table + warm cron (event-loop-safe) + `SignalSnapshotService`
- [ ] `scan_service` + `POST /api/screen/scan` + `POST /api/screen/count`
- [ ] `rank_service` (backtest matched subset, ranked, `(symbol, rule_hash)` cached)
- [ ] Tests per §4; no-regression suite green; smoke resolves
- [ ] **Live demo**: a composed reading scans the real S&P 500 snapshot and returns a real ranked basket — recorded in the PR (Mr Gu's "ensure the flow actually works" bar)
- [ ] PR merged to `main` with green CI; brick inventory (HANDOFF §5) updated

---

## 8. Hand-off to PRD-23b

When 23a is on `main`: 23b wires the `screen_mode` FlowDefinition to `POST /api/screen/scan` + `/count` (the live funnel) + the rank stream, and the `<UniverseSelector>` to `universe_resolver`'s default set. The scan response's per-symbol satisfied-readings drive the "why this matched" UI.

---

*PRD drafted 2026-06-16. Part of the Market Screener packet (`HANDOFF-livermore-market-screener.md`). Supersedes §3.2–3.5 of the single-doc draft `PRD-23-market-screener-mode.md`.*
