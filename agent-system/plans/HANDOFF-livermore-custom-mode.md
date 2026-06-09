# HANDOFF: Livermore Custom Mode — Signal Library + Composer + Active Execution

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first.** It is the entry point for the three-PRD packet that builds Livermore's Custom Mode (Mode 4) into the "compose signals → backtest → run live" loop. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: 5–7 weeks for the full packet (PRD-16a → PRD-16b → PRD-16c), single owner sequential.
**Total scope**: 3 PRDs — **PRD-16a (signal library)**, **PRD-16b (composer UI)**, **PRD-16c (intraday + active execution)**.
**Sprint goal**: Take Custom Mode from "fork a template and tweak risk" to "compose any combination of ~55 signal primitives, backtest it on daily or intraday bars, and optionally run it live with multi-tier exits and a live dashboard."

---

## 1. TL;DR

The v2 product flow HANDOFF previewed a single PRD-16 ("Custom Build — signal composer UI; ~1 week"). The user's 2026-06-08 vision expanded that into a three-PRD packet:

- **PRD-16a (~2 weeks)**: signal primitive library — wires ~40 Alpha Vantage technical indicators + existing template signals into a categorized catalog of ~55 primitives. Plus a KB lookup that takes a user's signal combo and recommends entry/exit thresholds from matching templates.
- **PRD-16b (~2 weeks)**: composer UI — drag-and-combine canvas that consumes PRD-16a's catalog. Adds `logic_with_prior` schema field and engine multi-rule fold for AND/OR composition. Registered as a `FlowDefinition` via PRD-13a's runtime.
- **PRD-16c (~3 weeks)**: intraday + active execution — adds intraday data support (5/15/30/60-min bars), multi-tier exit ladder (stop + partial TP + full TP), per-position state tracking, intraday monitor cron, and a live dashboard. Consumes PRD-19's notification infrastructure for position-event alerts.

PRD-16c depends on PRD-19 (notifications Phase B re-shape) being on `main`. PRD-16a is independent of PRD-19. PRD-16b consumes PRD-16a + PRD-13a (flow runtime).

---

## 2. The four design principles (load-bearing)

Same four principles as every PRD packet in this repo. They are stated identically across the v2 product flow HANDOFF, the notification HANDOFF, and this HANDOFF — moving between packets shouldn't cost a context switch.

### Principle 1 — Reuse, don't replicate

This packet must NOT add: a new BacktestEngine (extend it with a `bar_resolution` parameter), a new save format (existing StrategyJSON), a new notification dispatcher (PRD-19's lands first), a new SignalProvider abstraction (already exists), a new wizard (StrategyBuilderModal is the orchestrator). 

What this packet DOES add: ~40 new SignalProvider impls (extending the protocol), a categorized catalog (new content + new endpoint), a composer UI (new component), schema fields (additive), an intraday data service, multi-tier exit schema, a live dashboard.

The genuinely novel work is well-bounded. Most of the volume is *content* (catalog metadata) and *plumbing* (composer wiring) — not new infrastructure.

### Principle 2 — LEGO bricks

Each PRD ships bricks the others consume. PRD-16c specifically depends on bricks from PRD-16a AND PRD-16b. The brick inventory in §5 below is the canonical list — read it before writing new code.

### Principle 3 — Mode = `FlowDefinition`, not a route

PRD-16b registers Custom Build as a 5-step `FlowDefinition` (`custom_build_mode.ts`) via PRD-13a's runtime. PRD-16c's "Active execution" is NOT a new mode — it's a toggle inside the same `custom_build_mode` flow. The live dashboard is a content surface on the strategy detail page, not a flow.

### Principle 4 — UX consistency + sub-300ms perceived load

- **Centralized labels** via `useFlowCopy('signal_library', key)` (PRD-16a), `useFlowCopy('custom_build', key)` (PRD-16b), `useFlowCopy('active_exec', key)` (PRD-16c). Three distinct mode_ids; framework labels (Backtest, Save, etc.) inherit from the existing `FRAMEWORK_COPY`.
- **Aggressive catalog caching** — PRD-16a's catalog rarely changes; localStorage with version stamp + ETag revalidation.
- **Skeleton everywhere** for blocking calls > 200ms.
- **Optimistic UI** on signal-card drag (16b) and exit-ladder edits (16c).
- **Live dashboard polling** — 30s minimum; never sub-30s in v1.

---

## 3. Reading order (for a coding agent fresh to this work)

1. **`CLAUDE.md`** (repo root) — auto-loaded. Branch / PR / Python-3.9-compat conventions.
2. **`agent-system/PARALLEL_WORK.md`** — claim a row in the Active Sessions table.
3. **`agent-system/plans/HANDOFF-livermore-product-flow-v2.md`** — the parent HANDOFF. Sections 2 (principles) and 6 (brick inventory) apply here too.
4. **`agent-system/plans/HANDOFF-livermore-notifications.md`** — if you're assigned PRD-16c, read this — your work plugs into PRD-19's dispatcher + throttle.
5. **This file** — the three-PRD packet plan.
6. **`/Quant Strategy/framework/livermore_product_flow_v2.html`** §2 Mode 4 — the design vision.
7. **`/Quant Strategy/framework/Livermore_Strategy_Library_v2.html`** §3 — the existing template signal catalog (PRD-16a draws from this).
8. **Your assigned PRD** — `agent-system/plans/PRD-16a-signal-library-catalog.md`, `PRD-16b-custom-build-composer.md`, or `PRD-16c-intraday-active-execution.md`.

If your PRD is 16c, also `git show` PR #88, #101, #107 to understand what PRD-19 fixed about Phase B notifications — same dispatcher patterns apply to your new position-event triggers.

---

## 4. The three PRDs

| PRD | Title | Status | Owner | Effort | Depends on | Blocks |
|-----|-------|--------|-------|--------|------------|--------|
| **PRD-16a** | Signal primitive library + categorized catalog + KB lookup | ✅ [Ready](PRD-16a-signal-library-catalog.md) | TBD | ~2 weeks | None hard (soft: Module 2/PR #97) | PRD-16b, PRD-16c |
| **PRD-16b** | Custom Build composer UI + schema/engine multi-rule fold | ✅ [Ready](PRD-16b-custom-build-composer.md) | TBD | ~2 weeks | PRD-16a, PRD-13a | PRD-16c |
| **PRD-16c** | Intraday data + multi-tier exits + live monitoring + dashboard | ✅ [Ready](PRD-16c-intraday-active-execution.md) | TBD | ~3 weeks | PRD-19, PRD-16a, PRD-16b | — |

### Dependency graph

```
                                              ┌────────────────────┐
                                              │  PRD-19            │
                                              │  Notifications     │
                                              │  Phase B re-shape  │
                                              │  (separate packet) │
                                              └─────────┬──────────┘
                                                        │
┌────────────────────┐                                  │
│  PRD-13a           │                                  │
│  Flow runtime      │                                  │
│  (already on main) │                                  │
└────────┬───────────┘                                  │
         │                                              │
         │   ┌──────────────────────────────┐           │
         │   │  PRD-16a                     │           │
         │   │  Signal catalog + KB lookup  │           │
         │   │  (~2 wk; no PRD-19 dep)      │           │
         │   └────────┬─────────────────────┘           │
         │            │                                 │
         │            ▼                                 │
         │   ┌──────────────────────────────┐           │
         └──▶│  PRD-16b                     │           │
             │  Composer UI + multi-rule    │           │
             │  fold (~2 wk)                │           │
             └────────┬─────────────────────┘           │
                      │                                 │
                      ▼                                 ▼
             ┌────────────────────────────────────────────┐
             │  PRD-16c                                   │
             │  Intraday + multi-tier exits +             │
             │  live monitoring + dashboard (~3 wk)       │
             └────────────────────────────────────────────┘
```

### Recommended execution

**Sequential, single owner:**
- **Weeks 1–2**: PRD-16a. Starts the day PRD-19 enters review (zero touchpoints; can run in parallel with PRD-19's tail end).
- **Weeks 3–4**: PRD-16b. Waits for PRD-16a on main.
- **Weeks 5–7**: PRD-16c. Waits for PRD-19 + PRD-16a + PRD-16b all on main.

**Parallel-aggressive (two owners):**
- Owner A: PRD-19 → PRD-16c (the notification + active-execution path).
- Owner B: PRD-16a → PRD-16b (the catalog + composer path).
- Crossover at weeks 5–6 when both paths converge into PRD-16c.

**The strict order**: PRD-16c cannot start before PRD-19 + PRD-16a + PRD-16b are all merged. If any is missing, PRD-16c stalls on stubs that get refactored later — worse than waiting.

---

## 5. Shared infra inventory (living document)

Bricks created across the packet. Each PRD updates this section at PR close. **Read this before writing new code — if the brick exists, reuse it.**

### Backend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `SignalCategory` enum (8 categories) | PRD-16a | ⏳ | All consumers |
| `SignalPrimitive` Pydantic model | PRD-16a | ⏳ | Catalog endpoint + composer + intraday extension |
| `SIGNAL_PRIMITIVES` catalog data (~55 entries) | PRD-16a | ⏳ | PRD-16b composer; PRD-16c extends with intraday-resolution flags |
| ~40 new `SignalProvider` concrete impls | PRD-16a | ⏳ | Composer at backtest; intraday monitor |
| `GET /api/signal-primitives` endpoint | PRD-16a | ⏳ | Catalog browser; future standalone library page |
| `GET /api/signal-primitives/{id}/preview` endpoint | PRD-16a | ⏳ | Preview chart |
| `POST /api/signal-combos/match-templates` (KB lookup) | PRD-16a | ⏳ | Recommended-defaults panel |
| Per-template `signal_thresholds` metadata | PRD-16a | ⏳ | KB lookup output |
| `StrategyRule.logic_with_prior` field | PRD-16b | ⏳ | All multi-rule strategies; PRD-16c respects same field |
| Engine multi-rule fold (`_evaluate_block`) | PRD-16b | ⏳ | All multi-rule strategies; PRD-16c reuses |
| `POST /api/strategies/draft` (optional) | PRD-16b | ⏳ | Composer cross-device draft sync |
| `IntradayBarService` | PRD-16c | ⏳ | Active execution; future curated-themes PRD; future paper-trading |
| `intraday_bars` cache table | PRD-16c | ⏳ | Intraday consumers |
| `BacktestEngine.run(bar_resolution=...)` extension | PRD-16c | ⏳ | Intraday backtests; future replay features |
| `ExitTier`, `RiskManagement.exit_ladder` schema | PRD-16c | ⏳ | Multi-tier exit consumers; reusable on any strategy_type |
| `PositionState` table | PRD-16c | ⏳ | Active-execution strategies; future paper-trading audit |
| `IntradayPositionMonitorJob` cron | PRD-16c | ⏳ | Active-execution monitoring; pattern reusable for other intraday triggers |
| 3 new email templates (stop/tp1/tp2) | PRD-16c | ⏳ | Position-event alerts |
| 3 new trigger types in `NotificationThrottle` | PRD-16c | ⏳ | Position-event throttling (per-position semantics) |
| 3 new dashboard endpoints | PRD-16c | ⏳ | Live dashboard |

### Frontend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `<SignalCatalogBrowser>` | PRD-16a | ⏳ | Composer canvas; standalone library page |
| `<SignalPrimitiveCard>` | PRD-16a | ⏳ | Catalog browser; composer canvas |
| `<SignalPreviewChart>` | PRD-16a | ⏳ | Catalog browser hover preview |
| `<TemplateMatchSuggestion>` | PRD-16a | ⏳ | Composer right rail |
| Catalog localStorage cache (`lib/signal-library/catalog-cache.ts`) | PRD-16a | ⏳ | All catalog consumers |
| `<CustomBuildCanvas>` | PRD-16b | ⏳ | Composer flow step |
| `<RuleCard>` | PRD-16b | ⏳ | Composer canvas |
| `<RuleComposer>` (AND/OR toggle) | PRD-16b | ⏳ | Composer; future PRD-15 thesis confirmation filters |
| `<RecommendedDefaultsPanel>` | PRD-16b | ⏳ | Composer right rail |
| `custom_build_mode` FlowDefinition | PRD-16b | ⏳ | Strategy Builders custom-build CTA |
| `<ExitLadderEditor>` | PRD-16c | ⏳ | Composer WHEN OUT block (when "Active execution" enabled) |
| `<BarResolutionPicker>` | PRD-16c | ⏳ | Composer; future intraday-backtest surface |
| `<UniverseWatchPanel>` | PRD-16c | ⏳ | Strategy detail (active view); future watchlist surfaces |
| `<PositionCardsGrid>` | PRD-16c | ⏳ | Strategy detail (active view); future portfolio dashboard |
| `<TradeLogTable>` | PRD-16c | ⏳ | Strategy detail; future "all my trades" surface |

⏳ = not yet built. Update to ✅ when the brick lands.

---

## 6. Common pitfalls (read before your first commit)

### A. The catalog metadata IS the editorial product

PRD-16a hand-authors ~55 primitive descriptions. Each is 1-line plain English ("Measures overbought (>70) and oversold (<30) extremes…") plus an optional 1-paragraph explainer. **An agent should NOT dump Wikipedia summaries or LLM-generated text into the catalog.** PR review is the editorial gate. Treat this like user-facing copy, because it is.

### B. PRD-16c assumes a "leave room" pattern in PRD-16b's WHEN OUT block

PRD-16b ships single stop + single TP (matching existing `RiskManagement.stop_loss_pct` + `take_profit_pct`). PRD-16c adds the multi-tier exit ladder. **PRD-16b should leave a visible toggle scaffold in the WHEN OUT block** (even if disabled and labeled "Active execution coming soon") so PRD-16c can wire it up without modifying PRD-16b's component. Document this in PRD-16b's frontend section.

### C. The schema field `logic_with_prior` must be additive

Existing 22 strategy_types must continue backtest-identical after PRD-16b ships. **Run the full pytest suite** after the schema + engine change. If any existing test produces different output, the additive-change contract was violated.

### D. Stacked PRs lose backend CI

`.github/workflows/backend-ci.yml` only fires on `pull_request.branches: [main]`. **Always rebase your PR onto current `main` and set `base=main` before opening.** Full discussion in `CLAUDE.md`. PRD-16a/b/c are three sequential PRs but each must be `base=main`, not stacked.

### E. `X | None` syntax

CI runs on Python 3.9. Use `Optional[X]` not `X | None`. Grep your diff before pushing.

### F. Intraday data costs are real, even without tier-gating

The user explicitly said "don't worry about tiering for now" — but PRD-16c's intraday data fetching still has API cost. The 5-min monitor cron on a 6-symbol universe = ~78 calls/day per active strategy. Multiply by N active users and the Alpha Vantage budget matters. **Build the meter even if you don't gate on it** — `PostHog.capture('intraday_api_call', { …cost_estimate })` is enough for v1 visibility. Hard caps land in a follow-up PRD if usage warrants.

### G. Active execution toggle visibility

PRD-16c's "Active execution" toggle could overwhelm a new user opening Custom Build for the first time. **Default state: collapsed under "Advanced" disclosure** in the WHEN OUT block. Power users find it; beginners don't accidentally enable intraday monitoring they don't understand.

### H. Don't run `git add -A`

Explicit pathspecs only. Parallel work + multiple PRDs in the same area = high collision risk.

### I. Coordinate the settings form extension across PRD-19, PRD-20, PRD-16c

`<NotificationSettingsForm>` is touched by PRD-19 (originally), PRD-20 (cadence prefs), AND PRD-16c (intraday alerts). **All three follow the same section-extension pattern** so merges are clean. Check the open PRs before pushing your settings-form changes.

---

## 7. Retention metrics to watch (different from PRD-19's metric)

PRD-19's metric was "time from notification sent → Mark-as-executed." For PRD-16, the loop is different. Three metrics worth instrumenting:

1. **Composer completion rate** — % of `composer_opened` events that result in `composer_backtest_run`. Tells us if the composer UX is converting "I want to build a custom strategy" into "I built one and backtested it."
2. **Custom strategy save rate** — % of `composer_backtest_run` events that result in `strategy_saved`. Tells us if backtest results are convincing enough to commit.
3. **Active execution retention** — % of saved active-execution strategies still in `is_open=true` PositionState rows 30 days after save. Tells us if the live dashboard + alerts loop is worth the intraday cost.

The third metric is the most strategic — it answers "is active execution a feature people use, or a feature people try once?"

---

## 8. Relationship to the v2 product flow HANDOFF

The v2 product flow HANDOFF (`HANDOFF-livermore-product-flow-v2.md`) §10 "Sprint 2 preview" lists:

> "**PRD-16**: Custom Build (Mode 4) — signal composer UI; closes the read-only WHEN IN / WHEN OUT gap; reuses 4-block summary step."

That single line is now this entire three-PRD packet. The user's 2026-06-08 vision expanded it dramatically. **If you're reading the v2 HANDOFF and see "PRD-16," understand that it has been re-scoped into PRD-16a + PRD-16b + PRD-16c.** This HANDOFF is the canonical source for Custom Mode work going forward.

The other Sprint 2 PRDs mentioned in the v2 HANDOFF — PRD-15 (Thesis), PRD-17 (Saved strategies), PRD-18 (Community thesis cards) — are still single PRDs as originally scoped. They are NOT in this packet.

---

## 9. When in doubt

- **Architecture question** → check §2 (four principles) and the relevant PRD's "Design Constraints" block.
- **Branch / PR procedure** → `CLAUDE.md` (auto-loaded).
- **Brick already exists?** → check §5 of this doc.
- **PRD-19's brick I should reuse?** → check `HANDOFF-livermore-notifications.md` §5.
- **Module already shipped?** → check `/Quant Strategy/framework/strategy_builder_audit.md`.
- **Anything else** → escalate to Jimmy.

---

## 10. Final pre-flight checklist

Before you write your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] `CLAUDE.md` auto-loaded (Claude Code) or you've read it manually (other agents).
- [ ] You've read the relevant section of `livermore_product_flow_v2.html` §2 Mode 4.
- [ ] If your PRD is 16c, you've read `HANDOFF-livermore-notifications.md` AND `git show 9eeb3a9` (PR #88).
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md` Active Sessions.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] You've confirmed your PRD's prerequisites are on `main` (PRD-16b needs 16a; PRD-16c needs 19 + 16a + 16b).
- [ ] You've checked whether anyone else is mid-build on PRD-19, PRD-20, or any of the other PRD-16 sub-PRDs — if yes, coordinate via PARALLEL_WORK.md before pushing.

If all eight are checked, start. If any are unchecked, fix that first.

---

*Sprint plan drafted 2026-06-08. Cross-references: source design at `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 4, SpaceX reference from chat 2026-06-08. Updates to this handoff doc require updating PRD-16a/b/c's "Reading order" section to stay in sync.*
