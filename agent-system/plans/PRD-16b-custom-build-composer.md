# PRD-16b: Custom Build Composer UI

**Status**: Ready to build (once PRD-16a is on `main`)
**Phase**: Custom Mode UI
**Depends on**:
- **PRD-16a** (signal catalog + KB lookup) — HARD dependency. The composer consumes the catalog and the recommendation endpoint.
- **PRD-13a** (flow runtime) — HARD. Custom Build mode is registered as a `FlowDefinition`.

**Blocks**: PRD-16c consumes the composer's saved strategies (intraday extension).
**Effort**: ~2 weeks, single owner
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §2 Mode 4, §5 Surface 4 (Custom Builder mockup)

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md.

Goal: ship the Custom Build composer UI — the drag-and-combine surface where
users assemble signal primitives into a strategy. Three deliverables:

  1. Schema additions: `logic_with_prior` on StrategyRule, enabling multi-rule
     composition with AND/OR/weighted-sum operators.

  2. Engine multi-rule fold: when a strategy has > 1 rule, evaluate each rule
     into a Series, then fold left-to-right with the `logic_with_prior`
     operator. Drives the actual WHEN IN / WHEN OUT computation at backtest.

  3. Frontend composer: drag-and-combine UI with recommendation panel
     consuming PRD-16a's KB lookup. Wired as a FlowDefinition
     (custom_build_mode.ts) via PRD-13a's runtime.

PREREQUISITES (must be on main):
  - PRD-16a: signal catalog + KB lookup endpoints
  - PRD-13a: flow runtime infrastructure
  - Existing StrategyBuilderModal + SummaryStep (used downstream of composer)

OUT OF SCOPE for this PRD:
  - Intraday data + multi-tier exits + live dashboard — PRD-16c
  - New signal primitives — covered by PRD-16a
  - Backtest result viewer changes — uses existing strategy detail page

Context to read in order:
  - /Quant Strategy/framework/livermore_product_flow_v2.html §2 Mode 4, §5 Surface 4
  - agent-system/plans/PRD-16a-signal-library-catalog.md (the catalog you consume)
  - agent-system/plans/PRD-13a-flow-runtime-infra.md (the runtime you use)
  - apps/api/app/schemas/strategy.py (StrategyRule schema)
  - apps/api/app/services/backtester/engine.py (where multi-rule fold lands)

Architecture rules (the four principles, see HANDOFF §2):
  1. Reuse — composer feeds into the existing 4-block summary step + backtest
     pipeline; don't fork either.
  2. LEGO bricks — composer pieces are reusable; future thesis-builder may
     reuse <RuleComposer> for confirmation filters.
  3. FlowDefinition — Custom Build is a 5-step flow:
     compose_signals → set_universe → set_risk → review_summary → backtest.
  4. UX rules — useFlowCopy('custom_build', key); skeleton on KB lookup;
     optimistic-add on signal-card drag.

Acceptance: see "Acceptance Checklist" at the bottom. Branch as
`<your-agent-name>/feat/custom-build-composer`. Open one PR; base=main.
```

---

## Design Constraints (the four principles)

Same four. Restated.

### 1. Reuse, don't replicate

- Existing `StrategyBuilderModal` orchestrator — the Custom Build flow is a new step set within the same modal, not a new modal.
- Existing `SummaryStep` brick — composer hands off to it for HOW MUCH editing.
- Existing backtest pipeline (`POST /api/backtest/run`) — composer-produced `StrategyJSON` runs through the same pipeline as templates.
- Existing 4-block summary copy from `useFlowCopy('builder', key)` lexicon — extended for composer-specific labels under `useFlowCopy('custom_build', key)`.
- PRD-16a's `<SignalCatalogBrowser>` brick — used inside the composer for picking primitives.

### 2. LEGO bricks

This PRD ships:
- `<SignalCanvas>` — the drag-and-drop area for assembled rules.
- `<RuleCard>` — wraps a `<SignalPrimitiveCard>` with parameter editors + threshold sliders.
- `<RuleComposer>` — the AND/OR toggle widget between rule cards.
- `<RecommendedDefaultsPanel>` — consumes PRD-16a's KB lookup output.
- `custom_build_mode.ts` — FlowDefinition consumed by the runtime.

PRD-15 (Thesis Builder, future Sprint 2) will reuse `<RuleComposer>` for thesis confirmation filters.

### 3. Mode = FlowDefinition

Custom Build is a 5-step flow:

```
custom_build_mode flow:
  1. compose_signals    — drag from catalog into <SignalCanvas>
  2. set_universe        — single ticker / basket / sector / portfolio
  3. set_risk            — risk preset (low/med/high) + per-position stops
  4. review_summary      — existing 4-block summary; signals are read-only here
  5. backtest_and_save   — existing pipeline
```

Lives at `apps/web/src/lib/flows/custom_build_mode.ts`. Triggered by:
- Strategy Builders tab "Custom build" CTA
- Stock detail page "Customize this template" (future PRD-15 wiring)
- Community page (via "Fork this strategy" — future)

### 4. UX consistency + sub-300ms perceived load

- **Centralized labels** via `useFlowCopy('custom_build', key)`.
- **Skeleton** on KB lookup call (network round-trip to `match-templates`).
- **Optimistic-add** on signal-card drag (rule appears in canvas immediately; persistence is in background).
- **Auto-save draft** every 5 seconds while composing — losing work midway is the #1 retention killer for custom builders.
- **Plain-English everywhere** — rule cards show "RSI below 30" not `rsi_14 < 30`. The underlying schema is structured; the UI is human.

---

## Problem

Custom Mode (Mode 4) ships in v2 with read-only WHEN IN / WHEN OUT blocks. Users can fork a template and edit risk preset + universe, but cannot actually compose signals. PRD-16a shipped the catalog. This PRD ships the assembly UI that turns "browse the library" into "build a strategy."

The composer must:
1. Make signal picking easy (drag from catalog or click-to-add).
2. Make rule composition intelligible (AND/OR between rules; weighted-sum for ranking).
3. Show recommended defaults from the KB lookup so users aren't inventing thresholds blind.
4. Handle the schema → engine round-trip so a composed strategy backtests correctly.
5. Persist drafts so users don't lose work.

## Goals

1. **`logic_with_prior` field** added to `StrategyRule` (additive, backwards compatible).
2. **Engine multi-rule fold** evaluates strategies with > 1 rule per WHEN IN / WHEN OUT block correctly.
3. **`<SignalCanvas>` drag-and-drop UI** for assembling rules.
4. **`<RuleCard>`** with parameter editors + threshold sliders.
5. **`<RuleComposer>`** AND/OR toggle widget between rule cards.
6. **`<RecommendedDefaultsPanel>`** consumes KB lookup + offers one-click "Use these defaults."
7. **`custom_build_mode.ts`** FlowDefinition wired via PRD-13a runtime.
8. **Draft auto-save** every 5 seconds during composition; resume on revisit.
9. **Round-trip backtest** — composer-produced StrategyJSON runs successfully through existing backtest pipeline.

## Non-Goals

- **No new signal primitives** — covered by PRD-16a.
- **No backend test runs at composer-time** — the user explicitly clicks "Backtest" to run; live previews of composed strategies are deferred to a polish PRD.
- **No multi-tier exit ladder** — single stop / single TP only in this PRD; PRD-16c adds the ladder.
- **No intraday data** — PRD-16c.
- **No template-fork UX** — "fork an existing template into composer" is a follow-up; this PRD ships the blank-canvas composer.
- **No community strategy import** — same; follow-up.
- **No collaboration / sharing during composition** — single-user composer for now.

## User stories

1. **As a prosumer building a custom mean-reversion strategy**, I want to drag RSI, Bollinger, and Volume cards into the canvas, AND them together, and see top-3 matching templates suggesting thresholds — so I can start from a known-good baseline.
2. **As any user composing**, I want each rule card to have plain-English controls (sliders for thresholds, dropdowns for parameters) — not JSON editors.
3. **As any user**, I want my draft to persist if I close the tab — losing 20 minutes of composition is the fastest way to make me quit.
4. **As any user**, I want to run the backtest on my composed strategy with one click — the composer hands off cleanly to the existing 4-block summary + backtest pipeline.
5. **As a returning user**, I want to see "Continue your draft" if I left mid-composition — explicit prompt, not silent state.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  SCHEMA EXTENSION (apps/api/app/schemas/strategy.py)                   │
│                                                                        │
│   class StrategyRule:                                                  │
│     ... existing fields ...                                            │
│     logic_with_prior: Optional[Literal["AND", "OR"]] = None            │
│         # Operator joining THIS rule to the previous one in the list.  │
│         # First rule in a block has logic_with_prior=None (no prior).  │
│                                                                        │
│   Backwards-compatible — existing single-rule templates work unchanged.│
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  ENGINE MULTI-RULE FOLD (apps/api/app/services/backtester/engine.py)   │
│                                                                        │
│   For strategies with multiple rules in WHEN IN or WHEN OUT:           │
│     1. Evaluate each rule into a Series of booleans                    │
│     2. Fold left-to-right with logic_with_prior:                       │
│         result = rule[0]                                                │
│         for i in range(1, len(rules)):                                 │
│            if rules[i].logic_with_prior == "AND":                      │
│              result = result & evaluate(rules[i])                      │
│            elif rules[i].logic_with_prior == "OR":                     │
│              result = result | evaluate(rules[i])                      │
│     3. Use result as the WHEN IN / WHEN OUT boolean for backtest        │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  FRONTEND COMPOSER (apps/web/src/components/custom-build/)             │
│                                                                        │
│   <CustomBuildCanvas>                                                  │
│   ├── <SignalCatalogBrowser />     (PRD-16a brick, left rail)         │
│   ├── <SignalCanvas>                (drop target, center)              │
│   │   ├── WHEN IN block                                                │
│   │   │   ├── <RuleCard primitive="rsi_14" />                          │
│   │   │   ├── <RuleComposer logic="AND" />                            │
│   │   │   └── <RuleCard primitive="bbands_lower_touch" />             │
│   │   └── WHEN OUT block                                               │
│   │       └── ...                                                      │
│   ├── <RecommendedDefaultsPanel />  (right rail, PRD-16a brick)       │
│   └── Action bar: Save Draft / Run Backtest                            │
│                                                                        │
│   FlowDefinition: lib/flows/custom_build_mode.ts                       │
│                                                                        │
│   Draft persistence: localStorage (per-user) + optional server-side    │
│     POST /api/strategies/draft for cross-device.                       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. Schema extension

`apps/api/app/schemas/strategy.py`

Add additive field to `StrategyRule`:

```python
class StrategyRule(BaseModel):
    # ... all existing fields unchanged ...

    logic_with_prior: Optional[Literal["AND", "OR"]] = None
    """Operator joining THIS rule to the previous rule in the parent list.
    First rule in a list has logic_with_prior=None. AND means both must
    be true; OR means either must be true. Evaluated left-to-right.

    For 'WHEN IN' blocks: the final boolean Series after fold determines
    entry. For 'WHEN OUT' blocks: same for exit.

    Existing templates with single rules are unaffected — they evaluate
    as a single boolean with no fold.
    """
```

Validation: if a rule has `logic_with_prior` set, it must not be the first rule in its containing list (validator on `StrategyJSON`).

### 2. Engine multi-rule fold

`apps/api/app/services/backtester/engine.py`

Extend `_evaluate_block(rules: list[StrategyRule], ...) -> pd.Series`:

```python
def _evaluate_block(rules: list[StrategyRule], ...) -> pd.Series:
    """Evaluate WHEN IN or WHEN OUT block to a boolean Series.

    If len(rules) == 1: existing single-rule path (backwards compat).
    If len(rules) > 1: fold left-to-right via logic_with_prior.
    """
    if not rules:
        return pd.Series(False, index=index)
    result = _evaluate_single_rule(rules[0], ...)
    for rule in rules[1:]:
        rule_series = _evaluate_single_rule(rule, ...)
        if rule.logic_with_prior == "AND":
            result = result & rule_series
        elif rule.logic_with_prior == "OR":
            result = result | rule_series
        else:
            raise ValueError(
                f"Rule at position {rules.index(rule)} has no logic_with_prior "
                "but is not the first rule in the list"
            )
    return result
```

`_evaluate_single_rule` is a new helper that takes one rule + primitive_id + parameters + thresholds and returns the boolean Series. Most primitive evaluation logic already exists in PRD-16a's SignalProvider impls; this helper just wraps the call + applies the threshold comparison.

### 3. Draft persistence (optional server-side)

`POST /api/strategies/draft` (new endpoint)

```python
@router.post("/strategies/draft")
async def save_draft(payload: DraftRequest, user: User = Depends(get_current_user)):
    # Upsert into user_strategy_drafts table (new model, single row per user)
    # Returns saved_at timestamp
```

Cross-device draft sync is a small ergonomic win; per-user single-draft schema is enough for v1. If implementation feels heavy, ship localStorage-only and add server-side draft in a polish PRD.

### 4. Test plan

`apps/api/tests/`

- `test_logic_with_prior_validation.py` — first rule has no logic_with_prior; subsequent rules must have it.
- `test_multi_rule_fold_and.py` — synthetic 2-rule strategy with AND fold; verify engine output matches manual computation.
- `test_multi_rule_fold_or.py` — same with OR.
- `test_multi_rule_fold_mixed.py` — 3 rules with mixed AND + OR; verify left-to-right evaluation order.
- `test_single_rule_backwards_compat.py` — every existing template with single-rule blocks still produces identical backtest output.
- (If draft endpoint shipped) `test_strategies_draft.py` — save, retrieve, delete.

---

## Frontend changes

### 1. The composer canvas

`apps/web/src/components/custom-build/custom-build-canvas.tsx`

```tsx
export function CustomBuildCanvas() {
  // 3-pane layout:
  //   - Left: <SignalCatalogBrowser> (PRD-16a brick) for picking primitives
  //   - Center: <SignalCanvas> with drop targets for WHEN IN + WHEN OUT
  //   - Right: <RecommendedDefaultsPanel> showing KB lookup top-3
  //
  // Draft state persisted via custom_build_mode flow context + localStorage
  // Optimistic add: dragging a primitive adds it to the canvas immediately
  // Auto-save every 5 seconds while composing
}
```

### 2. Rule cards

`apps/web/src/components/custom-build/rule-card.tsx`

```tsx
export function RuleCard({ primitive, value, onChange, onRemove }: Props) {
  // Renders:
  //   - Primitive name + 1-line description
  //   - Parameter editors (sliders for numeric, dropdowns for enums)
  //   - Threshold editor with plain-English ("RSI below [30] to enter")
  //   - Remove button
  //   - "Preview on chart" link → opens <SignalPreviewChart> in tooltip
}
```

### 3. Rule composer (AND/OR toggle)

`apps/web/src/components/custom-build/rule-composer.tsx`

```tsx
export function RuleComposer({ logic, onChange }: Props) {
  // Toggle between AND / OR
  // Renders as a small vertical bar between rule cards with the operator
  // displayed mid-bar (similar to logic-gate pattern)
}
```

### 4. Recommended defaults panel

`apps/web/src/components/custom-build/recommended-defaults-panel.tsx`

```tsx
export function RecommendedDefaultsPanel({ primitiveIds }: Props) {
  // Calls POST /api/signal-combos/match-templates whenever primitiveIds changes
  // (debounced 400ms — we don't want to re-fetch on every drag mid-flight)
  //
  // Renders top-3 template matches with:
  //   - Template name + 1-line thesis
  //   - Suggested thresholds (e.g. "RSI < 30 → buy, RSI > 60 → sell")
  //   - "Use these defaults" button — sets thresholds + WHEN OUT rules on canvas
}
```

### 5. Flow definition

`apps/web/src/lib/flows/custom_build_mode.ts`

```ts
import { registerFlow } from "./registry";
import { CustomBuildCanvas } from "@/components/custom-build";
import { UniverseStep, RiskStep, SummaryStep } from "@/components/strategy-builder";

export const CustomBuildFlow: FlowDefinition<CustomBuildContext> = {
  id: "custom_build_mode",
  name: "Custom Build",
  triggers: [
    "strategy_builders/custom_build_cta",
    "stock_page/customize_template",  // future PRD-15 wiring
  ],
  initialStepId: "compose_signals",
  steps: [
    { id: "compose_signals", brick: CustomBuildCanvas, next: () => "set_universe" },
    { id: "set_universe", brick: UniverseStep, next: () => "set_risk" },   // existing
    { id: "set_risk", brick: RiskStep, next: () => "review_summary" },     // existing
    { id: "review_summary", brick: SummaryStep, next: () => "backtest" },  // existing
    { id: "backtest", brick: BacktestRunner, next: () => null },           // existing
  ],
  onComplete: (ctx) => router.push(`/strategies/${ctx.savedStrategySlug}`),
};

registerFlow(CustomBuildFlow);
```

### 6. Strategy Builders tab integration

`apps/web/src/app/builders/page.tsx` (extend existing)

Wire the "Custom build" CTA to:

```tsx
<Button onClick={() => startFlow("custom_build_mode", {
  initialContext: { fromTrigger: "strategy_builders/custom_build_cta" }
})}>
  Custom build
</Button>
```

### 7. Test plan

- `__tests__/custom-build-canvas.test.tsx` — drag a primitive; rule card appears; draft saves.
- `__tests__/rule-card.test.tsx` — parameter sliders, threshold editor work; remove button.
- `__tests__/rule-composer.test.tsx` — toggle AND/OR fires callback.
- `__tests__/recommended-defaults-panel.test.tsx` — fetches + renders; "Use these defaults" sets values.
- E2E: `e2e/custom-build.spec.ts` — full flow: open composer → drag 2 primitives → compose AND → get recommendations → use defaults → set universe → backtest → save.

---

## Reusable LEGO bricks created by this PRD

### Backend

| Brick | Path | Used by |
|---|---|---|
| `StrategyRule.logic_with_prior` field | `schemas/strategy.py` (extended) | All multi-rule strategies; PRD-16c respects same field |
| Engine multi-rule fold (`_evaluate_block`) | `services/backtester/engine.py` (extended) | All multi-rule strategies; PRD-16c reuses |
| `POST /api/strategies/draft` (optional) | `routes/strategies_draft.py` | Composer cross-device draft sync |

### Frontend

| Brick | Path | Used by |
|---|---|---|
| `<CustomBuildCanvas>` | `components/custom-build/` | Composer flow step |
| `<RuleCard>` | Same | Composer canvas |
| `<RuleComposer>` | Same | Composer canvas; PRD-15 thesis confirmation filters (future) |
| `<RecommendedDefaultsPanel>` | Same | Composer right rail; future "explain my strategy" surface |
| `custom_build_mode` FlowDefinition | `lib/flows/custom_build_mode.ts` | Strategy Builders custom-build CTA |

---

## Acceptance checklist

A PR is accepted when **all of the following are true**.

### Prerequisites

- [ ] PRD-16a on `main`. Verify `GET /api/signal-primitives` returns ≥ 50 entries.
- [ ] PRD-13a on `main`. Verify `lib/flows/runtime.ts` exists.

### Backend

- [ ] `StrategyRule.logic_with_prior` field added; additive; existing tests pass unchanged.
- [ ] Validator enforces "first rule must not have `logic_with_prior`."
- [ ] Engine `_evaluate_block` handles multi-rule fold correctly for AND and OR.
- [ ] All 5 backend tests pass.
- [ ] Full backend suite passes: `cd apps/api && python3 -m pytest -q`.
- [ ] No regressions in existing 22 strategy_types' backtest output.

### Frontend

- [ ] `<CustomBuildCanvas>` brick implemented; drag-and-drop works.
- [ ] `<RuleCard>` brick implemented; parameter editors + threshold sliders functional.
- [ ] `<RuleComposer>` brick implemented; AND/OR toggle works.
- [ ] `<RecommendedDefaultsPanel>` brick implemented; fetches + renders KB lookup; "Use these defaults" wires through.
- [ ] `custom_build_mode.ts` FlowDefinition registered.
- [ ] Strategy Builders "Custom build" CTA wires through to `startFlow('custom_build_mode')`.
- [ ] Draft auto-save every 5s; resumable on revisit (localStorage + optional server endpoint).
- [ ] All 4 unit tests + 1 E2E pass.
- [ ] `cd apps/web && npm run build` clean.

### Quality

- [ ] Rule cards display plain-English ("RSI below 30") not JSON.
- [ ] KB lookup debounce: 400ms after last canvas change; not on every drag.
- [ ] Drag-and-drop: optimistic add (instant); no flicker.
- [ ] Catalog browser cache hit on warm load < 100ms.

### Round-trip

- [ ] Compose a 2-rule WHEN IN + 1-rule WHEN OUT → save → run backtest → result returns successfully.
- [ ] Refresh page mid-composition → "Continue your draft" prompt → draft state intact.

### Telemetry

- [ ] PostHog events: `composer_opened`, `primitive_added` (with primitive_id), `rule_composer_toggle` (with operator), `recommendation_accepted`, `composer_backtest_run`.

### Documentation

- [ ] Update HANDOFF-livermore-product-flow-v2.md §6 Brick inventory: mark PRD-16b bricks as ✅.
- [ ] PR title: `feat(custom-build): composer UI + multi-rule fold (PRD-16b)`.

---

## Out of scope (do not build in this PRD)

- **Intraday data + multi-tier exits + live dashboard** — PRD-16c.
- **Template-fork into composer** ("start from an existing template, then modify") — follow-up PRD; current scope ships blank-canvas composer.
- **Community strategy import** — follow-up.
- **Live backtest preview during composition** — only on explicit "Backtest" click for now.
- **Per-user signal favorites** — future polish.
- **Multi-user collaboration on a draft** — future Pro feature.
- **LLM-guided composition** ("explain to me what would happen if I added MACD") — different product surface.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 4, §5 Surface 4
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Hard deps: `PRD-16a-signal-library-catalog.md`, `PRD-13a-flow-runtime-infra.md`
- Blocks: `PRD-16c-intraday-active-execution.md`
- Existing modal: `apps/web/src/components/strategy-builder/strategy-builder-modal.tsx`
- Existing engine: `apps/api/app/services/backtester/engine.py`
- Repo conventions: `CLAUDE.md`, `agent-system/PARALLEL_WORK.md`

---

*Drafted 2026-06-08. The composer is the visible-to-user piece — what users will say "Livermore lets me build custom strategies" about. Schema and engine work are small; UI work is the bulk.*
