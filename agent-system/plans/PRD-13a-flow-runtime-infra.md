# PRD-13a: Flow Runtime Infrastructure

**Status**: Ready to build
**Phase**: Sprint 1 — foundation
**Depends on**: None (pure foundation; no external deps)
**Blocks**: PRD-11 (wires Home triggers via `startFlow`), PRD-13b (defines the first concrete `FlowDefinition`), and every future mode (PRD-15, PRD-16, …)
**Effort**: 2–3 days, single owner
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §4 Navigation IA (especially principle "expanding user routes is NOT equivalent as adding more web page tabs")

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/web). Read CLAUDE.md first
(auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md.

Goal: build the FLOW RUNTIME — the foundation every Sprint 1+ entry mode
will plug into. Four files in apps/web/src/lib/flows/:

  - types.ts       (FlowDefinition, FlowStep, FlowContext, FlowEvent types)
  - runtime.ts     (startFlow, useFlowState, persistState, FlowProvider)
  - registry.ts    (FLOW_REGISTRY: which modes exist)
  - copy.ts        (useFlowCopy(modeId, key) hook + lexicon)

This PRD ships INFRASTRUCTURE ONLY. No bricks, no flow definitions, no UI
wiring. The runtime must be importable + testable in isolation. PRD-13b
ships the first concrete FlowDefinition (portfolio_mode); PRD-11 wires
the Home trigger to startFlow().

Critical constraint: the public API must be Sprint-2-ready. Specifically
useFlowCopy MUST take (modeId, key) — not just (key) — so Mode 3
(Thesis) and Mode 4 (Custom Build) can disambiguate "portfolio" labels
from "thesis" labels when they ship.

Acceptance: the checklist at the bottom of this PRD, fully ticked.
Branch as `<agent>/feat/flow-runtime-infra`. One PR, base=main.
```

---

## Design Constraints (the four principles)

Same four principles as the rest of the Sprint 1 packet — see HANDOFF doc §2. The infrastructure built here is itself the **mechanism** by which the four principles get enforced across modes, so the API surface matters more than usual.

### 1. Reuse, don't replicate

Nothing to reuse here yet — this PRD creates the foundation. But the foundation must be reusable by every future mode.

### 2. LEGO bricks

This PRD ships **the brick-loading machinery**, not bricks. Bricks come in PRD-13b and onward. The runtime defines the contract every brick will satisfy: `(props: FlowStepProps) => JSX.Element`.

### 3. Mode = FlowDefinition

The TypeScript types in this PRD are the schema for that abstraction. Get them right and Sprint 2 is cheap; get them wrong and every later mode pays the refactor tax.

### 4. UX rules

`useFlowCopy` is the centralized label lexicon. Sub-300ms perceived load: the runtime exposes `prefetch(stepId)` and emits a `step_idle` event so bricks can opportunistically warm up the next call.

---

## Problem

Today, the strategy-builder modal (`apps/web/src/components/strategy-builder/strategy-builder-modal.tsx`) is a 1163-line React component that hardcodes its step machine inline as `type Step = "launch" | "template-pick" | …`. Adding a new entry mode means editing this monster file and forking its state logic.

Sprint 1+ adds five new entry modes (Mode 1 refactor, Mode 2 portfolio, Mode 3 thesis, Mode 4 custom build, Mode 5 idea). Continuing the inline-step-machine pattern would force all five modes to share one growing file and force every PRD to step on the others' merge conflicts.

The solution from the v2 product flow spec: **each mode is a declarative `FlowDefinition` object**, rendered by a shared runtime that handles persistence, navigation, prefetching, and analytics. Triggers from any UI surface (Home button, stock page CTA, community card, chat command) call:

```ts
startFlow('portfolio_mode', { initialContext: ctx });
```

No code duplication. No 1500-line monster modals. Sprint 2 modes cost a flow file + bricks.

This PRD ships the runtime. It is foundation-only — zero user-visible UI lands.

## Goals

1. **Four files in `apps/web/src/lib/flows/`** — `types.ts`, `runtime.ts`, `registry.ts`, `copy.ts` — with the full public API.
2. **Runtime supports session-persistence** — close the tab mid-flow, reopen, resume from the same step with context intact.
3. **`useFlowCopy(modeId, key)` ships with the 2-arg signature today** so Sprint 2 modes don't refactor it.
4. **Typed events** emitted on every step transition for analytics (PostHog wiring is downstream PRD; this PRD just emits the events).
5. **Mock flow definition + tests** — the runtime is testable in isolation against a fixture flow; no real bricks required.

## Non-Goals

- No `FlowDefinition` for any real mode in this PRD. That's PRD-13b (`portfolio_mode`), PRD-11 (Home trigger), etc.
- No UI redesign of `StrategyBuilderModal`. The modal continues to work as-is; flow runtime sits *alongside* it. A future PRD migrates existing modal logic into a `FlowDefinition` if/when that's worth doing.
- No backend changes.
- No PostHog wiring (events are emitted; downstream PRD subscribes).
- No new tab, no new route, no new page.

---

## The four files

### File 1: `apps/web/src/lib/flows/types.ts`

```ts
import type { ComponentType } from "react";

/**
 * A FlowContext is the typed bag of state a flow accumulates as the user
 * progresses through steps. Each mode extends this with its own fields
 * (declared in the mode's FlowDefinition). Generic over T to keep
 * mode-specific context shapes type-safe.
 */
export interface FlowContextBase {
  /** Identifier of the UI surface that launched the flow.
   *  Format: "<surface>/<action>" — e.g., "home/upload_portfolio",
   *  "builders/multi_ticker", "stock_page/apply_strategy".
   *  Used for analytics and for surface-specific copy variants. */
  fromTrigger: string;
}

export interface FlowStepProps<TCtx extends FlowContextBase = FlowContextBase> {
  context: TCtx;
  updateContext: (patch: Partial<TCtx>) => void;
  advance: () => void;        // go to next step (uses next() predicate)
  back: () => void;           // go to previous step
  abort: () => void;          // exit flow, discard state
}

export interface FlowStep<TCtx extends FlowContextBase = FlowContextBase> {
  id: string;
  /** The React component for this step. Receives FlowStepProps<TCtx>. */
  brick: ComponentType<FlowStepProps<TCtx>>;
  /** Optional validator. Returns true to allow advance, false to block,
   *  or a string error message to show the user. */
  validate?: (context: TCtx) => boolean | string;
  /** Optional next-step predicate. Returns the next step id, or null
   *  to mark this step terminal. Defaults to the next step in the
   *  `steps` array. */
  next?: (context: TCtx) => string | null;
  /** Optional idle-prefetch hook. Called when the step has been
   *  rendered for > 300ms and the user hasn't interacted. Use to
   *  warm up the next step's API calls. */
  prefetch?: (context: TCtx) => Promise<void>;
}

export interface FlowDefinition<TCtx extends FlowContextBase = FlowContextBase> {
  id: string;                                  // unique mode id (e.g., 'portfolio_mode')
  name: string;                                // user-facing
  /** Documented entry points. Format: "<surface>/<action>". */
  triggers: string[];
  steps: FlowStep<TCtx>[];
  initialStepId: string;
  /** Called when the user completes the terminal step. Use to navigate
   *  to a result page, save state, fire analytics, etc. */
  onComplete: (context: TCtx) => void;
  /** Called when the user aborts the flow. Use to clean up partial
   *  state or fire abandonment analytics. */
  onAbort?: (context: TCtx) => void;
}

/** Emitted by the runtime on every step transition. Subscribe via
 *  FlowProvider's `onEvent` prop (a downstream PRD wires this to PostHog). */
export type FlowEvent =
  | { type: "flow_started"; flowId: string; trigger: string }
  | { type: "step_entered"; flowId: string; stepId: string }
  | { type: "step_exited";  flowId: string; stepId: string; advancedTo: string | null }
  | { type: "step_idle";    flowId: string; stepId: string }   // fires after 300ms of no interaction
  | { type: "flow_completed"; flowId: string }
  | { type: "flow_aborted"; flowId: string; atStep: string };
```

### File 2: `apps/web/src/lib/flows/runtime.ts`

```ts
import type { FlowDefinition, FlowEvent, FlowContextBase } from "./types";
import { FLOW_REGISTRY } from "./registry";

const STORAGE_KEY = (flowId: string) => `livermore_flow_${flowId}`;

interface RuntimeState<TCtx extends FlowContextBase> {
  flowId: string;
  currentStepId: string;
  context: TCtx;
}

/**
 * Public API. Called by any UI trigger.
 *   startFlow('portfolio_mode', { initialContext: { fromTrigger, ...ctx } });
 *
 * Resolves the flow from FLOW_REGISTRY, persists initial state to
 * sessionStorage, navigates to the flow shell route, and fires
 * 'flow_started'.
 */
export function startFlow<TCtx extends FlowContextBase>(
  flowId: string,
  opts: { initialContext: TCtx }
): void;

/**
 * React hook used INSIDE each step brick. Returns the current step,
 * the context, and the navigation helpers. Bricks declare their
 * props via FlowStepProps<TCtx> rather than calling this directly,
 * but it's available for advanced cases (debugging, conditional
 * sub-flows).
 */
export function useFlowState<TCtx extends FlowContextBase>(): {
  flow: FlowDefinition<TCtx>;
  step: FlowStep<TCtx>;
  context: TCtx;
  updateContext: (patch: Partial<TCtx>) => void;
  advance: () => void;
  back: () => void;
  abort: () => void;
};

/** Internal — used by the runtime to write state to sessionStorage. */
function persistState<TCtx extends FlowContextBase>(state: RuntimeState<TCtx>): void;

/** Internal — used by the runtime to read state from sessionStorage on
 *  page load. Returns null if no flow in progress. */
function resumeState<TCtx extends FlowContextBase>(flowId: string): RuntimeState<TCtx> | null;

/**
 * The React provider that wraps the flow shell page. Renders the
 * current step's brick, handles transitions, and emits events.
 *   <FlowProvider flowId="portfolio_mode" onEvent={handleEvent}>
 *     <FlowShell />
 *   </FlowProvider>
 */
export const FlowProvider: React.FC<{
  flowId: string;
  onEvent?: (event: FlowEvent) => void;
  children: React.ReactNode;
}>;
```

Implementation notes:

- `startFlow` navigates to `/flow/<flowId>` (a new Next.js route added in this PRD, rendering `<FlowProvider><FlowShell /></FlowProvider>`).
- The flow shell page is the only new route. It renders the current step's brick component.
- `step_idle` fires via `setTimeout(300ms)` after the step mounts, cleared on any user interaction (mousemove, keydown, click).
- `persistState` is debounced (250ms) to avoid spamming sessionStorage on every keystroke when the brick updates context.

### File 3: `apps/web/src/lib/flows/registry.ts`

```ts
import type { FlowDefinition } from "./types";

/**
 * The flow registry. Empty at PRD-13a; populated as modes ship:
 *   PRD-13b → portfolio_mode
 *   PRD-15  → thesis_mode
 *   PRD-16  → custom_build_mode
 *   PRD-XX  → one_asset_mode (refactor; future)
 *
 * Importing the registry triggers the flow definitions to register
 * themselves via side-effect (each mode's file calls
 * `registerFlow(MyFlowDef)` on module load). The registry exposes
 * the public lookup API.
 */
const REGISTRY = new Map<string, FlowDefinition<any>>();

export function registerFlow<TCtx extends FlowContextBase>(flow: FlowDefinition<TCtx>): void {
  if (REGISTRY.has(flow.id)) {
    throw new Error(`Flow already registered: ${flow.id}`);
  }
  REGISTRY.set(flow.id, flow);
}

export function getFlow<TCtx extends FlowContextBase>(flowId: string): FlowDefinition<TCtx> | undefined {
  return REGISTRY.get(flowId) as FlowDefinition<TCtx> | undefined;
}

export function listFlows(): readonly FlowDefinition<any>[] {
  return Array.from(REGISTRY.values());
}

export const FLOW_REGISTRY = { register: registerFlow, get: getFlow, list: listFlows };
```

### File 4: `apps/web/src/lib/flows/copy.ts`

```ts
/**
 * Central label lexicon. Sprint 1+ rule: NO HARDCODED LABELS IN BRICKS.
 * All user-facing copy comes through useFlowCopy(modeId, key).
 *
 * The 2-arg signature is intentional and Sprint-2-ready. Mode 3's
 * "thesis" labels differ from Mode 2's "portfolio" labels, but the
 * framework labels (Backtest, Save, Risk preset, etc.) resolve the
 * same regardless of modeId via the FRAMEWORK_COPY fallback.
 *
 * Lookup order:
 *   1. MODE_COPY[modeId][key]      — mode-specific override
 *   2. FRAMEWORK_COPY[key]          — shared default across modes
 *   3. key                          — fallback to the key itself (dev mode warning)
 */

interface ModeCopyMap { [key: string]: string }
interface FrameworkCopyMap { [key: string]: string }

const FRAMEWORK_COPY: FrameworkCopyMap = {
  backtest_button: "Run backtest →",
  save_button:     "Save strategy",
  risk_preset_low:    "Conservative",
  risk_preset_medium: "Balanced",
  risk_preset_high:   "Aggressive",
  what_block_title:    "WHAT",
  when_in_block_title: "WHEN IN",
  how_much_block_title:"HOW MUCH",
  when_out_block_title:"WHEN OUT",
  // ... etc
};

const MODE_COPY: { [modeId: string]: ModeCopyMap } = {
  // Each mode contributes its own subset; modes register theirs from
  // their FlowDefinition module via registerModeCopy().
  // PRD-13b registers: portfolio_mode.upload_title, etc.
};

export function registerModeCopy(modeId: string, copy: ModeCopyMap): void {
  if (MODE_COPY[modeId]) {
    Object.assign(MODE_COPY[modeId], copy);
  } else {
    MODE_COPY[modeId] = copy;
  }
}

export function useFlowCopy(modeId: string, key: string): string {
  if (MODE_COPY[modeId]?.[key] !== undefined) return MODE_COPY[modeId][key];
  if (FRAMEWORK_COPY[key] !== undefined) return FRAMEWORK_COPY[key];
  if (process.env.NODE_ENV !== "production") {
    console.warn(`[useFlowCopy] missing copy for ${modeId}.${key} — returning key as fallback`);
  }
  return key;
}
```

---

## Test plan

`apps/web/src/lib/flows/__tests__/`

### `runtime.test.ts`

- `startFlow('test_flow', ...)` persists state to sessionStorage.
- Closing and reopening the page resumes at the same step with context intact.
- `updateContext({ x: 1 })` then `back()` then `advance()` preserves `x = 1`.
- `abort()` clears sessionStorage and fires `flow_aborted`.
- Unknown `flowId` throws a clear error (not undefined).

### `events.test.ts`

- All five event types fire in expected order: `flow_started → step_entered → step_idle → step_exited → step_entered → … → flow_completed`.
- `step_idle` fires 300ms after step mount, but NOT if the user interacted.

### `copy.test.ts`

- `useFlowCopy('mode_a', 'foo')` returns `MODE_COPY.mode_a.foo` when registered.
- Falls back to `FRAMEWORK_COPY.foo` when mode-specific is absent.
- Falls back to the raw key when both are absent (and warns in dev).
- `registerModeCopy('mode_a', { foo: 'bar' })` mutates the registry idempotently.

### `registry.test.ts`

- `registerFlow(flow)` adds to the registry.
- Re-registering the same flow id throws.
- `getFlow(unknownId)` returns `undefined`.
- `listFlows()` enumerates registered flows.

### Test fixture: a mock flow

```ts
// apps/web/src/lib/flows/__tests__/fixtures/mock-flow.ts
export const MockFlow: FlowDefinition<MockContext> = {
  id: "mock_flow",
  name: "Mock",
  triggers: ["test/start"],
  steps: [
    { id: "step1", brick: MockStep1, next: () => "step2" },
    { id: "step2", brick: MockStep2, next: () => "step3" },
    { id: "step3", brick: MockStep3, next: () => null },
  ],
  initialStepId: "step1",
  onComplete: () => {},
};
```

The mock flow is the only consumer of the runtime in this PRD. PRD-13b adds the first real flow (`portfolio_mode`).

---

## Acceptance checklist

### Code

- [ ] Four files exist at `apps/web/src/lib/flows/{types,runtime,registry,copy}.ts`.
- [ ] Public APIs match the contracts above exactly (any deviation must be justified in PR description).
- [ ] `useFlowCopy(modeId, key)` ships with 2-arg signature.
- [ ] New Next.js route `/flow/[flowId]` renders the flow shell (just `<FlowProvider><FlowShell /></FlowProvider>`).
- [ ] No backend changes.

### Tests

- [ ] All four test files exist and pass.
- [ ] Mock flow fixture (`__tests__/fixtures/mock-flow.ts`) exists and is driven through all 3 steps in `runtime.test.ts`.
- [ ] `cd apps/web && npm run test` green.
- [ ] `cd apps/web && npm run build` clean — no TypeScript errors.

### Hygiene

- [ ] PR title: `feat(flows): runtime infrastructure (PRD-13a)`.
- [ ] Branch follows `<agent>/feat/flow-runtime-infra` convention.
- [ ] Base = `main` (no stacked PRs).
- [ ] `git status --short` clean before `git add`; explicit pathspecs only.

### Smoke

- [ ] Open `/flow/mock_flow` in dev → renders MockStep1 → click "advance" → renders MockStep2 → close tab → reopen `/flow/mock_flow` → still on MockStep2 with context intact.

### Documentation

- [ ] Brief docstring at the top of each of the four files explaining the file's role.
- [ ] Update HANDOFF doc §6 (Brick inventory) — mark the four runtime bricks as ✅.
- [ ] Update `apps/web/AGENTS.md` with a "Flow runtime" section pointing to `lib/flows/`.

---

## Out of scope (do not ship in this PRD)

- Any concrete `FlowDefinition` (those are PRD-13b, PRD-15, PRD-16).
- Any brick components (those are PRD-13b onward).
- UI wiring from existing surfaces (Home, Stock page, Strategy Builders) — those PRDs consume the runtime.
- PostHog event subscription (events are emitted; subscription is a follow-up).
- Migrating `StrategyBuilderModal` to use the runtime (future refactor PRD).

---

## Why this is its own PRD (justification for the split)

The original PRD-13 bundled the runtime with portfolio bricks + backend engine work into a 1.5–2 week PRD. Three problems:

1. **PRD-11 (Home redesign) needs `startFlow` to wire its CTAs.** Without the split, PRD-11 has to wait the full 2 weeks.
2. **Sprint 2's PRD-15 (Thesis) and PRD-16 (Custom Build) also depend on the runtime.** Splitting unblocks Sprint 2 architectural design now.
3. **The runtime is reviewed differently from feature work.** It's a foundation API surface; mistakes here propagate to every mode. Reviewing it inside a portfolio-feature PR muddles signal.

This PRD is 2–3 days; PRD-13b is 1.5–2 weeks. They can be reviewed independently. Ship 13a first; 13b and PRD-11 can then proceed in parallel.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §4
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Consumer PRDs: PRD-13b (Portfolio Mode), PRD-11 (Home), and every future mode
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`
