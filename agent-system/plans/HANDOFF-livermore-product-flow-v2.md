# HANDOFF: Livermore Product Flow v2 — Sprint 1

> **You are a coding agent (Claude Code, Codex, or human). Read this doc first.** It is the entry point for the Sprint 1 build of Livermore's v2 product flow. After reading this (~5 minutes), `CLAUDE.md` is auto-loaded for branch/PR conventions; then pick your assigned PRD and start.

**Sprint window**: 4–6 weeks
**Total scope**: 5 PRDs (PRD-11, PRD-12, PRD-13a, PRD-13b, PRD-14)
**Sprint goal**: Ship the two P0 entry modes (One Asset, Portfolio) with their full trigger surfaces and the underlying flow-template + LEGO-brick infrastructure that Sprint 2 will compose against.

**Update 2026-05-26**: PRD-13 split into PRD-13a (flow runtime infrastructure, 2–3 days) and PRD-13b (portfolio mode + engine, 1.5–2 weeks). The split unblocks PRD-11 and any future mode from waiting on the full portfolio work.

---

## 1. TL;DR

The Livermore product is being restructured around **six user entry modes** (One Asset / Portfolio / Thesis / Custom / Idea / Discovery), triggered contextually inside the existing four navigation tabs (Home / Market Pulse / Community / Strategy Builders). Sprint 1 builds the two highest-priority modes (One Asset + Portfolio), their trigger surfaces, and the architectural infrastructure (`FlowDefinition`, runtime, brick library) that all future modes will compose against.

The product vision lives at `/Quant Strategy/framework/livermore_product_flow_v2.html`. Module status (what's shipped vs missing today) lives at `/Quant Strategy/framework/strategy_builder_audit.md`. **Read both before writing code.**

---

## 2. The four principles (load-bearing)

Every PRD in this packet enforces these. Re-read before each phase.

### Principle 1 — Reuse, don't replicate

Sprint 1 must not add: a new wizard, a new backtest pipeline, a new save format, a new result viewer, a new tab. All four exist in the codebase. The novel work is the upload/diagnosis/overlay-picker bricks and the flow runtime. Everything downstream — risk preset, summary, backtest, result, save, publish, monitor — **must** reuse `apps/web/src/components/strategy-builder/` and `apps/api/app/services/backtester/`.

If you find yourself writing a new "result viewer for portfolio mode" or a "save endpoint for thesis mode" — stop. The answer is reuse.

### Principle 2 — LEGO bricks

Every new component, hook, or service is either:

- **A brick** — reusable across modes, with a documented contract.
- **A composer** — wires bricks for *one* mode only, no logic beyond composition.

PRD-13a (runtime) creates bricks like `lib/flows/runtime.ts`, `types.ts`, `copy.ts`. PRD-13b (Portfolio) creates `<PortfolioUpload>`, `<PortfolioDiagnosis>`, `<OverlayPicker>` and `PortfolioDiagnosisService`. PRD-15 (Thesis) and PRD-16 (Custom Build) **must** reuse these where applicable rather than building parallels.

The "Brick inventory" in section 6 of this doc is the running list. Each PRD updates it at the bottom — and reads it at the top.

### Principle 3 — Mode = `FlowDefinition`, not a route

Each entry mode is stored as a declarative `FlowDefinition` object in `apps/web/src/lib/flows/`. The flow defines the steps, validation, and transitions; the runtime renders them. Multiple UI triggers (Home button, Strategy Builders option, stock-page CTA, chat command) call:

```ts
startFlow('portfolio_mode', { initialContext: { fromTrigger, ...ctx } });
```

The flow runtime decides modal vs full-page rendering, persists state in `sessionStorage` (so interruptions resume), and emits typed events for analytics. **A mode's UI logic must not live in a page component.** It lives in the flow definition + the bricks.

This is the abstraction that makes Sprint 2 cheap: adding Mode 3 (Thesis) is "build one or two new bricks + one new flow file + wire one trigger" — not "build another wizard from scratch."

### Principle 4 — UX consistency + sub-300ms perceived load

Four concrete rules every PR ships against:

- **Centralized labels.** `useFlowCopy(key)` reads from `apps/web/src/lib/flows/copy.ts`. No hardcoded labels in bricks. The text for "WHAT" / "WHEN IN" / "Backtest" / "Save" is the same across every mode.
- **Skeleton states for every blocking call > 200ms.** Use existing `<Skeleton>` from `components/ui/`. Skeleton must appear within 50ms of the call starting.
- **Prefetch on idle.** When the user lands on step N, idle-prefetch step N+1's API calls and any chart libs.
- **Optimistic UI.** Save / fork / subscribe show success immediately; API confirms in background; revert + toast on failure.

---

## 3. Reading order (for a coding agent fresh to this work)

Do these in order:

1. **`CLAUDE.md`** (repo root) — auto-loaded by Claude Code on boot. Defines branch naming (`<agent>/<type>/<slug>`), the master-merger policy, Python 3.9 compat rule, the stacked-PR CI gotcha, the parallel-work session table. If you're a non-Claude-Code agent, read it manually first.

2. **`agent-system/PARALLEL_WORK.md`** — branch/worktree rules; claim a session-table row before starting.

3. **This file (HANDOFF-livermore-product-flow-v2.md)** — Sprint 1 plan + the four principles.

4. **`/Quant Strategy/framework/livermore_product_flow_v2.html`** — the product vision. Read §1 (decision tree), §2 (per-mode flows for Mode 1 and Mode 2), §4 (4-tab IA + trigger map), and §5 (UI mockups — especially the mockups for your assigned PRD).

5. **`/Quant Strategy/framework/strategy_builder_audit.md`** — current module status (shipped/partial/missing). Confirms what exists so you don't rebuild it.

6. **`/Quant Strategy/framework/risk_control_prompt.md`** — only if your PRD touches risk-preset wiring (PRD-13b does).

7. **Your assigned PRD** — `agent-system/plans/PRD-1X-*.md`. Each PRD is self-sufficient once the above is in context.

---

## 4. The five Sprint 1 PRDs

| PRD | Title | Status | Owner | Effort | Depends on | Blocks |
|-----|-------|--------|-------|--------|------------|--------|
| **PRD-12** | Asset behavior fingerprint service | ⏳ Draft pending | TBD | ~3 hours | None | PRD-13b (diagnosis composes it), PRD-14 (stock-page surfaces it) |
| **PRD-13a** | Flow runtime infrastructure | ✅ [Ready](PRD-13a-flow-runtime-infra.md) | TBD | 2–3 days | None | PRD-11, PRD-13b, every future mode |
| **PRD-13b** | Portfolio Mode + engine extension | ✅ [Ready](PRD-13b-portfolio-mode.md) | TBD | 1.5–2 weeks | PRD-12, PRD-13a | PRD-11 frontend wiring of "Upload portfolio" CTA |
| **PRD-14** | Stock-page "Apply a strategy" button | ⏳ Draft pending | TBD | ~1 day | PRD-12 | — |
| **PRD-11** | Home page entry picker UI | ⏳ Draft pending | TBD | ~3 days | PRD-13a (runtime), PRD-13b (registers `portfolio_mode`) | — |

### Dependency graph

```
       ┌──────────────┐         ┌──────────────────┐
       │  PRD-12      │         │  PRD-13a         │
       │  fingerprint │         │  Flow runtime    │
       │  (~3h)       │         │  (2–3 days)      │
       └──────┬───────┘         └─────────┬────────┘
              │                            │
              │                            │
       ┌──────┴───────┐                    │
       │              │                    │
       ▼              ▼                    │
  ┌─────────┐  ┌──────────────────────────┴────┐
  │ PRD-14  │  │  PRD-13b                       │
  │ Stock   │  │  Portfolio Mode + engine ext.  │
  │ page CTA│  │  (1.5–2 wk)                    │
  │ (~1d)   │  │  Registers `portfolio_mode`    │
  └─────────┘  └──────────┬─────────────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  PRD-11      │
                   │  Home picker │
                   │  (~3d)       │
                   └──────────────┘
                Calls startFlow('portfolio_mode',…)
```

**Recommended execution** (with the split):

- **Week 1, Mon**: PRD-12 (single agent, ~3h). Lands by EOD Mon.
- **Week 1, Tue–Thu**: PRD-13a (single agent, 2–3 days). The runtime ships before anyone consumes it.
- **Week 1 Fri – Week 3**: PRD-13b starts (1.5–2 weeks). Once on the engine work, can parallel with PRD-14.
- **Week 2 in parallel**: PRD-14 (any agent with frontend skills, ~1 day). Needs PRD-12; doesn't need PRD-13a or PRD-13b.
- **Week 3–4**: PRD-11 (depends on PRD-13a's runtime being on `main` AND PRD-13b registering `portfolio_mode`).

**Why split PRD-13**: the runtime is foundation for every Sprint 1+ mode. Bundling it inside the 2-week portfolio work would force PRD-11 and PRD-15/PRD-16 (Sprint 2) to wait. Splitting unblocks PRD-11 by Week 2 instead of Week 4, and lets Sprint 2 architectural design start as soon as PRD-13a lands. The split also makes pitfall §8.E ("flow infrastructure must land before flow consumers") mechanical rather than a coordination headache.

---

## 5. Branch & PR conventions (quick reference)

Full rules in `CLAUDE.md`. Highlights:

- **Branch name**: `<agent>/<type>/<slug>` — e.g., `claude/feat/portfolio-mode`, `codex/feat/asset-fingerprint`. No bare `feat/*`.
- **Worktree**: spin up `git worktree add ../the_counselor-<session-tag> -b <branch> main`. Don't work in the canonical root (`/Users/jimmygu/the_counselor`).
- **One PR per PRD**. Don't stack PRs — backend CI only fires when `base=main`.
- **Master-merger**: only `claude-main` runs `gh pr merge` against `main`. Everyone else opens PRs and waits.
- **Pre-push**: backend `pytest -q` green, frontend `npm run build` clean, Python 3.9 compat audit on diff.
- **Karpathy principles** (auto-loaded via user memory): think before coding, surgical changes, every changed line traces back to the PRD.

---

## 6. Brick inventory (living document)

The running list of LEGO bricks created across Sprint 1. Each PRD updates this section in its closing PR. Read this before writing new code — if the brick already exists, **reuse it**.

### Backend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `StrategyJSON.inherited_universe` field | PRD-13b | ✅ | Any mode that ingests user-defined tickers — additive; existing 22 strategy_types ignore it |
| `Holding` Pydantic model | PRD-13b | ✅ | Any mode/endpoint ingesting holdings |
| `PortfolioDiagnosisService.diagnose(holdings)` | PRD-13b | ✅ | Mode 2; future watchlist diagnosis; Mode 1 (degenerate N=1 case). Session-safe per PR #126 trap-#13 fix. |
| `AssetFingerprintService.classify(ticker)` | PRD-12 | ✅ | Stock page (PRD-14); Portfolio diagnosis (PRD-13b); Mode 1 picker (Sprint 2) |
| `POST /api/portfolio/diagnose` (cached + rate-limited + pool-safe) | PRD-13b + PR #126 | ✅ | Any frontend surface needing diagnosis |
| `GET /api/company/{symbol}/asset-behavior` | PRD-12 | ✅ | Stock page (PRD-14); future Mode 1 picker |
| `weekly_usage.portfolio_diagnose_runs_hourly` column | PRD-13b | ✅ | Per-tier rate-limiting (Scout 5/h, Strategist 50/h, Quant unlimited) |
| `signal_service` per-holding payload | DEFERRED | ⛔ | Phase B is paused (PR #107); separate follow-up PRD after reshape |

### Frontend bricks

| Brick | Owner PRD | Status | Used by |
|---|---|---|---|
| `lib/flows/types.ts` (FlowDefinition, FlowStep, FlowContext, FlowEvent) | PRD-13a | ✅ | Every mode |
| `lib/flows/runtime.ts` (startFlow, useFlowState, FlowProvider) | PRD-13a + PR #124 | ✅ | Every mode; `schemaVersion: 1` on persisted state for safe schema evolution |
| `lib/flows/copy.ts` (useFlowCopy(modeId, key) — 2-arg, Sprint-2-ready) | PRD-13a | ✅ | Every mode; `registerModeCopy` is the registration pattern |
| `lib/flows/registry.ts` (registerFlow, getFlow) | PRD-13a | ✅ | Every mode |
| `<ApplyStrategyCTA>` brick | PRD-14 | ✅ | Stock detail page; future commodity page, screener result rows. Reusable Mode 1 secondary trigger. |
| `portfolio-mode.ts` (FlowDefinition for Mode 2) | PRD-13b | ✅ | Home upload CTA (PRD-11); Strategy Builders multi-ticker option |
| `<PortfolioUpload>` brick | PRD-13b | ✅ | Mode 2; future watchlist UI |
| `<PortfolioDiagnosis>` brick | PRD-13b | ✅ | Mode 2; future portfolio review pages |
| `<OverlayPicker>` brick (neutral copy in Sprint 1; tease deferred to Sprint 2 polish) | PRD-13b | ✅ | Mode 2; future "rule overlay" patterns |
| `<AssetBehaviorFingerprintCard>` brick | PRD-12 / PRD-14 | ✅ | Stock page; future Mode 1 picker (Sprint 2) |
| `<EntryModePicker>` brick | PRD-11 | ✅ | Home page; future re-engagement modals |
| `<SavedStrategiesTile>` brick | PRD-11 | ✅ | Home page; future saved-strategies surface PRD |

All Sprint 1 bricks ✅ shipped. Sprint 2 PRDs (PRD-15 Thesis, PRD-16 Custom Build, PRD-17 Saved-Strategies surface, PRD-18 Community thesis cards) will compose against these — see §10 Sprint 2 preview.

---

## 7. Sprint-level acceptance

The sprint is done when **all of the following are true**:

### Functional

- [x] User on Home page can click "Pick an asset" → routes to `/stocks` (Mode 1 = existing ticker search; Sprint 2 will refactor to `startFlow('one_asset_mode')`). (PRD-11 + Mode 1)
- [x] User on Home page can click "Upload portfolio" → `startFlow('portfolio_mode')` → upload step → diagnose → overlay → backtest → save. (PRD-11 + PRD-13a + PRD-13b)
- [x] User on Home page can click "Chat builder" → opens floating ChatWidget seeded with the trading-idea greeting. (PRD-11 uses the existing widget per PRD carve-out; Mode 3/5 build in Sprint 2 PRD-15.)
- [x] User on any stock detail page sees "⚡ Apply a strategy" button → opens existing strategy-builder modal with ticker pre-loaded; `<AssetBehaviorFingerprintCard>` renders below sections. (PRD-14 / PR #120)
- [x] User on Strategy Builders, when picking a multi-ticker template, sees "Use my portfolio →" as a universe option → calls `startFlow('portfolio_mode', { fromTrigger: 'builders/multi_ticker_use_my_portfolio', fromTemplate })`. (PRD-13b / PR #125)
- [x] User can interrupt any flow (close tab) → reopens later → resumes at the same step with context intact via sessionStorage. (PRD-13a runtime + PR #124 `schemaVersion: 1` guard; verified end-to-end during PRD-13b smoke at `/test/flows/portfolio`)
- [ ] Mode 2 strategies save successfully → live signal cron emits aggregate signal payload → email alert renders. **DEFERRED**: PR #88 (Signals v0 Phase B) is paused for reshape per backlog §4. Save-strategy works; cron + email are not part of Sprint 1's bar. Tracked in PROJECT_BACKLOG.md.

### Architectural

- [x] `apps/web/src/lib/flows/` exists with `types.ts`, `runtime.ts`, `copy.ts`, `registry.ts`. (PRD-13a / PR #117)
- [x] First `FlowDefinition` shipped: `portfolio_mode` self-registers on import. (PRD-13b / PR #125)
- [x] All four principles enforced — verified across PR reviews #117, #120, #125, #127: no hardcoded labels (every brick routes through `useFlowCopy`), no duplicated wizards (backtest / save / result paths reused via adapter bricks), no JSX in flow definitions (`portfolio-mode.ts` is pure data).
- [x] Brick inventory section (§6 of this doc) updated to ✅ for every shipped brick.

### Quality

- [x] `cd apps/api && python3 -m pytest -q` — **790 passed, 12 skipped** (PR #126 final).
- [x] `cd apps/web && npm run build` — clean, no TypeScript errors.
- [x] `cd apps/web && npm run test -- --run` — **55 / 55 passed** (PR #127 final).
- [x] No `X | None` syntax in backend code (Python 3.9 compat); audited on each PR.
- [x] PostHog events captured: `portfolio_diagnosed`, `portfolio_diagnose_rate_limited`, `stock_page_apply_strategy_clicked`, plus EntryModePicker's per-CTA events.
- [x] No regressions in existing tests — engine additivity verified by PRD-13b (existing 22 strategy_types unaffected; `test_engine_cross_sectional` / `test_vol_target` / `test_fundamental_templates` all green).

### Documentation

- [x] `agent-system/WORK_LOG.md` updated with Sprint 1 wrap (this PR).
- [x] `docs/PROJECT_BACKLOG.md` — Sprint 1 items closed; Sprint 2 PRD candidates listed per §10 below.
- [x] Brick inventory (§6) reflects final state — all entries ✅.
- [x] `HANDOFF` + 5 PRDs committed to `main` in this PR (previously untracked in canonical root only).

---

## 8. Common pitfalls (read this before your first commit)

These bit prior PRs. Don't let them bite yours.

### A. Stacked PRs lose backend CI

`.github/workflows/backend-ci.yml` only fires on `pull_request.branches: [main]`. A PR stacked on another branch gets no backend tests. **Always rebase your PR onto current `main` and set `base=main` before opening.** Full discussion in `CLAUDE.md` §"Stacked PRs lose backend CI".

### B. Don't run `git add -A` or `git add .`

Explicit pathspecs only. The parallel-work setup means stray files from other agents can land in your commit. Run `git status --short` immediately before every `git add`.

### C. Branch you didn't create

Don't push to a branch you didn't create unless explicitly asked. Cross-agent contamination has burned three PRs already. See `CLAUDE.md` §"Hard rules".

### D. `X | None` syntax

CI runs on Python 3.9 even though Railway runs 3.13. Use `Optional[X]` not `X | None`. Grep your diff before pushing.

### E. The flow infrastructure must land before flow consumers

PRD-13a ships `lib/flows/runtime.ts` (foundation, 2–3 days). PRD-13b registers `portfolio_mode` in the runtime. PRD-11 calls `startFlow('portfolio_mode', …)`.

**Strict order**: PRD-13a → PRD-13b → PRD-11 frontend wiring.

PRD-13a is small enough (2–3 days, single owner) that the split is the right way to enforce this — bundling everything inside one giant PRD made the ordering implicit and fragile. With the split, an agent that picks up PRD-11 too early literally cannot start because `startFlow` doesn't exist yet on `main`.

### F. Engine `inherited_universe` is additive — don't break existing templates

Sprint 1 adds `inherited_universe: Optional[list[str]]` to `StrategyJSON`. Existing 22 strategy_types ignore it. After your change, **run the full pytest suite** including `test_engine_cross_sectional.py`, `test_vol_target.py`, `test_fundamental_templates.py`. If anything breaks, the additive-change contract was violated.

### G. FUSE-mount git lock issues (sandbox-specific)

If working from a sandboxed environment that mounts the repo via FUSE, you may hit "cannot create `.git/index.lock`" errors. Workaround:

```bash
mv .git/HEAD.lock /tmp/dead.lock 2>/dev/null
mv .git/index.lock /tmp/dead.lock 2>/dev/null
```

(`unlink` is denied; `mv` is permitted on this mount.) Not a code issue — just sandbox quirk.

---

## 9. When in doubt

- **Architecture question** → check this doc §2 (four principles) and the PRD's "Design Constraints" block. If still unclear, escalate to `claude-main` via a comment on the PR.
- **Branch / PR procedure** → `CLAUDE.md` (auto-loaded).
- **Brick already exists?** → check §6 of this doc.
- **Module already shipped?** → check `/Quant Strategy/framework/strategy_builder_audit.md`.
- **Engine semantics?** → `apps/api/CLAUDE.md` + the relevant `backtester/*.py` file's docstrings.
- **Anything else** → escalate to Jimmy.

---

## 10. Sprint 2 preview (so you can build Sprint 1 with the right hooks)

After Sprint 1, the next PRDs are:

- **PRD-15**: Thesis Builder (Mode 3) — new bricks (`<ThesisInput>`, `<ThesisFormulaPreview>`, `<ConfirmationFilters>`); new flow file (`thesis-mode.ts`); two triggers (Home chat-builder CTA, Community thesis card click).
- **PRD-16**: Custom Build (Mode 4) — signal composer UI; closes the read-only WHEN IN / WHEN OUT gap; reuses 4-block summary step.
- **PRD-17**: Saved-strategies surface — Home tile + Strategy Builders section; reuses existing endpoints.
- **PRD-18**: Community thesis cards — Mode 3 secondary trigger.
- **PRD-19** (or similar): Per-holding signal extension — once Phase B is reshaped (currently paused per PR #107), un-defer the per-holding payload + email template extension. Until then, Portfolio Mode strategies emit aggregate-level signals via the existing cron.
- **Sprint 2 polish PRD**: Overlay backtest tease — pre-compute coarse aggregate stats ("Defensive overlay on growth-tilted portfolios in 2022: average DD reduction = 8pp") and surface them on the OverlayPicker cards. Currently deferred from PRD-13b because live mini-backtests are 2–5s each, not 500ms as originally specced.

**Implications for Sprint 1** (already enforced in PRD-13a):

- **`startFlow` accepts an arbitrary `initialContext` shape.** PRD-13a's `FlowContextBase` defines only `fromTrigger`; each mode extends it. PRD-15's chat-builder will pass `{ thesis_text }`; PRD-18's community card click will pass `{ thesis_id }`. No portfolio-mode-specific fields in the base type.
- **`useFlowCopy(modeId, key)` is already 2-arg.** Sprint 2's Thesis labels won't trigger a refactor of PRD-13a's contract.
- **Brick reuse**: PRD-15 should reuse `<SummaryStep>` from `components/strategy-builder/` for HOW MUCH editing, just as PRD-13b does. The Sprint 1 brick inventory in §6 is the canonical list.

---

## 11. Final pre-flight checklist

Before you write your first line of code:

- [ ] You've read this doc end-to-end.
- [ ] `CLAUDE.md` auto-loaded (Claude Code) or you've read it manually (other agents).
- [ ] You've read the relevant section of `livermore_product_flow_v2.html` for your PRD's modes.
- [ ] You've claimed your row in `agent-system/PARALLEL_WORK.md` Active Sessions.
- [ ] You've spun up a worktree (`git worktree add ../the_counselor-<tag> -b <branch> main`).
- [ ] You've confirmed your PRD's "Coding-agent kickoff prompt" still matches this doc and CLAUDE.md (no drift).

If all six are checked, start. If any are unchecked, fix that first.

---

*Sprint 1 plan drafted 2026-05-26. Cross-reference: source spec at `/Quant Strategy/framework/livermore_product_flow_v2.html`. Updates to this handoff doc require updating every Sprint 1 PRD's "Reading order" section to stay in sync — be deliberate.*
