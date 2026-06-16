# PRD-23: Market Screener Mode — "Screen the market" (signal-driven stock discovery)

**Status**: Draft — pending Jimmy's review (do not build until approved)
**Phase**: New entry mode (market-out discovery), built on Custom Mode v2
**Depends on** (all shipped):
  - PRD-13a — flow runtime (`src/lib/flows/`, `FlowDefinition`, `startFlow`, `/flow/[flowId]` shell)
  - PRD-16a — signal catalog + primitives + `GET /api/signal-primitives` + KB `match-templates`
  - PRD-16b — Custom Build composer (canvas, rule cards, AND/OR fold, canvas→`StrategyJSON`)
  - PRD-22a — `output_kind` semantics layer (drives the kind-specific rule widgets)
  - PRD-22b — the screenable primitive set (frozen at ~72 for v1 of this mode)
  - PRD-16c / PRD-19 — active-execution cron + notifications + live dashboard (the "track" half)
  - The universe standard `SP500_TICKERS` + cached daily `price_bars` + `PriceDataService`
**Soft dependency**: PRD-22c (composer kind-dispatch widgets) — the polished intent-first
  compose UX renders the CROSS/EVENT/REGIME/DISTANCE widgets PRD-22c ships. The screener can
  ship 23a (backend) without it; 23b's composer needs it (or ships a degraded VALUE-only UI).
**Blocks**: nothing downstream yet — this is a leaf mode.
**Effort**: ~3–4 weeks, phased: **23a** backend spine · **23b** mode + UI · **23c** discover→track + intraday.
**Owner**: TBD
**Source**: this PRD + the design conversation that produced it (2026-06-16). The screener UX
  (intent-first compose → scan → ranked basket → drill/track) and the snapshot architecture are
  specified here; there is no separate design HTML.

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md first
(auto-loaded), then apps/api/CLAUDE.md and apps/web/AGENTS.md.

Goal: ship "Screen the market" — a market-OUT entry mode. Today every mode is asset-IN:
the user supplies a ticker ("backtest symbol") and the universe IS that ticker. This mode
inverts it — the user picks a UNIVERSE (S&P 500 by default), composes a "reading" (a rule
over the signal catalog), and the rule SCREENS the universe down to a small matched basket;
only that basket is backtested, ranked by return, and offered for save+track.

Three phased deliverables (one PR each, minimum):

  23a — Backend spine:
    - universe_resolver (universe_id -> [symbols]); default set + tiering
    - signal_snapshot table + daily warm cron + SignalSnapshotService
      (latest value of every primitive for every universe symbol, from cached bars)
    - scan_service: evaluate a composed rule as a boolean filter over the snapshot
    - POST /api/screen/scan (universe + rule -> matched basket + satisfied readings)
    - POST /api/screen/count (live match count, for the composer funnel)
    - rank: backtest the matched subset (reuse BacktestEngine), cache (symbol, rule_hash)

  23b — Mode + UI:
    - screen_mode FlowDefinition (register it; the /flow shell renders it)
    - <UniverseSelector> (replaces the "backtest symbol" input)
    - <ReadingComposer> (extends the PRD-16b composer; intent chips + live count + kind widgets)
    - <ScreenResults> (progressive ranked basket; drill into the existing backtest detail)

  23c — Discover -> track + intraday:
    - save a discovered basket as a SavedStrategy; cron re-scans, notifies on NEW entrants
    - intraday snapshot option (reuse the PRD-16c intraday path)

PREREQUISITES (must be on main): PRD-16a/b, PRD-22a, the catalog frozen at ~72 primitives.

OUT OF SCOPE:
  - Net-new primitives — the catalog is FROZEN at the current set for this mode's v1.
  - Options / short-interest / VIX-term-structure data (separate PRD).
  - User-uploaded custom Python signals.

DEFINITION OF DONE: see Section 7.
```

---

## 1. The problem

Every entry mode Livermore ships today is **asset-in**: Pick-an-Asset, Upload-Portfolio, and
Build-from-Scratch all start from a symbol (or a handful) the user already has in mind. In
Custom Build the user types tickers into a symbol picker, and the strategy's `universe` IS
that list — so the "backtest symbol" *is* the universe. The catalog + composer can express a
rich market reading ("momentum turning, with a volume surge, inside a confirmed uptrend"), but
they can only point that reading at a symbol the user supplies. There is no **market-out**
path: *"I don't have a ticker — show me which stocks are reading this right now."*

That is the single most valuable thing a quant tool can do, and we don't have it. The
**Market Screener** inverts the relationship:

> **The universe is given (broad), and the composed rule discovers the names.**

The rule is the screen: it filters ~500 stocks down to a small matched basket; only the
survivors get backtested and ranked. Discovery (scan) → validation (backtest) → monitoring
(track) — all powered by the *same* composed reading the user authored once.

---

## 2. Design constraints (load-bearing)

The four principles, stated identically across every packet in this repo.

### Principle 1 — Reuse, don't replicate

This mode must NOT add: a new composer (extend the PRD-16b canvas), a new strategy object
(reuse `StrategyJSON`), a new backtester (reuse `BacktestEngine`), a new catalog/primitive
system (reuse PRD-16a/22a), a new notification/dashboard stack (reuse PRD-16c/19), or a new
universe definition (reuse `SP500_TICKERS` + the sector/macro baskets). See §3.1 for the full
reuse-vs-new map. The genuinely new bricks are small: a **universe resolver**, a **signal
snapshot**, a **scan endpoint**, and a **results surface**.

### Principle 2 — LEGO bricks

23a ships the backend bricks (snapshot + scan + rank) that 23b's UI consumes; 23b ships the
mode flow that 23c's track integration extends. The brick inventory in §3.1 is canonical.

### Principle 3 — Mode = `FlowDefinition`, not a route

"Screen the market" is a new `FlowDefinition` registered via `registerFlow`, rendered by the
universal `/flow/[flowId]` shell — **not** a bespoke page. Triggered from Home (PRD-11 entry
picker) via `startFlow("screen_mode", …)`. This is the same contract Portfolio Mode and Custom
Build use; moving between modes must not cost a context switch.

### Principle 4 — UX consistency + sub-300ms perceived load

This is the make-or-break constraint, and it is achievable *because of the snapshot*:
- **The scan is a filter over a pre-warmed snapshot, not a live 500-symbol crunch** — so
  universe→basket is sub-300ms (in-memory set ops over ~36k cached values).
- **Live match count during composition** — every rule the user adds re-filters the snapshot
  and updates a count ("add 'volume surge' → 47 → 18 match"). The funnel tightening in real
  time IS the discovery loop. This is the single most compelling part of the UX; treat it as a
  first-class feature, not a nicety.
- **Progressive ranking, never a blank page** — the matched basket renders instantly
  (proxy-ordered by signal strength / dollar volume); the backtest-return metrics stream in
  row-by-row and the list re-sorts as they land (the PRD-I staged-loading pattern). Only ~18
  names are backtested, not 500, so this is fast and bounded.
- **Date-stamp freshness** — every result carries "as of <close date>" (the date-visibility
  product invariant). Intraday (23c) refreshes the snapshot on the cron cadence.

### Additional invariants

- **No fabricated data** (repo-wide rule). The snapshot is computed from real cached bars or
  the cell is null + the symbol is excluded from rules that need it — never a placeholder
  value. Ranks come from real backtests. If a primitive can't be computed for a symbol, it
  fails loudly in the warm job's logs (`logger.exception`, trap #20), not silently.
- **Universe is a STANDARD, expand-only** (product invariant). The screener reads
  `SP500_TICKERS` / sector baskets; it must never silently shrink them.

---

## 3. Implementation

### 3.1 The lego-brick map (reuse vs new)

| Brick | Status | Source / new file |
|---|---|---|
| Flow runtime + `/flow` shell + `startFlow` | ♻️ reuse | `apps/web/src/lib/flows/` (PRD-13a) |
| Composer canvas + rule cards + AND/OR fold | ♻️ reuse | PRD-16b-1/2 (`logic_with_prior`) |
| Canvas → `StrategyJSON` converter | ♻️ reuse | PRD-16b-3 |
| Signal catalog + primitives + `output_kind` | ♻️ reuse | PRD-16a / 22a (frozen at ~72) |
| `get_signal_provider` / `get_signal_frame` | ♻️ reuse | `backtester/signal_provider.py` |
| `BacktestEngine.run()` + `StrategyJSON` | ♻️ reuse | `backtester/engine.py` |
| KB `match-templates` (recommended defaults) | ♻️ reuse | PRD-16a-3 |
| Active-execution cron + dashboard + notifications | ♻️ reuse | PRD-16c-3/6, PRD-19 |
| `SavedStrategy` / `BacktestRecord` two-table model | ♻️ reuse | PRD-16b / PRD-19 |
| Universe standard (`SP500_TICKERS`, sector/macro baskets) | ♻️ reuse | `data/sp500_tickers.py` |
| Cached daily `price_bars` + `PriceDataService` | ♻️ reuse | existing |
| Staged backtest-loading UI | ♻️ reuse | PRD-I |
| Per-`output_kind` rule widgets (CROSS/EVENT/REGIME/DISTANCE…) | 🔜 soft-dep | PRD-22c |
| **Universe resolver** (`universe_id → [symbol]`) | 🆕 23a | `services/screener/universe_resolver.py` |
| **`signal_snapshot` table** | 🆕 23a | `models/signal_snapshot.py` |
| **Snapshot warm cron + `SignalSnapshotService`** | 🆕 23a | `jobs/signal_snapshot_job.py`, `services/screener/snapshot_service.py` |
| **Scan service** (rule → matched basket over snapshot) | 🆕 23a | `services/screener/scan_service.py` |
| **`POST /api/screen/scan` + `/count`** | 🆕 23a | `api/routes/screener.py` |
| **Rank** (backtest matched subset, `(symbol, rule_hash)` cache) | 🆕 23a | `services/screener/rank_service.py` |
| **`screen_mode` FlowDefinition** | 🆕 23b | `apps/web/src/lib/flows/modes/screen-mode.tsx` |
| **`<UniverseSelector>` / `<ReadingComposer>` / `<ScreenResults>`** | 🆕 23b | `apps/web/src/lib/flows/bricks/` |
| **Intent / reading layer** (`reading` + `intent_group` catalog fields) | 🆕 23b | additive catalog fields (see §3.6) |
| **Discover → track** (basket → SavedStrategy → notify on new entrants) | 🆕 23c | extends PRD-19 dispatcher |

### 3.2 Universe resolver (23a)

A pure function `resolve_universe(universe_id, user) -> list[str]`:

- `sp500` (default) → `SP500_TICKERS`
- `sector_<key>` → the sector basket (reuse `US_SECTORS` membership)
- `watchlist` → the user's saved watchlist symbols
- `portfolio` → the user's uploaded holdings (Portfolio Mode `inherited_universe`)

**Tiering** (reuse `entitlements.TIER_CAPS`): Scout → a single capped universe (e.g. sector
only, or top-N by market cap); Strategist/Quant → full S&P 500 + sectors + custom. Gate at the
scan endpoint, not the resolver, so the resolver stays pure/testable.

### 3.3 Signal snapshot (23a) — the spine

A table that holds the **latest** value of every primitive for every universe symbol, warmed
once per day after close:

```
signal_snapshot(
  symbol        VARCHAR(16),
  primitive_id  VARCHAR(64),
  resolution    VARCHAR(8)   DEFAULT 'daily',   -- 'daily' | 'intraday' (23c)
  value         DOUBLE,                          -- scalar / fired-state / boolean-as-0-1
  as_of_date    DATE,                            -- the bar the value is computed at
  computed_at   TIMESTAMP,
  PRIMARY KEY (symbol, primitive_id, resolution)
)
```

- ~72 primitives × ~500 symbols ≈ **36k rows** — tiny; no disk-headroom concern (trap #10
  still: log the row count). Upsert idempotently (one row per (symbol, primitive_id, resolution)).
- **Value encoding by `output_kind`**: VALUE → the scalar (RSI = 28.4); EVENT/CROSS → the fired
  state at the latest bar (+1 / 0 / −1); LEVEL/REGIME → 1.0/0.0 (or a small categorical code);
  DISTANCE → the signed pct. The encoding is documented per kind so the scan filter reads it
  consistently.
- **Computed from cached bars** via the existing providers — for each symbol, fetch the price
  frame once (`PriceDataService.get_price_frame`) and evaluate each primitive's `_compute` at
  the last bar. No live AV/FMP fetch for the daily snapshot (data is already maintained).
- **Warm cron** (`signal_snapshot_job`) runs post-close. It MUST follow the event-loop rules:
  run via the `_run_async_in_thread` bridge (trap #21) and not touch singletons holding shared
  asyncio primitives (trap #22). Failures use `logger.exception` (trap #20), not `.warning`.
- **No-fake-data**: a symbol with no bars or a primitive that raises yields a *null* cell that
  is excluded from any rule referencing it — never a synthesized value.

### 3.4 Scan service (23a)

`scan(universe_id, strategy_json, as_of) -> ScanResult`:

1. `symbols = resolve_universe(universe_id, user)`
2. Load the snapshot rows for those symbols (one indexed query → in-memory frame).
3. Compile each rule in `strategy_json` to a boolean mask over the snapshot column for its
   `primitive_id`, honoring `output_kind` (VALUE → `< / >` threshold; CROSS → `== ±1`; EVENT →
   `== 1`; LEVEL/REGIME → `== state`; DISTANCE → range). Fold with the rule's AND/OR logic
   (reuse the same fold semantics as the engine's `logic_with_prior`).
4. Return the matched symbols + **per-symbol satisfied readings** (so the UI can show *why*
   each name matched) + the snapshot `as_of_date`.

`POST /api/screen/scan` wraps this; `POST /api/screen/count` returns just `len(matched)` (the
live funnel — must stay <100ms). Both are pure reads over the snapshot — no backtest yet.

### 3.5 Rank (23a)

`rank(matched, strategy_json) -> list[RankedMatch]`:

- Backtest the rule on **each matched symbol** via `BacktestEngine` (matches ≪ universe, so
  bounded). Rank by total return / CAGR (configurable).
- **Cache** keyed by `(symbol, rule_hash, as_of_date)` so re-scans and pagination are free.
- **Top-K cap**: if matches are large, pre-order by a cheap proxy (signal strength /
  dollar volume) and backtest only the top-K for the return ranking; `log()` the cap (no silent
  truncation).
- The API streams/paginates so the UI can render the basket first and fill metrics
  progressively (§Principle 4).

### 3.6 Mode + UI (23b)

- **`screen_mode` FlowDefinition** — steps: `pick-universe → compose-reading → results`. Saves
  flow state to `sessionStorage` like every mode; registered in `registry.ts`.
- **`<UniverseSelector>`** — the few default universes (§3.2) as cards/chips; tier-gated. This
  is the brick that replaces the "backtest symbol" input.
- **`<ReadingComposer>`** — extends the PRD-16b canvas with: (a) **intent chips** at the top
  (the `intent_group` taxonomy), (b) the per-`output_kind` rule widgets (PRD-22c), and (c) a
  **live match count** wired to `/api/screen/count` that updates as rules change.
- **`<ScreenResults>`** — the ranked basket: ticker · satisfied readings · streamed backtest
  metric · sparkline; "as of <date>"; click → the existing single-asset backtest detail
  (drill-in, fully reused). A "Save + track this screen" CTA hands off to 23c.
- **Reading layer (additive catalog fields)** — to make the composer intent-first, add two
  additive fields to `SignalPrimitive` (same pattern as PRD-22a): `reading: str` (the
  plain-English headline a trader reads when it fires) and `intent_group: str` (the chip it
  lives under). Backfill the ~72 primitives. This is editorial (Jimmy's gate) and direction is
  handled in the widget copy (a CROSS reads "turning up" / "rolling over" per the picker).

### 3.7 Discover → track + intraday (23c)

- **Save**: a discovered screen becomes a `SavedStrategy` (rule + `universe_id`). The existing
  active-execution cron re-runs the scan on the cron cadence; when a **new** symbol enters the
  matched basket, dispatch the existing notification (reuse PRD-19's `SignalEvent` + dispatcher
  + digest). The live dashboard's universe-watch panel already renders "which names are
  triggering" — point it at the saved screen.
- **Intraday option**: warm an `resolution='intraday'` snapshot on the PRD-16c intraday cadence
  (the FMP ~15-min-delayed path) so the screen can run during market hours. Daily ships first.

### 3.8 Entitlement

Screening the full market is a Strategist/Quant feature. Gate `POST /api/screen/scan` via
`require_entitlement` (Scout → capped universe or N scans/day). Anonymous users get a demo
universe (e.g. one sector) so the mode is explorable pre-sign-in (`allow_anonymous=True`,
trap #18) — but rank-by-backtest is sign-in-gated.

---

## 4. Testing

### 4.1 Snapshot (23a)
- Warm job writes one row per (symbol, primitive_id), idempotent on re-run (no dupes).
- Value encoding per `output_kind` is correct (VALUE scalar, EVENT ±1/0, LEVEL/REGIME 0/1).
- A symbol with no bars → null cell, excluded from rules referencing it (no-fake-data).
- Freshness: `as_of_date` equals the latest cached bar's date (computed in backend TZ).

### 4.2 Scan + rank (23a)
- Scan filter correctness for each `output_kind` (a hand-seeded snapshot → known matches).
- AND/OR fold matches the engine's `logic_with_prior` semantics on the same rule.
- `/count` equals `len(scan().matched)` for the same input.
- Rank orders by backtest return; `(symbol, rule_hash)` cache hit on the second call.
- Top-K cap logs what it dropped.

### 4.3 Flow + UI (23b)
- `screen_mode` registers and renders via the `/flow` shell; types-first in `contracts.ts`.
- `<ReadingComposer>` live count calls `/count` and debounces; `<ScreenResults>` renders basket
  before metrics arrive then re-sorts (progressive).

### 4.4 No-regression
- The full backtest suite stays byte-identical — this mode is additive; it reuses the engine
  read-only and adds no new strategy_type. Existing strategies are untouched.

### 4.5 Perf
- Scan over a 500-symbol snapshot returns < 300ms (in-memory); `/count` < 100ms.

---

## 5. Pre-merge checklist (per phase)

1. `cd apps/api && python3 -m pytest -q` — green.
2. `cd apps/web && npm run build` — types compile.
3. Static-import smoke (`python3 -c "from app.main import app; print(len(app.routes))"`) — new
   route/model/job resolves.
4. Postgres-safe DDL: `signal_snapshot` created via `CREATE TABLE IF NOT EXISTS` in the shared
   block; `user`-scoped columns use `String(36)` with no FK to `users` (apps/api/CLAUDE.md #1/#3).
5. Warm-cron event-loop audit: `_run_async_in_thread` bridge; no shared asyncio primitives
   (traps #21/#22); `logger.exception` on failure (trap #20).
6. Py3.9 compat (`grep "| None"` empty); env-var audit if any added.
7. Editorial review of the `reading` / `intent_group` copy (23b).

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Snapshot stale / silently old | `as_of_date` stamped + shown; a freshness check in `/health`; warm-cron failure surfaces via `logger.exception`, not `.warning` (trap #20) |
| Scan feels slow / blank page | Snapshot pre-warm makes scan in-memory (<300ms); live count during compose; progressive rank render over an already-populated basket |
| Rank backtest cost explodes on a loose rule | Only matches are backtested (≪ universe); top-K cap + `(symbol, rule_hash)` cache; cheap proxy pre-order |
| Warm cron blocks the event loop / wedges a deploy | `_run_async_in_thread` bridge (trap #21); no singleton asyncio primitives (trap #22) |
| Fabricated snapshot values | Null cells, never placeholders; excluded from referencing rules; loud logs on compute failure |
| Universe silently shrinks | Read-only over `SP500_TICKERS`; the expand-only invariant; a test asserts universe size ≥ floor |
| Compose UX needs PRD-22c widgets | 23a ships independent of UI; 23b either lands after 22c or ships a degraded VALUE-only composer first |
| Disk growth from snapshot | ~36k rows is trivial; still log the row count (trap #10) and upsert (no unbounded growth) |

---

## 7. Definition of done

**23a (backend spine)**
- [ ] `universe_resolver` with the default set + tier gate
- [ ] `signal_snapshot` table + warm cron (event-loop-safe) + `SignalSnapshotService`
- [ ] `scan_service` + `POST /api/screen/scan` + `POST /api/screen/count`
- [ ] `rank_service` (backtest matched subset, ranked, cached)
- [ ] Tests per §4.1/4.2/4.5; no-regression green; smoke resolves

**23b (mode + UI)**
- [ ] `screen_mode` FlowDefinition registered + rendered via `/flow`
- [ ] `<UniverseSelector>` replaces the symbol input; `<ReadingComposer>` with intent chips +
      live count; `<ScreenResults>` progressive ranked basket + drill-in
- [ ] `reading` + `intent_group` additive catalog fields backfilled (editorial review passed)
- [ ] `contracts.ts` types-first; `npm run build` clean

**23c (discover → track + intraday)**
- [ ] Save a screen → `SavedStrategy`; cron notifies on new basket entrants (reuse PRD-19)
- [ ] Intraday snapshot option (reuse PRD-16c intraday path)

**Packet**
- [ ] Each phase merged to `main` with green CI
- [ ] Brick inventory (§3.1) kept current at each PR close
- [ ] `agent-system/WORK_LOG.md` + `docs/PROJECT_BACKLOG.md` updated

---

## 8. Hand-off / future

- **PRD-22c** ships the kind-widgets the composer renders; sequencing 23b after it gives the
  full intent-first UX. If 23b lands first, it ships VALUE-only and lights up when 22c merges.
- **More universes** — Nasdaq-100, custom user lists, multi-asset (once non-equity universes
  are defined) — additive to the resolver.
- **Net-new primitives** resume after this mode proves the loop (the catalog was frozen at ~72
  for v1; the remaining PRD-22b families expand what's screenable).
- **Saved screens as a library** — discovered baskets become shareable, like saved strategies.

---

*PRD drafted 2026-06-16. Cross-references: the four principles + Custom Mode HANDOFF
(`HANDOFF-livermore-custom-mode.md`), the catalog v2 packet (PRD-22a/b/c), the flow runtime
(PRD-13a, `apps/web/AGENTS.md`), and the active-execution/notifications stack (PRD-16c/19).
This is a new mode under the Mode = FlowDefinition principle — it adds no bespoke route.*
