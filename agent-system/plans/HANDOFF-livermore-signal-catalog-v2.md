# HANDOFF: Livermore Signal Catalog v2 — Industry-Standard Semantics + Missing Primitives

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first.** It is the entry point for the three-PRD packet that upgrades the shipped PRD-16a signal catalog into v2 — adding output-kind semantics, decomposing single-channel primitives into their full event/cross/divergence families, and shipping ~65 net-new primitives that the current catalog can't express. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: 4–6 weeks for the full packet (PRD-22a → PRD-22b → PRD-22c), single owner sequential.
**Total scope**: 3 PRDs — **PRD-22a (semantics + schema)**, **PRD-22b (catalog v2 content)**, **PRD-22c (composer kind-dispatch)**.
**Sprint goal**: Take Custom Mode from "55 primitives that all emit a scalar" to "120 primitives across seven semantic kinds (VALUE / EVENT / REGIME / LEVEL / DISTANCE / CROSS / DIVERGENCE), with rule-builder widgets specialized to each kind."

---

## 1. TL;DR

PRD-16a shipped a working signal catalog (~55 primitives, 8 categories, parameterized, evidence-tiered). But the catalog has two structural issues — the v2 spec at [`/Quant Strategy/framework/signal_catalog_v2_spec.html`](../../Quant%20Strategy/framework/signal_catalog_v2_spec.html) is the design source.

**Bug 1 — Semantic flatness.** Every v1 primitive emits a scalar, and the composer renders one rule shape: "[primitive] [< | >] [threshold]." That's correct for `RSI < 30` and `ADX > 25`, but wrong for the industry-canonical consumption of MACD (signal-line crossover), Stochastic (%K vs %D cross), Bollinger (squeeze fire), ADX (DI+ vs DI- cross), MA family (golden/death cross), and every RSI/MACD/OBV divergence pattern. PRD-22 introduces `output_kind` and the composer dispatches to a kind-specific rule-builder.

**Bug 2 — Missing computations.** Six common idioms can't be expressed: distance-to-extremum ("within 2-25% of 52-week high"), TTM Squeeze (Bollinger ∩ Keltner), Anchored VWAP, ATR-trailing stops (Chandelier / Supertrend), Heikin-Ashi candle direction, 12-1 momentum z-score (academic / MSCI standard), PEAD drift window. PRD-22 adds ~65 new primitives across 11 families.

The packet:

- **PRD-22a (~1 week)**: schema fields (`output_kind`, `output_channels`, `composes`) + v1 backfill. Zero behavior change — proves identical backtests on all existing strategies.
- **PRD-22b (~3 weeks)**: 11 family upgrades + 65 new primitive `SignalProvider` impls + editorial catalog content + KB-lookup enrichment.
- **PRD-22c (~1.5 weeks)**: composer rule-builder dispatch on `output_kind`; new widgets for EVENT, LEVEL, CROSS, REGIME, DISTANCE, DIVERGENCE.

---

## 2. The four design principles (load-bearing)

Same four principles as every PRD packet in this repo. Stated identically across the v2 product flow HANDOFF, the notification HANDOFF, the Custom Mode HANDOFF, and this HANDOFF — moving between packets shouldn't cost a context switch.

### Principle 1 — Reuse, don't replicate

This packet must NOT add: a new `SignalPrimitive` schema (extend it with three additive fields), a new catalog file (extend `apps/api/app/data/signal_primitives.py`), a new endpoint surface (extend `GET /api/signal-primitives` to return the new fields), a new composer canvas (extend the existing `<RuleBuilder>` to dispatch on `output_kind`).

What this packet DOES add: three additive schema fields, ~40 net-new `SignalProvider` impls, ~65 new catalog entries (each with hand-authored description), six kind-specific rule-builder widgets in the composer, an enriched Jaccard similarity in the KB-lookup endpoint.

### Principle 2 — LEGO bricks

PRD-22a ships schema bricks PRD-22b and PRD-22c consume. PRD-22b ships catalog content + provider impls PRD-22c consumes. The brick inventory in §5 is the canonical list.

### Principle 3 — Mode = `FlowDefinition`, not a route

This packet does NOT introduce a new mode. `custom_build_mode` continues to be the only consumer of the signal catalog. PRD-22c's composer changes are widget-level — the FlowDefinition itself is unchanged.

### Principle 4 — UX consistency + sub-300ms perceived load

- The catalog payload grows from ~55 entries to ~120. Stay aggressive on the localStorage cache that PRD-16a shipped — same ETag revalidation pattern, just a bigger payload (~120 KB JSON vs ~55 KB).
- Kind-specific rule widgets share a common shell: same border-radius, same hover state, same focus ring. Only the inner inputs differ.
- KB-lookup endpoint stays sub-200ms even with the enriched Jaccard — cache the match-template results by `frozenset(primitive_ids)` for 1 hour.

---

## 3. Reading order (for a coding agent fresh to this work)

1. **`CLAUDE.md`** (repo root) — auto-loaded. Branch / PR / Python-3.9-compat conventions.
2. **`agent-system/PARALLEL_WORK.md`** — claim a row in the Active Sessions table.
3. **`agent-system/plans/HANDOFF-livermore-custom-mode.md`** — the parent HANDOFF for the Custom Mode work this packet builds on.
4. **`/Quant Strategy/framework/signal_catalog_v2_spec.html`** — the design source. Read §2 (semantics layer), §3 (per-family audit), §4 (computation reference for new primitives). This is the canonical spec for what to build.
5. **This file** — the three-PRD packet plan.
6. **`apps/api/app/data/signal_primitives.py`** — the shipped v1 catalog (1,232 LOC). Skim it to understand the existing entry shape before you upgrade it.
7. **`apps/api/app/schemas/signal_primitive.py`** — the shipped schema. PRD-22a extends this.
8. **Your assigned PRD** — `PRD-22a-signal-catalog-v2-semantics.md`, `PRD-22b-signal-catalog-v2-content.md`, or `PRD-22c-composer-kind-dispatch.md`.

If your PRD is 22b, also `git log apps/api/app/data/signal_primitives.py` to see the editorial conventions PRD-16a established — descriptions are hand-authored 1-line plain English, not LLM-generated. Match that voice.

---

## 4. The three PRDs

| PRD | Title | Status | Owner | Effort | Depends on | Blocks |
|-----|-------|--------|-------|--------|------------|--------|
| **PRD-22a** | Semantics layer + schema fields (output_kind / output_channels / composes) | ✅ [Ready](PRD-22a-signal-catalog-v2-semantics.md) | TBD | ~1 week | PRD-16a (shipped) | PRD-22b, PRD-22c |
| **PRD-22b** | Catalog v2 content — 11 family upgrades + 65 new primitives + provider impls | ✅ [Ready](PRD-22b-signal-catalog-v2-content.md) | TBD | ~3 weeks | PRD-22a | PRD-22c (soft) |
| **PRD-22c** | Composer rule-builder kind-dispatch + 6 new widgets | ✅ [Ready](PRD-22c-composer-kind-dispatch.md) | TBD | ~1.5 weeks | PRD-22a (hard), PRD-22b (soft) | — |

### Dependency graph

```
┌─────────────────────┐
│  PRD-16a shipped    │
│  Catalog v1 (55)    │
│  + signal schema    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────┐
│  PRD-22a                        │
│  Semantics layer (3 fields)     │
│  Backfill v1 catalog            │
│  Zero behavior change (~1 wk)   │
└────────┬────────────────────────┘
         │
         ├──────────────────────────────┐
         │                              │
         ▼                              ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  PRD-22b                 │   │  PRD-22c                 │
│  Catalog v2 content      │   │  Composer kind-dispatch  │
│  +65 primitives          │   │  +6 rule-builder widgets │
│  +40 SignalProvider impls│   │  Renders for v1 already  │
│  KB-lookup enrich (~3 wk)│   │  (~1.5 wk)               │
└──────────────────────────┘   └──────────────────────────┘
            │                              │
            └──────────────┬───────────────┘
                           │
                           ▼
                    Soft coupling: PRD-22c can
                    ship with v1-only catalog
                    rendering correctly. New
                    primitives from 22b light up
                    once both are on main.
```

### Recommended execution

**Sequential, single owner (~5.5 weeks):**
- **Week 1**: PRD-22a. Schema fields + v1 backfill + pytest proves no regression.
- **Weeks 2–4**: PRD-22b. The biggest PRD by far — 40 provider impls + 65 editorial entries + KB-lookup enrichment.
- **Weeks 5–6.5**: PRD-22c. Composer widgets. Can begin as soon as PRD-22a merges; doesn't strictly block on PRD-22b.

**Parallel-aggressive (two owners, ~4 weeks):**
- Owner A: PRD-22a → PRD-22b. The catalog-content path. Heavier load.
- Owner B: PRD-22c (starts after PRD-22a on main). The frontend path.
- Crossover at week 3 when both paths converge for end-to-end testing.

**The strict order**: PRD-22b's new primitives cannot ship before PRD-22a's schema fields exist (or the new primitives have no `output_kind` to declare). PRD-22c's kind-specific widgets are useful only when there are primitives with the relevant `output_kind` — so 22c shipping with only v1 primitives in production gives a degraded but non-broken experience.

---

## 5. Shared infra inventory (living document)

Bricks created across the packet. Each PRD updates this section at PR close.

### Backend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `OutputKind` enum (7 values) | PRD-22a | ✅ | All v2 consumers |
| `SignalPrimitive.output_kind` field | PRD-22a | ✅ | Catalog endpoint; composer dispatch; KB-lookup Jaccard |
| `SignalPrimitive.output_channels` field | PRD-22a | ✅ | Multi-channel primitives (MACD, BB, ADX, Stoch) |
| `SignalPrimitive.composes` field | PRD-22a | ✅ | Derived primitives (signal_cross, divergence, etc.) |
| v1 catalog backfill (~55 entries) | PRD-22a | ✅ | Backward compat; all consumers |
| 11 family upgrade primitives (~30 entries) | PRD-22b | ⏳ | Composer (when kind-dispatch ready) |
| 52-week extrema family (7 primitives) | PRD-22b | ✅ | Distance/breakout/zone rule consumers |
| TTM Squeeze + Supertrend + Chandelier (8 primitives) | PRD-22b | ⏳ | Volatility consumers; multi-tier exits |
| RVOL + Anchored VWAP family (5 primitives) | PRD-22b | ⏳ | Volume consumers |
| 12-1 Momentum + z-score family (4 primitives) | PRD-22b | ⏳ | Cross-sectional momentum strategies |
| PEAD signal + drift window family (6 primitives) | PRD-22b | ⏳ | Event-driven consumers |
| Heikin-Ashi family (3 primitives) | PRD-22b | ⏳ | Trend / smoothing consumers |
| ~40 net-new `SignalProvider` impls | PRD-22b | ⏳ | Backtest engine; intraday monitor (via PRD-16c) |
| KB-lookup enrichment (Jaccard on `output_kind`) | PRD-22b | ⏳ | `POST /api/signal-combos/match-templates` |
| `output_kind`-keyed template recommendation index | PRD-22b | ⏳ | KB-lookup; future template browsing |

### Frontend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `<RuleBuilder>` kind-dispatcher | PRD-22c | ⏳ | Composer canvas |
| `<ValueRule>` (existing shape, refactored) | PRD-22c | ⏳ | VALUE primitives |
| `<EventRule>` | PRD-22c | ⏳ | EVENT primitives (no threshold input) |
| `<LevelRule>` | PRD-22c | ⏳ | LEVEL primitives (persistent boolean) |
| `<CrossRule>` | PRD-22c | ⏳ | CROSS primitives (direction picker) |
| `<RegimeRule>` | PRD-22c | ⏳ | REGIME primitives (single-select chip) |
| `<DistanceRule>` | PRD-22c | ⏳ | DISTANCE primitives (range slider, signed) |
| `<DivergenceRule>` | PRD-22c | ⏳ | DIVERGENCE primitives (lookback + bull/bear picker) |
| Catalog browser filter on `output_kind` | PRD-22c | ⏳ | `<SignalCatalogBrowser>` (PRD-16a) |
| Recommended-defaults panel updates | PRD-22c | ⏳ | `<RecommendedDefaultsPanel>` (PRD-16b) |

⏳ = not yet built.

---

## 6. Common pitfalls (read before your first commit)

### A. Slice A must be a no-op at the backtest level

PRD-22a adds schema fields. It does NOT change any primitive's behavior. **Run `pytest -q` on the full backtest suite and assert every test produces byte-identical output to `main`.** If any backtest changes, the additive-change contract was violated and the PR should not merge.

### B. v1 primitives need `output_kind` backfill — most are VALUE, but a few aren't

`adx` has a threshold semantics (above 25 = trending) that v1 used as a level. `ma_crossover` is genuinely a CROSS. `donchian_breakout` is an EVENT. Don't lazy-default all 55 to VALUE; review each in the v2 spec §3 before backfilling. The audit is already done — the v2 spec has every v1 primitive's correct kind. Use it as ground truth.

### C. The catalog is the editorial product — PRD-22b has a real writing budget

65 new primitives × ~1 hour editorial = ~8 working days of writing on top of the engineering. **Do not LLM-generate descriptions.** The PRD-16a HANDOFF §6 pitfall stated this clearly; it applies double here. PR review is the editorial gate. If you're not the right person to write them, escalate to Jimmy.

### D. The composer can ship before all the new primitives

PRD-22c can render kind-specific widgets correctly even if only v1 primitives are in production. A widget that renders for `output_kind=EVENT` is harmless when zero EVENT primitives exist — it just doesn't activate. This decouples 22b and 22c at release time.

### E. New primitives need intraday flagging at PRD-16c boundary

PRD-16c (already shipped) ships intraday-compatible primitives via the `resolution` field. PRD-22b's new primitives must all ship with `resolution=["daily"]` initially. A follow-up PR can flip eligible ones to `["daily", "intraday"]` — but that PR is out of scope for PRD-22, and likely lives in the intraday-extensions queue.

### F. `output_channels` is for multi-output primitives — keep the channel names stable

MACD shipping with `output_channels=["macd_line", "signal_line", "histogram"]` becomes a public contract. Saved strategies in production will reference these channel names. **Never rename a channel after it ships.** Add new ones if needed; deprecate by hiding from the UI but keep them backtest-resolvable.

### G. KB-lookup enrichment must stay sub-200ms

The Jaccard similarity now operates on `(category, output_kind)` tuples instead of just `category`. The set size grows from 8 (categories) to 56 (8 × 7). For ~30 templates × ~10 primitives each, the comparison is still cheap — but cache the result keyed by `frozenset(primitive_ids)` for at least 1 hour. The KB content rarely changes; users compose-and-recompose constantly.

### H. Python 3.9 compat (the usual)

`Optional[X]` not `X | None`. Grep your diff. CI runs on 3.9.

### I. Static-import smoke test after PRD-22b

PRD-22b adds ~40 new provider impl files. After your commit, run:
```bash
cd apps/api && python3 -c "from app.main import app; print(f'{len(app.routes)} routes')"
```
to confirm every new import resolves. The `notifications.py`-missed-`git-add` bug from 2026-06-08 is in scope here too — 40 new files is 40 chances to forget one.

### J. Don't run `git add -A`

Explicit pathspecs only. PRD-22b will touch ~80 files (impls + tests + catalog data); one stray uncommitted file or one accidentally-included unrelated file ruins the diff.

### K. Data-source coverage was audited late — read PRD-22b §9 before promising primitives

A 2026-06-12 feasibility check (post-spec) flagged that ~58/65 v2 primitives are computable from data we already fetch (just price + volume + indicators), but a handful need new AV endpoint wiring or proxy approximations. PRD-22b §9 has the full per-primitive coverage map. The two real constraints:

1. **PEAD `pead_signal`** approximates SUE as `surprise_pct / trailing_8q_std(surprise_pct)` because AV's `EARNINGS` endpoint doesn't expose analyst-estimate std-err. Not academically rigorous; document the proxy in catalog `long_description`.
2. **`insider_net_buy_surge`** depends on AV `INSIDER_TRANSACTIONS` (premium-tier). Ship behind feature flag `AV_INSIDER_TXN_ENABLED`; catalog entry filtered out when flag is off. Avoids serving a primitive that 500s.

Three new AV client methods are required (`fetch_earnings_history`, `fetch_earnings_calendar`, `fetch_insider_transactions`) — `fetch_technical_indicator` already covers everything else. Rate-limit budget impact is <0.5% even at 1k-symbol universe.

---

## 7. Retention metrics to watch (different from PRD-16's metrics)

PRD-16's metric set tracked composer-completion and active-execution retention. PRD-22 changes what's possible to compose, so two new metrics are worth instrumenting:

1. **Kind-specific rule adoption** — % of saved strategies after PRD-22 ships that use at least one non-VALUE rule (EVENT, CROSS, REGIME, etc.). Tells us if the semantic upgrade is actually being consumed or if users default to threshold rules out of habit.
2. **52-week-extrema family use rate** — % of saved strategies using a primitive from this family. Tells us if the gap users flagged is now closed.

A third metric worth watching but not new — KB-lookup precision (% of recommended templates the user accepted). The enriched Jaccard should make this metric move up; if it stays flat or drops, the enrichment didn't help.

---

## 8. Relationship to the v2 spec HTML

The HTML at `/Quant Strategy/framework/signal_catalog_v2_spec.html` is the DESIGN source. This packet is the OPERATIONALIZATION.

- v2 spec §2 (semantics layer) → PRD-22a (schema fields)
- v2 spec §3 (per-family audit) → PRD-22b (catalog content) — every recommended primitive maps to a catalog entry
- v2 spec §4 (computation reference) → PRD-22b (provider impl) — every formula maps to a `SignalProvider` impl
- v2 spec §5 (schema implications) → PRD-22a (the additive fields)
- v2 spec §6 (summary table) → PRD-22b (definition-of-done count)
- v2 spec §7 (migration plan slices A/B/C) → PRD-22a/b/c respectively
- v2 spec §8 (sources) → reference material for PRD authors

**If a question arises that the PRD doesn't answer, the v2 spec almost certainly does.** It is more design-rich than the PRDs; the PRDs are scoped to "what to build and how to verify it shipped."

---

## 9. When in doubt

- **Architecture question** → check §2 (four principles) and the relevant PRD's "Design Constraints" block.
- **What kind should this primitive emit?** → check v2 spec §2 and §3.
- **What's the formula?** → check v2 spec §4.
- **Brick already exists?** → check §5 of this doc + §5 of `HANDOFF-livermore-custom-mode.md`.
- **Branch / PR procedure** → `CLAUDE.md` (auto-loaded).
- **Anything else** → escalate to Jimmy.

---

## 10. Final pre-flight checklist

Before you write your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] You've read `/Quant Strategy/framework/signal_catalog_v2_spec.html` §2-5 (the design source).
- [ ] You've read `agent-system/plans/HANDOFF-livermore-custom-mode.md` (parent HANDOFF).
- [ ] `CLAUDE.md` auto-loaded (Claude Code) or you've read it manually (other agents).
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md` Active Sessions.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] You've confirmed your PRD's prerequisites are on `main` (22b/22c need 22a; 22a needs PRD-16a which is shipped).
- [ ] You've skimmed `apps/api/app/data/signal_primitives.py` to understand the existing entry shape.
- [ ] You've checked PARALLEL_WORK.md for anyone else mid-build on PRD-22.

If all nine are checked, start. If any are unchecked, fix that first.

---

*Sprint plan drafted 2026-06-12. Design source: [`/Quant Strategy/framework/signal_catalog_v2_spec.html`](../../Quant%20Strategy/framework/signal_catalog_v2_spec.html). Cross-references: `HANDOFF-livermore-custom-mode.md` (parent), PRD-16a/b/c (shipped foundation). Updates to this handoff doc require updating PRD-22a/b/c's "Reading order" section to stay in sync.*
