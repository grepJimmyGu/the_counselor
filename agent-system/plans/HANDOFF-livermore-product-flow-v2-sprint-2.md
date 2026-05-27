# HANDOFF: Livermore Product Flow v2 — Sprint 2

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first.** It is the entry point for the Sprint 2 build of Livermore's v2 product flow. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: 4 weeks (estimated; Sprint 1 came in at ~6h via chip-driven parallel sessions — Sprint 2 may compress similarly because the runtime + brick library are already on `main`)
**Total scope**: 6 PRDs (PRD-Mode1-Refactor, PRD-15, PRD-16, PRD-17, PRD-18, PRD-19)
**Sprint goal**: Bring the remaining four user entry modes (One Asset, Thesis, Custom Build, plus the saved-strategies surface and community thesis cards) onto the same `FlowDefinition` runtime that PRD-13a / PRD-13b shipped in Sprint 1. Extract the portfolio adapter bricks into mode-agnostic versions so every Sprint 2 mode reuses them.

**Updated 2026-05-26 (Sprint 1 closeout)**: Sprint 1 shipped end-to-end. See [`HANDOFF-livermore-product-flow-v2.md`](HANDOFF-livermore-product-flow-v2.md) for the historical record (final acceptance checklist, brick inventory all ✅). This file picks up from there.

---

## 1. TL;DR

Sprint 1 built **the runtime + the first mode**. Sprint 2 builds **the remaining modes** plus surfaces that let users find their saved work and community contributions.

The hard part — `FlowDefinition` runtime, brick library patterns, the `useFlowCopy` lexicon, the self-registering FlowDefinition import pattern — is on `main` and validated end-to-end via Portfolio Mode (PR #125). Each Sprint 2 PRD is "write one flow file + N novel bricks + wire one trigger." That's the explicit promise of the architecture.

The one piece of *foundational* work left in Sprint 2 is **PRD-Mode1-Refactor**: bring the one-asset journey onto the runtime (it bypasses the flow runtime today — the stock-page "Apply a strategy" CTA opens the legacy `StrategyBuilderModal` directly, and the Home picker's "Pick an asset" CTA is a plain `<Link>` to `/stocks`). Doing PRD-Mode1-Refactor *first* extracts PRD-13b's adapter bricks (`portfolio-summary` / `-backtest` / `-review` / `-save`) into mode-agnostic versions that PRD-15 (Thesis) and PRD-16 (Custom Build) will reuse instead of forking.

---

## 2. Where Sprint 1 left off (as of 2026-05-26)

### What's shipped on `main`

| Layer | Files / scope | Status |
|---|---|---|
| Flow runtime | `apps/web/src/lib/flows/{types,runtime,registry,copy}.ts` + `/flow/[flowId]` shell route | ✅ PR #117 + #122 / #123 / #124 hardening |
| First FlowDefinition | `apps/web/src/lib/flows/portfolio-mode.ts` (Mode 2, 7 steps, self-registers on import) | ✅ PR #125 |
| Mode 2 bricks | `<PortfolioUpload>`, `<PortfolioDiagnosis>`, `<OverlayPicker>` | ✅ PR #125 |
| Mode 2 adapter bricks | `portfolio-summary`, `portfolio-backtest`, `portfolio-review`, `portfolio-save` | ✅ PR #125 — **expected to collapse into mode-agnostic versions by PRD-Mode1-Refactor** |
| Mode 1 secondary trigger | `<ApplyStrategyCTA>` brick on `/stocks/[ticker]` | ✅ PR #120 — **opens legacy modal; runtime path comes in PRD-Mode1-Refactor** |
| Home entry picker | `<EntryModePicker>` + `<SavedStrategiesTile>` on Home | ✅ PR #127 |
| Asset Behavior Fingerprint | `AssetFingerprintService` + `<AssetBehaviorFingerprintCard>` + `GET /api/company/{symbol}/asset-behavior` | ✅ PRs #97 / #106 |
| Engine `inherited_universe` | Additive `Optional[list[str]]` field + 3 portfolio overlay strategy_types | ✅ PR #125 |
| `POST /api/portfolio/diagnose` | Cached (60-min LRU) + rate-limited (Scout 5/h, Strategist 50/h, Quant ∞) + pool-safe | ✅ PR #125 + #126 |

### Test count at sprint close

- **Backend pytest**: 790 passed (was 763 pre-Sprint-1; +27 across 5 PRDs + the trap-#13 fix)
- **Frontend vitest**: 55 passed (runner itself shipped in PRD-13a; +55 over Sprint 1)

### Acceptance checklist gaps

The Sprint 1 closeout (PR #128) ticked every line in the original HANDOFF §7 except two `[~]` items:

- **Mode 1 via Home picker** — "Pick an asset" CTA is a `<Link>` to `/stocks`, not `startFlow('one_asset_mode')`. No `one_asset_mode` FlowDefinition exists.
- **Mode 1 via stock-page CTA** — `<ApplyStrategyCTA>`'s `onClick` calls `setBuilderOpen(true)` on the legacy `StrategyBuilderModal`, not `startFlow`.

Both are explicit Sprint 1 carve-outs that **PRD-Mode1-Refactor closes** as the first Sprint 2 PR.

The third gap (signal-cron-emits-aggregate) is **DEFERRED** until Phase B reshape (PR #88 paused per backlog §4) — not a Sprint 2 commitment.

---

## 3. The four principles (load-bearing, unchanged from Sprint 1)

Same four principles as Sprint 1. Re-read before each phase. They're load-bearing because the runtime was built to enforce them — violating one corrupts every mode that follows.

### Principle 1 — Reuse, don't replicate

Sprint 1 shipped 5 modes' worth of plumbing without forking the wizard, the backtest pipeline, the save format, the result viewer, or any tab. Sprint 2 holds the line: **PRD-15 / PRD-16 / PRD-17 must reuse the bricks PRD-Mode1-Refactor extracts**, not build parallel `<ThesisBacktestRunner>` / `<CustomBuildBacktestRunner>` versions.

If you find yourself writing a new "result viewer for thesis mode" or a "save endpoint for custom build mode" — stop. The answer is reuse. PRD-Mode1-Refactor's adapter-brick extraction is the *whole point* of executing it first.

### Principle 2 — LEGO bricks

Sprint 1's brick inventory (HANDOFF v1 §6, all ✅) is the canonical map of what's reusable. Sprint 2 PRDs **must update this file's §6** when they ship; agents reading this doc should treat the inventory as the source of truth for "does this brick already exist?"

Bricks live at `apps/web/src/lib/flows/bricks/`. The `<ApplyStrategyCTA>` pattern from PR #120 + #123 is the canonical brick template:
- `registerModeCopy("mode_id", { ... })` at module load (side effect)
- `useFlowCopy("mode_id", "key")` for every visible label
- `from` prop for surface-aware analytics
- No inline navigation logic for flow-runtime CTAs

### Principle 3 — Mode = `FlowDefinition`, not a route

`portfolio-mode.ts` is the canonical example. 7 steps, pure data, self-registers via `if (!getFlow(id)) registerFlow(...)`. Sprint 2 modes follow the same pattern:

```ts
import { startFlow } from "@/lib/flows/runtime";
startFlow("thesis_mode", { initialContext: { fromTrigger, thesisText } });
```

**A mode's UI logic must not live in a page component or a modal component.** It lives in the flow definition + the bricks. The `<StrategyBuilderModal>` is legacy and will be deleted in Sprint 3 once every mode is on the runtime.

### Principle 4 — UX consistency + sub-300ms perceived load

Same four concrete rules every PR ships against:

- **Centralized labels.** `useFlowCopy(modeId, key)`. No hardcoded user-facing labels in bricks.
- **Skeleton states for every blocking call > 200ms.** Use existing `<Skeleton>` from `components/ui/`.
- **Prefetch on idle.** When the user lands on step N, idle-prefetch step N+1.
- **Optimistic UI.** Save / fork / subscribe show success immediately; API confirms in background; revert + toast on failure.

---

## 4. Reading order (for a coding agent fresh to this work)

Do these in order:

1. **`CLAUDE.md`** (repo root) — auto-loaded by Claude Code. Defines branch naming, master-merger policy, Python 3.9 compat, parallel-work rules.

2. **`agent-system/PARALLEL_WORK.md`** — branch / worktree rules; claim a session-table row before starting.

3. **`agent-system/WORK_LOG.md` Current Session** — the operational "where are we right now" snapshot. Refreshed at every sprint close.

4. **This file** — Sprint 2 plan + the four principles + the gaps Sprint 1 left.

5. **`agent-system/plans/HANDOFF-livermore-product-flow-v2.md`** (Sprint 1) — historical record. Notably §6 (brick inventory, all ✅) is the canonical reusable-bricks reference, and §10 (Sprint 2 preview) is the spec these PRDs evolved from.

6. **`/Quant Strategy/framework/livermore_product_flow_v2.html`** — the original product vision. Read §1 (decision tree), §2 (per-mode flows), §4 (4-tab IA + trigger map), §5 (UI mockups for your assigned mode).

7. **`agent-system/plans/PRD-13a-flow-runtime-infra.md`** — the runtime spec; you'll be calling into it.

8. **`agent-system/plans/PRD-13b-portfolio-mode.md`** — the reference implementation of a real `FlowDefinition`. Read this *before* writing your own — it shows the canonical shape, the self-registration pattern, the adapter-brick wrapping of existing endpoints, the `useFlowCopy` discipline.

9. **Your assigned PRD** — `agent-system/plans/PRD-1X-*.md` (Sprint 2 PRDs will land here).

---

## 5. The six Sprint 2 PRDs

| PRD | Title | Status | Owner | Effort | Depends on | Blocks |
|-----|-------|--------|-------|--------|------------|--------|
| **PRD-Mode1-Refactor** | `one_asset_mode` FlowDefinition + adapter-brick extraction | ⏳ Chip queued (2026-05-26) | TBD | 3-5 days | PRD-13a + PRD-13b (both on main) | PRD-15 + PRD-16 reuse the mode-agnostic adapter bricks this PRD extracts |
| **PRD-15** | Thesis Builder (Mode 3) | ⏳ Draft pending | TBD | ~1 week | PRD-Mode1-Refactor (adapter bricks) | PRD-18 (community thesis cards trigger Mode 3) |
| **PRD-16** | Custom Build (Mode 4) — closes WHEN IN / WHEN OUT read-only gap | ⏳ Draft pending | TBD | ~1 week | PRD-Mode1-Refactor (adapter bricks) | — |
| **PRD-17** | Saved-strategies surface (Home tile + Strategy Builders section) | ⏳ Draft pending | TBD | 3-4 days | None (Home tile already exists from PR #127; this PRD adds the Strategy Builders section and any missing list endpoints) | — |
| **PRD-18** | Community thesis cards (Mode 3 secondary trigger) | ⏳ Draft pending | TBD | ~3 days | PRD-15 (need Thesis Mode to trigger from card click) | — |
| **PRD-19** | Per-holding signal extension | 🚧 Blocked on Phase B reshape | TBD | ~1 week once unblocked | PR #88 (Signals v0 Phase B) reshape — paused per backlog §4 | — |

### Dependency graph

```
              ┌─────────────────────────┐
              │ PRD-Mode1-Refactor      │
              │ one_asset_mode + extract │
              │ adapter bricks (3-5d)    │
              └────────────┬────────────┘
                           │ (mode-agnostic adapter bricks)
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌────────────┐            ┌────────────┐         ┌────────────┐
       │  PRD-15    │            │  PRD-16    │         │  PRD-17    │
       │  Thesis    │            │  Custom    │         │  Saved-    │
       │  Mode (1w) │            │  Build (1w)│         │  strats UI │
       └─────┬──────┘            └────────────┘         │  (3-4d)    │
             │                                          └────────────┘
             ▼
       ┌────────────┐
       │  PRD-18    │
       │  Community │
       │  cards (3d)│
       └────────────┘

       (parallel track — blocked on external work)
       ┌────────────┐
       │  PRD-19    │  ← blocked on PR #88 Phase B reshape
       │  Per-      │
       │  holding   │
       │  signals   │
       └────────────┘
```

### Recommended execution order

- **Week 1**: PRD-Mode1-Refactor (single owner). Lands first to unblock everything else with mode-agnostic adapter bricks.
- **Week 2 in parallel**: PRD-15 + PRD-16 + PRD-17 (three independent owners, three worktrees, three PRs). PRD-17 has no upstream so it can start the moment Sprint 2 begins; PRD-15 and PRD-16 wait for Week 1's PRD-Mode1-Refactor merge but otherwise don't block each other.
- **Week 3**: PRD-18 (after PRD-15 lands).
- **Deferred**: PRD-19 — when Phase B reshape is ready.

Tonight's Sprint 1 wall-clock (~6 hours from PR #117 to PR #128) suggests this 4-week estimate could compress significantly via the chip-driven parallel pattern. The estimates above are *upper bounds*; the foundation that PRD-13a + PRD-13b shipped is doing the heavy lifting from now on.

---

## 6. Branch & PR conventions (unchanged from Sprint 1)

Full rules in `CLAUDE.md`. Recap:

- **Branch name**: `<agent>/<type>/<slug>` — e.g., `claude/feat/one-asset-mode-refactor`. No bare `feat/*`.
- **Worktree**: spin up `git worktree add ../the_counselor-<session-tag> -b <branch> main`. Don't work in the canonical root.
- **One PR per PRD**. No stacking — backend CI only fires when `base=main`.
- **Master-merger**: only `claude-main` runs `gh pr merge` against `main`. Everyone else opens PRs and waits.
- **Pre-push**: backend `pytest -q` green, frontend `npm run build` + `npm run test -- --run` clean, Python 3.9 compat audit on diff.
- **Karpathy principles** apply by default: think first, simplicity, surgical changes, goal-driven.

---

## 7. Brick inventory (Sprint 2 additions)

The Sprint 1 inventory lives in [`HANDOFF-livermore-product-flow-v2.md` §6](HANDOFF-livermore-product-flow-v2.md) — every entry ✅ shipped. Reuse what's there before adding new bricks.

### Bricks Sprint 2 will add

#### Adapter brick extractions (PRD-Mode1-Refactor)

| Brick (current name) | Becomes | Used by |
|---|---|---|
| `portfolio-summary` (Mode 2 only) | `<SummaryStep>` (mode-agnostic) | Mode 1, Mode 2, Mode 3, Mode 4 |
| `portfolio-backtest` (Mode 2 only) | `<BacktestRunner>` (mode-agnostic) | Mode 1, Mode 2, Mode 3, Mode 4 |
| `portfolio-review` (Mode 2 only) | `<ResultViewer>` (mode-agnostic) | Mode 1, Mode 2, Mode 3, Mode 4 |
| `portfolio-save` (Mode 2 only) | `<SaveStrategy>` (mode-agnostic) | Mode 1, Mode 2, Mode 3, Mode 4 |

Existing Portfolio Mode keeps working through these renames — adapter wrappers preserve the prop surface. The promise PRD-13b's commit message made: *"Sprint 2's Mode 1 refactor will collapse these into mode-agnostic bricks."*

#### New mode-specific bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `one-asset-mode.ts` (FlowDefinition) | PRD-Mode1-Refactor | ⏳ | Stock page Apply CTA + Home picker Pick-an-asset CTA |
| `<OneAssetTemplatePick>` brick (if extracted from `StrategyBuilderModal`) | PRD-Mode1-Refactor | ⏳ | Mode 1 |
| `thesis-mode.ts` (FlowDefinition) | PRD-15 | ⏳ | Home picker Chat-builder CTA (typed thesis input) + Community thesis cards |
| `<ThesisInput>` brick | PRD-15 | ⏳ | Mode 3 |
| `<ThesisFormulaPreview>` brick | PRD-15 | ⏳ | Mode 3 |
| `<ConfirmationFilters>` brick | PRD-15 | ⏳ | Mode 3 |
| `custom-build-mode.ts` (FlowDefinition) | PRD-16 | ⏳ | Strategy Builders Custom Build tile |
| `<SignalComposer>` brick (closes WHEN IN / WHEN OUT read-only gap) | PRD-16 | ⏳ | Mode 4 |
| `<SavedStrategiesSection>` brick (Strategy Builders surface) | PRD-17 | ⏳ | Strategy Builders page; reuses `<SavedStrategiesTile>`'s API helper from PR #127 |
| `<CommunityThesisCard>` brick | PRD-18 | ⏳ | `/community` page |

Sprint 2 closeout will flip all ⏳ → ✅ in this section and add a final entry tying it back to this file.

---

## 8. Sprint-level acceptance

The sprint is done when **all of the following are true**:

### Functional

- [ ] User on Home page can click "Pick an asset" → **`startFlow('one_asset_mode')`** fires → ticker pick step → template pick → summary → backtest → save. (PRD-11 CTA wired to runtime via PRD-Mode1-Refactor)
- [ ] User on any stock detail page can click "⚡ Apply a strategy" → **`startFlow('one_asset_mode', { initialContext: { ticker } })`** fires → skips ticker step → template pick → backtest → save. (PRD-14 CTA wired to runtime via PRD-Mode1-Refactor)
- [ ] User on Home page can click "Chat builder" → types a plain-English thesis → routes into Mode 3 (`thesis_mode`) → formula preview → confirmation filters → backtest → save. (PRD-15)
- [ ] User on Strategy Builders can click "Custom Build" → composes a WHEN IN / WHEN OUT signal via the editable picker (not the read-only template view today) → summary → backtest → save. (PRD-16)
- [ ] User on Strategy Builders sees a "Saved strategies" section listing their saved work; clicking a row resumes/clones the strategy. (PRD-17)
- [ ] User on Home page's "Your saved strategies" tile sees the same data + signal chips. (PRD-17 — already shipped via PRD-11 + PR #127; PRD-17 extends to Strategy Builders surface)
- [ ] User on `/community` sees thesis cards; clicking a card triggers Mode 3 with the published thesis pre-loaded. (PRD-18)
- [ ] All four modes (1, 2, 3, 4) survive close-tab-and-reopen via sessionStorage resume with `schemaVersion: 1` invalidation. (PRD-13a runtime, validated per-PRD)

### Architectural

- [ ] **The two Sprint 1 `[~]` acceptance lines on Mode 1 flip to `[x]`** in the Sprint 1 HANDOFF doc (or get a forward-reference here).
- [ ] At least **four** `FlowDefinition` modes on `main`: `portfolio_mode` (Sprint 1) + `one_asset_mode` + `thesis_mode` + `custom_build_mode`.
- [ ] Adapter bricks (`SummaryStep`, `BacktestRunner`, `ResultViewer`, `SaveStrategy`) are mode-agnostic and reused by all four modes — no per-mode forks.
- [ ] Brick inventory section (§7 of this doc + §6 of the Sprint 1 HANDOFF) updated to ✅ for every shipped brick.
- [ ] Legacy `<StrategyBuilderModal>` flagged as **deprecated** in code comments + tracked in PROJECT_BACKLOG.md for Sprint 3 deletion. Don't delete it in Sprint 2 — it may still be referenced by surfaces not yet refactored.

### Quality

- [ ] `cd apps/api && python3 -m pytest -q` — green, including any new tests per PRD.
- [ ] `cd apps/web && npm run build` — clean, no TypeScript errors.
- [ ] `cd apps/web && npm run test -- --run` — green; vitest count grows by ~10-20 per PRD.
- [ ] No `X | None` syntax in backend code (Python 3.9 compat).
- [ ] PostHog events captured for each new mode's per-step transitions + each new trigger.
- [ ] No regressions in existing tests, especially engine `test_engine_cross_sectional` / `test_vol_target` / `test_fundamental_templates` (signal-composer in PRD-16 may touch StrategyJSON; verify additivity the same way PRD-13b did).

### Documentation

- [ ] `agent-system/WORK_LOG.md` Current Session updated at each PRD merge.
- [ ] `docs/PROJECT_BACKLOG.md` updated when Sprint 1 deferred items unblock.
- [ ] Sprint 2 PRD files (PRD-Mode1-Refactor, PRD-15, PRD-16, PRD-17, PRD-18, PRD-19) all committed to `main` in their owning PRs.
- [ ] Sprint 2 closeout PR flips brick inventory ⏳ → ✅ and adds the Sprint 2 wrap entry to `project_log.md` + `docs/BUILDING_LIVERMORE_JOURNAL.md` (Episode 29+).

---

## 9. Common pitfalls (read before your first commit)

These bit prior PRs. Don't let them bite yours.

### Sprint-1-carried pitfalls (still relevant)

- **A. Stacked PRs lose backend CI** — `.github/workflows/backend-ci.yml` only fires on `pull_request.branches: [main]`. Always rebase + `base=main`.
- **B. Don't run `git add -A` or `git add .`** — explicit pathspecs only. Run `git status --short` immediately before every `git add`.
- **C. Branch you didn't create** — don't push to a branch you didn't create unless explicitly asked.
- **D. `X | None` syntax** — CI runs on Python 3.9. Use `Optional[X]`. Grep your diff before pushing.
- **E. The flow infrastructure must land before flow consumers** — preserved from Sprint 1; relevant if anyone tries to ship Sprint 2 PRDs in the wrong order. PRD-Mode1-Refactor must land before PRD-15 / PRD-16 consume the mode-agnostic adapter bricks.
- **F. Engine `inherited_universe` is additive — don't break existing templates** — relevant if PRD-16's signal-composer adds new `strategy_type` literals. Run the full pytest suite after any engine touch.
- **G. FUSE-mount git lock issues** — sandbox-specific; `mv .git/index.lock /tmp/dead.lock` if `unlink` is denied.

### New pitfalls from Sprint 1 close

- **H. Acceptance language: "the journey works" ≠ "the journey routes through the architecture".** Tonight's Mode 1 acceptance ticks got downgraded from `[x]` to `[~]` because Jimmy's screenshot caught the gap: the CTA opens the legacy `StrategyBuilderModal` but doesn't call `startFlow`. When writing per-PRD acceptance criteria, be explicit which one you mean. *"Mode 3 fires"* is ambiguous; *"`startFlow('thesis_mode', ...)` writes a sessionStorage entry with `flowId=thesis_mode`"* is not.

- **I. Commit the planning docs as you go.** Sprint 1's HANDOFF + 5 PRDs sat untracked in canonical root the whole sprint. The Sprint 1 closeout PR (#128) had to land them all at once. Sprint 2 PRDs should be committed in their owning PR (or a small bootstrap PR at the start of the sprint), not deferred to closeout — the "Reading order" §4 above can't work for fresh agents if the files aren't on `main`.

- **J. Trap #13 / DB-session-across-slow-await applies to ALL async route handlers.** PR #126 fixed `POST /api/portfolio/diagnose`. Any new endpoint PRD-15 / PRD-16 / PRD-17 adds that's `async def` + takes `db: Session = Depends(get_db)` + awaits external HTTP should mirror PR #126's pattern (`db.close()` before the slow await, `SessionLocal()` blocks for the work + the cache write). The `apps/api/CLAUDE.md` trap #13 has the recipe.

- **K. PRD-13b's adapter bricks are *not* mode-agnostic yet.** If you ship PRD-15 or PRD-16 *before* PRD-Mode1-Refactor extracts them, you'll be tempted to copy-paste the `portfolio-summary` brick into `thesis-summary` and forever own the mode-specific fork. Don't. Wait for PRD-Mode1-Refactor.

---

## 10. Sprint 3 preview (what's after Sprint 2)

After Sprint 2 the architecture is fully populated — every entry mode has a `FlowDefinition`, every adapter brick is mode-agnostic, and the legacy `StrategyBuilderModal` is dead weight. Sprint 3 candidates:

- **Sprint 3a — Delete the legacy `StrategyBuilderModal`.** Audit every reference; migrate the last few surfaces (probably `/workspace`?) onto the runtime; remove the file. Codify "no inline step machines outside `lib/flows/runtime.ts`" as a rule.
- **Sprint 3b — Mode 5 (Idea) + Mode 6 (Discovery)** if traffic / user behavior signals they're worth investing in. Both modes were named in the v2 spec but deprioritized for Sprint 1-2 because they're less critical to the activation flow.
- **Sprint 3c — Per-mode analytics dashboards.** PostHog funnels per `startFlow` event stream. Once enough modes are running, the per-step drop-off data tells us where the flow runtime's UX rules need tightening.
- **Sprint 3d — Re-engagement modal reusing `<EntryModePicker>`.** The picker was built as a brick specifically so it could appear inside a modal when a user returns after a gap. Sprint 3 wires the modal once retention data warrants it.

**Implications for Sprint 2** (already enforced by the architecture):

- `startFlow` accepts an arbitrary `initialContext` shape — every mode extends `FlowContextBase`. Sprint 3's re-engagement modal won't need new runtime work.
- `useFlowCopy(modeId, key)` is 2-arg — Sprint 3's Mode 5/6 labels won't trigger a refactor of PRD-13a's contract.
- Brick reuse is the rule. Sprint 3 PRDs should expect to write *zero* new adapter bricks — only mode-specific input/preview bricks.

---

## 11. Final pre-flight checklist

Before you write your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] `CLAUDE.md` auto-loaded (Claude Code) or you've read it manually (other agents).
- [ ] You've read the Sprint 1 HANDOFF doc's §6 (brick inventory) and §10 (Sprint 2 preview).
- [ ] You've read the relevant section of `livermore_product_flow_v2.html` for your PRD's modes.
- [ ] You've read `PRD-13b-portfolio-mode.md` as the reference implementation pattern.
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md` Active Sessions.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] You've confirmed your PRD's "Coding-agent kickoff prompt" still matches this doc and CLAUDE.md (no drift).
- [ ] If your PRD is PRD-15 / PRD-16 — you've confirmed PRD-Mode1-Refactor is already on `main`. If it isn't, **stop and wait** (or work on PRD-17 instead, which has no upstream).

If all checked, start. If any unchecked, fix that first.

---

*Sprint 2 plan drafted 2026-05-26 at Sprint 1 closeout. Cross-reference: Sprint 1 record at [`HANDOFF-livermore-product-flow-v2.md`](HANDOFF-livermore-product-flow-v2.md); product vision at `/Quant Strategy/framework/livermore_product_flow_v2.html`; current state at `agent-system/WORK_LOG.md` Current Session.*
