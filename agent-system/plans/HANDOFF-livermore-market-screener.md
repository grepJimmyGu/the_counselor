# HANDOFF: Livermore Market Screener — "Screen the market" (signal-driven stock discovery)

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first — including §0, which governs the whole packet.** It is the entry point for the three-PRD packet that evolves "Build from scratch" into **one unified Compose & Run mode** (§0 — *a single symbol is just a universe of size 1*): the user picks a universe (1 symbol → the whole S&P 500), composes a "reading" over the signal catalog, and runs it — a direct backtest for entered symbols, or a screen-to-ranked-basket for a standing universe. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: ~3–4 weeks for the full packet (PRD-23a → 23b → 23c), single owner sequential.
**Total scope**: 3 PRDs — **PRD-23a (backend spine)**, **PRD-23b (mode + UI)**, **PRD-23c (discover → track + intraday)**.
**Sprint goal**: Take strategy authoring from "I bring a ticker, the rule measures it" to "I bring a reading, the rule discovers the tickers" — a ranked basket of stocks that match the reading *right now*, on the frozen ~72-primitive catalog.

---

## 0. Design revision (2026-06-16) — ONE unified "Compose & Run" mode (read this first)

Jimmy's call after reviewing the first draft: the screener is **not** a separate mode from
"Build from scratch." The two are identical in the middle — same composer, same catalog, same
`StrategyJSON` — and differ only at the edges (input target + output action). So they **merge
into one unified flow**:

> **A single symbol is just a universe of size 1.** The universe selector subsumes the old
> "backtest symbol" input — `Enter your own symbol(s)` becomes the narrowest *tier* of the same
> selector, alongside `S&P 500` · `Sector` · `My watchlist` · `My portfolio`.

**The one flow:** pick a universe (1 symbol → 500) → compose a reading → **run**. The run adapts
to universe size:
- **Entered symbols (1 or a few)** → the existing **direct backtest** path (no snapshot needed).
  This *is* today's "Build from scratch."
- **A standing universe (S&P 500 / sector)** → the **snapshot scan → rank the survivors** — the
  screener.
- **One results surface that adapts:** size 1 → the existing backtest detail; many → the ranked
  basket. Save + track is shared.

**What this changes vs the draft below:**
- There is **no separate `screen_mode` FlowDefinition.** PRD-23b **extends `custom_build_mode`**
  (Build from scratch) with the universe selector (incl. the entered-symbols tier) + the
  scan/results path. **Where the slice PRDs below still say "screen_mode," read: the
  universe-screening path of the one unified `custom_build` flow.**
- The Home picker keeps a distinct **"Screen the market"** entry tile (different intent, no ticker
  in hand) — but it drops into the *same* flow with a standing universe preselected; "Build from
  scratch" drops into the same flow with the entered-symbols tier preselected.
- **Power unlocked:** a reading composed once can be backtested on a name **and** used to screen a
  universe — no re-composing.

The rest of this HANDOFF + PRD-23a/b/c describe the machinery; this section is the framing that
governs all of it.

---

## 1. TL;DR

Every entry mode Livermore ships today is **asset-in** — Pick-an-Asset, Upload-Portfolio, Build-from-Scratch all start from a symbol the user supplies, and in Custom Build the "backtest symbol" input *is* the universe. There is no market-out path: *"I don't have a ticker — show me what's reading X right now."*

The Market Screener inverts the relationship:

> **The universe is given (broad), and the composed rule discovers the names.**

The rule is the screen: it filters ~500 stocks down to a small matched basket; only the survivors get backtested and ranked. **Discovery (scan) → validation (backtest) → monitoring (track) — all powered by the same composed reading the user authored once.**

The packet:

- **PRD-23a (~1.5 wk)**: the backend spine — universe resolver + a daily `signal_snapshot` pre-warm + the scan/count endpoints + rank-by-backtest. Headless-testable; **its DoD includes a real end-to-end demo on live data**, not just unit tests.
- **PRD-23b (~1.5 wk)**: **extend `custom_build_mode`** (not a new mode — §0) — the universe selector (incl. the entered-symbols tier) *replaces* the bare symbol input + the intent-first reading composer (with the live match-count funnel) + the size-adaptive results surface.
- **PRD-23c (~1 wk)**: save a discovered basket → cron notifies on new entrants (reuse PRD-19) + the intraday snapshot option.

**Prerequisite (hard):** PRD-22c's engine operator-dispatch (slice a, shipped #207) — the screener's scan filter + rank backtest evaluate composed rules via the *same* `_apply_rule_threshold` operators (`fires`/`crosses_up`/`in_range`/…). The rest of 22c (widgets + reading layer) makes the composer intent-first; 23b reuses it.

---

## 2. The four design principles (load-bearing)

Same four principles as every PRD packet in this repo. Stated identically across the catalog-v2 HANDOFF, the Custom Mode HANDOFF, and this one — moving between packets shouldn't cost a context switch.

### Principle 1 — Reuse, don't replicate

This packet must NOT add: a new composer (extend PRD-16b's `<CustomBuildRuleComposer>`), a new strategy object (reuse `StrategyJSON`), a new backtester (reuse `BacktestEngine`), a new catalog/primitive system (reuse PRD-16a/22a), a new notification/dashboard stack (reuse PRD-16c/19), or a new universe definition (reuse `SP500_TICKERS` + the sector/macro baskets). The genuinely new bricks are small — see §5. **~Half the mode is reused.**

### Principle 2 — LEGO bricks

23a ships the backend bricks (snapshot + scan + rank) that 23b's UI consumes; 23b ships the mode flow that 23c's track integration extends. The brick inventory in §5 is canonical.

### Principle 3 — Mode = `FlowDefinition`, not a route

Per §0, this is **one unified mode** — the existing `custom_build_mode` FlowDefinition, *extended* with a universe selector + the scan/results path. **No new `FlowDefinition`.** The Home picker's "Screen the market" tile and its "Build from scratch" tile both `startFlow("custom_build_mode", …)` with a different universe tier preselected (standing universe vs entered symbols), rendered by the universal `/flow/[flowId]` shell — **not** a bespoke page. Same contract Portfolio Mode and Custom Build use.

### Principle 4 — UX consistency + sub-300ms perceived load

Achievable *because of the snapshot*:
- **The scan is a filter over a pre-warmed snapshot, not a live 500-symbol crunch** — universe→basket is sub-300ms (in-memory set ops over ~36k cached values).
- **Live match count during composition** — every rule the user adds re-filters the snapshot and updates a count ("add 'volume surge' → 47 → 18 match"). The funnel tightening in real time IS the discovery loop. **First-class feature, not a nicety.**
- **Progressive ranking, never a blank page** — the matched basket renders instantly (proxy-ordered); the backtest-return metrics stream in row-by-row and the list re-sorts (PRD-I staged-loading pattern). Only ~18 names are backtested, not 500.
- **Date-stamp freshness** — every result carries "as of <close date>" (the date-visibility product invariant).

### Additional invariants (repo-wide)

- **No fabricated data.** The snapshot is computed from real cached bars or the cell is null + the symbol is excluded from rules that need it — never a placeholder. Ranks come from real backtests. A primitive that can't be computed fails loudly (`logger.exception`, trap #20), not silently.
- **Universe is a STANDARD, expand-only.** The screener reads `SP500_TICKERS` / sector baskets; it must never silently shrink them.

---

## 3. Reading order (for a coding agent fresh to this work)

1. **`CLAUDE.md`** (repo root) — auto-loaded. Branch / PR / Python-3.9-compat conventions.
2. **`agent-system/PARALLEL_WORK.md`** — claim a row in the Active Sessions table.
3. **This file** — the three-PRD packet plan + the four principles + the brick map.
4. **`agent-system/plans/HANDOFF-livermore-custom-mode.md`** — the parent HANDOFF; the composer + catalog + active-execution stack this mode reuses.
5. **`apps/api/app/services/backtester/engine.py`** — `_evaluate_custom_build_block` + `_apply_rule_threshold` (the rule evaluator the scan + rank call).
6. **`apps/api/app/data/sp500_tickers.py`** + `market_pulse_service.py` (`US_SECTORS`) — the universe standard.
7. **`apps/web/src/lib/flows/`** — the flow runtime (`FlowDefinition`, `startFlow`, the `/flow` shell).
8. **Your assigned PRD** — `PRD-23a-screener-backend-spine.md`, `PRD-23b-screener-mode-ui.md`, or `PRD-23c-screener-track-intraday.md`.

---

## 4. The three PRDs

| PRD | Title | Status | Owner | Effort | Depends on | Blocks |
|-----|-------|--------|-------|--------|------------|--------|
| **PRD-23a** | Backend spine — universe resolver + signal snapshot + scan/count + rank | ✅ [Ready](PRD-23a-screener-backend-spine.md) | TBD | ~1.5 wk | PRD-22c slice a (shipped), PRD-16a/b, `SP500_TICKERS` | 23b, 23c |
| **PRD-23b** | Mode + UI — **extend `custom_build_mode`**: universe selector (incl. entered-symbols tier) + reading composer + size-adaptive results | ✅ [Ready](PRD-23b-screener-mode-ui.md) | TBD | ~1.5 wk | 23a; PRD-22c widgets (soft) | 23c (soft) |
| **PRD-23c** | Discover → track + intraday | ✅ [Ready](PRD-23c-screener-track-intraday.md) | TBD | ~1 wk | 23a + 23b; PRD-19/16c | — |

### Dependency graph

```
┌──────────────────────────────┐
│ shipped foundation           │
│ PRD-16a/b (catalog+composer) │
│ PRD-22a (output_kind)        │
│ PRD-22c slice a (operators)  │  ← #207, the evaluator the scan/rank reuse
│ PRD-19/16c (cron+dashboard)  │
│ SP500_TICKERS + price_bars   │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ PRD-23a — backend spine      │
│ resolver · snapshot · scan   │
│ · count · rank               │
│ DoD = working live demo      │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐      ┌──────────────────────────────┐
│ PRD-23b — mode + UI          │ ───► │ PRD-23c — discover → track   │
│ flow · selector · composer   │      │ basket→SavedStrategy→notify  │
│ · live count · results       │      │ + intraday snapshot          │
└──────────────────────────────┘      └──────────────────────────────┘
```

### Recommended execution

**Sequential, single owner (~4 weeks):** 23a → 23b → 23c. 23a is the spine; prove the loop end-to-end on live data before building the UI on top. 23b's polished composer wants PRD-22c's kind-widgets (the reading layer) — sequence 22c's remaining slices before 23b, or ship 23b VALUE-only and light it up when 22c lands.

**The strict order:** 23b/23c cannot scan without 23a's snapshot + scan endpoint. 23c cannot track a discovered basket without 23b's save handoff.

---

## 5. Shared infra inventory (living document)

Each PRD updates this section at PR close. ♻️ = reused, 🆕 = new.

### Reused bricks (Principle 1)

| Brick | Source |
|---|---|
| Flow runtime + `/flow` shell + `startFlow` | `apps/web/src/lib/flows/` (PRD-13a) |
| Composer canvas + rule cards + AND/OR fold | PRD-16b (`logic_with_prior`) |
| Catalog + primitives + `output_kind` | PRD-16a / 22a (frozen at ~72) |
| Rule evaluator (`_apply_rule_threshold` operators) | PRD-22c slice a (#207) |
| `BacktestEngine.run()` + `StrategyJSON` | `backtester/engine.py` |
| KB `match-templates` (recommended defaults) | PRD-16a-3 |
| Active-execution cron + dashboard + notifications | PRD-16c-3/6, PRD-19 |
| `SavedStrategy` / `BacktestRecord` model | PRD-16b / PRD-19 |
| Universe standard (`SP500_TICKERS`, sector baskets) | `data/sp500_tickers.py` |
| Cached daily `price_bars` + `PriceDataService` | existing |
| Staged backtest-loading UI | PRD-I |

### New bricks

| Brick | Owner PRD | Status |
|---|---|---|
| `universe_resolver` (`universe_id → [symbol]`) + tier gate + `is_standing_universe` switch | PRD-23a | ✅ slice 1 |
| `signal_snapshot` table + daily warm cron (gated `SCREENER_SNAPSHOT_ENABLED`) + `SignalSnapshotService` | PRD-23a | ✅ slice 2 |
| `scan_service` (rule → matched basket + readings over snapshot) | PRD-23a | ✅ slice 3 |
| `POST /api/screen/scan` + `POST /api/screen/count` | PRD-23a | ✅ slice 4 |
| `rank_service` (backtest matched subset, `(symbol, rule_hash, as_of_date)` cache) + `POST /api/screen/rank` | PRD-23a | ✅ slice 5 |
| `custom_build_mode` *extension* — universe selector (incl. entered-symbols tier) + scan/results path (NOT a new FlowDefinition) | PRD-23b | ⏳ |
| `<UniverseSelector>` / `<ReadingComposer>` / `<ScreenResults>` | PRD-23b | ⏳ |
| Intent / reading layer (`reading` + `intent_group` catalog fields) | PRD-22c (folded in) | ⏳ |
| Discover → track (basket → SavedStrategy → notify on new entrants) | PRD-23c | ⏳ |
| Intraday snapshot (`resolution='intraday'`) | PRD-23c | ⏳ |

⏳ = not yet built.

---

## 6. Common pitfalls (read before your first commit)

### A. The scan must read the snapshot, never recompute per request
The whole sub-300ms promise rests on pre-warming the **primitive layer** (`~72 × ~500 ≈ 36k` values/day), not the rule space (infinite). At scan time, a composed rule is a boolean filter over the in-memory snapshot. If you find yourself computing a primitive series per scan, you've lost the architecture.

### B. Rank only the matched subset — never the universe
The rule screens 500 → ~18 *before* anything expensive runs. Backtest the ~18 (cap to top-K, pre-order by a cheap proxy), cache `(symbol, rule_hash, as_of_date)`. Backtesting the whole universe is a design error.

### C. No fabricated snapshot values (repo rule)
A symbol with no bars / a primitive that raises → a **null** cell, excluded from rules referencing it. Never a placeholder. The warm job logs failures with `logger.exception` (trap #20).

### D. Warm cron must not block the event loop or share asyncio primitives
The daily snapshot warm runs off the request path via the `_run_async_in_thread` bridge (trap #21) and must not touch singletons holding shared `asyncio.Lock`/`Semaphore` (trap #22). `apps/api/CLAUDE.md` #21/#22.

### E. Postgres-safe DDL for `signal_snapshot`
`CREATE TABLE IF NOT EXISTS` in the shared block; `user`-scoped columns (if any) use `String(36)` with no FK to `users` (apps/api/CLAUDE.md #1/#3). Log the row count (#10) — ~36k rows is small, but the discipline stands.

### F. Universe is a STANDARD, expand-only
The resolver reads `SP500_TICKERS`; a test asserts universe size ≥ a floor. Never quietly shrink it (product invariant).

### G. The reading layer is editorial — Jimmy's gate
The `reading` + `intent_group` catalog fields (folded into PRD-22c) are the trader-facing vocabulary. Author them in the established voice; PR review is the editorial gate (same as the catalog descriptions).

### H. Python 3.9 compat + types-first
`Optional[X]`, not `X | None` (CI is 3.9). Define `contracts.ts` types before the UI (the types-first rule).

### I. 23a's DoD is a working live demo
"Ensure the flow actually works" (Mr Gu's bar) — 23a is done when a composed reading scans the real S&P 500 snapshot and returns a real ranked basket, not when the unit tests pass.

---

## 7. Retention metrics to watch

1. **Scan → save conversion** — % of scans where the user saves the screen to track. The core funnel.
2. **Basket drill-in rate** — % of ranked results the user clicks into (backtest detail). Tells us if the ranking is trusted.
3. **New-entrant notification engagement** — for saved screens, % of "new name entered your basket" alerts the user acts on (reuse PRD-19's dispatched↔executed join).

---

## 8. Relationship to the design conversation

There is no separate design HTML for this mode — the design source is the 2026-06-16 conversation that produced this packet. The single comprehensive draft (`PRD-23-market-screener-mode.md`, PR #206) is **superseded by this HANDOFF + the three slice PRDs**. The screener is the productized form of the parked "multi-asset filter → rank → top-K composer" item in `docs/PROJECT_BACKLOG.md` §4.

---

## 9. When in doubt

- **Architecture question** → §2 (four principles) + the relevant PRD's "Design constraints" block.
- **Reuse or new?** → §5 brick inventory.
- **Snapshot value encoding per kind?** → PRD-23a §3.3.
- **Branch / PR procedure** → `CLAUDE.md` (auto-loaded).
- **Anything else** → escalate to Jimmy.

---

## 10. Final pre-flight checklist

Before your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] You've read `HANDOFF-livermore-custom-mode.md` (parent) + skimmed `engine.py:_apply_rule_threshold`.
- [ ] `CLAUDE.md` + `apps/api/CLAUDE.md` + `apps/web/AGENTS.md` loaded.
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md`.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] Your PRD's prerequisites are on `main` (23a needs PRD-22c slice a #207 + PRD-16a/b; 23b/c need 23a).

---

*Packet plan drafted 2026-06-16. Supersedes the single-doc draft `PRD-23-market-screener-mode.md` (PR #206). Cross-references: `HANDOFF-livermore-custom-mode.md` (parent), the catalog-v2 packet (PRD-22a/b/c), the flow runtime (PRD-13a, `apps/web/AGENTS.md`), the active-execution/notifications stack (PRD-16c/19). This is a new mode under the Mode = FlowDefinition principle — it adds no bespoke route.*
