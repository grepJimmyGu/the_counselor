"use client";

/**
 * Flow runtime — Provider, hooks, navigation, persistence, events.
 *
 * This module is the brick-loading machinery every Sprint 1+ entry mode
 * plugs into. It owns:
 *   - <FlowProvider>     — React context wrapping a flow's runtime state
 *   - useFlowState()     — hook used inside bricks to read context + nav
 *   - <FlowShell />      — renders the current step's brick
 *   - startFlow()        — fire-and-forget launcher called by any UI surface
 *   - sessionStorage     — debounced persistence so interruptions resume
 *   - step_idle timer    — fires after 300ms of no interaction for prefetch
 */

import * as React from "react";
import type {
  FlowContextBase,
  FlowDefinition,
  FlowEvent,
  FlowStep,
} from "./types";
import { getFlow } from "./registry";

const STORAGE_KEY = (flowId: string) => `livermore_flow_${flowId}`;
const PERSIST_DEBOUNCE_MS = 250;
const IDLE_MS = 300;

// Bump when RuntimeState / FlowDefinition contract changes in a way that
// would deserialize subtly wrong from older session entries. Mismatched
// entries are dropped on read, so the user starts fresh instead of
// resuming into a half-shaped context.
const SCHEMA_VERSION = 1;

interface RuntimeState<TCtx extends FlowContextBase> {
  schemaVersion: number;
  flowId: string;
  currentStepId: string;
  context: TCtx;
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function persistState<TCtx extends FlowContextBase>(
  state: RuntimeState<TCtx>
): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY(state.flowId),
      JSON.stringify(state)
    );
  } catch {
    // sessionStorage may be full or disabled; the runtime degrades to
    // in-memory-only without crashing.
  }
}

function resumeState<TCtx extends FlowContextBase>(
  flowId: string
): RuntimeState<TCtx> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY(flowId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as RuntimeState<TCtx>;
    if (!parsed || parsed.flowId !== flowId) return null;
    if (parsed.schemaVersion !== SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function clearState(flowId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY(flowId));
  } catch {
    // ignore
  }
}

// ─── startFlow (called from any UI surface) ──────────────────────────────────

/**
 * Launch a flow. Writes the initial state to sessionStorage and navigates
 * to `/flow/<flowId>`. Triggers the FlowProvider on the destination route
 * to pick up the state and render the first step.
 *
 * Navigation uses `window.location.assign` (full-page) rather than
 * `router.push` (soft) because (a) flows are inherently full-page
 * experiences and (b) keeping `startFlow` as a non-hook function matches
 * the PRD-13a contract. Sprint 2 can swap to soft nav if perf justifies.
 */
export function startFlow<TCtx extends FlowContextBase>(
  flowId: string,
  opts: { initialContext: TCtx }
): void {
  const flow = getFlow(flowId);
  if (!flow) {
    throw new Error(
      `startFlow: unknown flowId "${flowId}". Did you import the mode's FlowDefinition file?`
    );
  }
  const initial: RuntimeState<TCtx> = {
    schemaVersion: SCHEMA_VERSION,
    flowId,
    currentStepId: flow.initialStepId,
    context: opts.initialContext,
  };
  persistState(initial);
  if (typeof window !== "undefined") {
    try {
      window.location.assign(`/flow/${flowId}`);
    } catch {
      // jsdom and some sandboxed envs throw on navigation; the
      // sessionStorage write is the observable side-effect tests verify.
    }
  }
}

// ─── React context ───────────────────────────────────────────────────────────

interface FlowContextValue<TCtx extends FlowContextBase> {
  flow: FlowDefinition<TCtx>;
  step: FlowStep<TCtx>;
  context: TCtx;
  updateContext: (patch: Partial<TCtx>) => void;
  advance: () => void;
  back: () => void;
  abort: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const FlowReactContext = React.createContext<FlowContextValue<any> | null>(null);

/**
 * The React provider wrapping the flow shell page. Renders the current
 * step's brick (via <FlowShell />) and handles transitions.
 *
 *   <FlowProvider flowId="portfolio_mode" onEvent={handleEvent}>
 *     <FlowShell />
 *   </FlowProvider>
 */
export const FlowProvider: React.FC<{
  flowId: string;
  onEvent?: (event: FlowEvent) => void;
  children: React.ReactNode;
}> = ({ flowId, onEvent, children }) => {
  const flow = getFlow(flowId);
  if (!flow) {
    throw new Error(
      `FlowProvider: unknown flowId "${flowId}". Make sure the FlowDefinition file is imported before this provider mounts.`
    );
  }

  // Load initial state. If sessionStorage has prior state for this flow,
  // resume; otherwise start fresh at the definition's initialStepId.
  const [state, setState] = React.useState<RuntimeState<FlowContextBase>>(() => {
    const resumed = resumeState<FlowContextBase>(flowId);
    if (resumed) {
      const validStepId = flow.steps.some((s) => s.id === resumed.currentStepId);
      if (validStepId) return resumed;
    }
    return {
      schemaVersion: SCHEMA_VERSION,
      flowId,
      currentStepId: flow.initialStepId,
      context: { fromTrigger: "direct" } as FlowContextBase,
    };
  });

  // Back-stack so the back() helper can return to the previous step, not
  // just the prior index in `steps`. Without this, conditional `next`
  // predicates can produce confusing back-button behavior.
  const stepStack = React.useRef<string[]>([state.currentStepId]);

  // Emit flow_started + initial step_entered exactly once per mount.
  // (React strict mode runs effects twice in dev; the ref guards against
  // duplicate emission.)
  const startedRef = React.useRef(false);
  React.useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    onEvent?.({
      type: "flow_started",
      flowId,
      trigger: state.context.fromTrigger,
    });
    onEvent?.({ type: "step_entered", flowId, stepId: state.currentStepId });
    // Intentionally empty deps — fire-once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced persist. Every state change schedules a write 250ms later;
  // a subsequent change cancels and reschedules. Prevents sessionStorage
  // spam when bricks update context on every keystroke.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const t = window.setTimeout(() => persistState(state), PERSIST_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [state]);

  // step_idle: fires 300ms after a step mounts IF no user interaction.
  // Any mousedown / keydown / mousemove cancels it. Bricks can use the
  // event to opportunistically prefetch.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    const onInteraction = () => {
      cancelled = true;
    };
    window.addEventListener("mousedown", onInteraction, { once: true });
    window.addEventListener("keydown", onInteraction, { once: true });
    window.addEventListener("mousemove", onInteraction, { once: true });
    const t = window.setTimeout(() => {
      if (cancelled) return;
      onEvent?.({ type: "step_idle", flowId, stepId: state.currentStepId });
      const cur = flow.steps.find((s) => s.id === state.currentStepId);
      cur?.prefetch?.(state.context).catch(() => {
        // prefetch errors are swallowed by design — they're advisory.
      });
    }, IDLE_MS);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("mousedown", onInteraction);
      window.removeEventListener("keydown", onInteraction);
      window.removeEventListener("mousemove", onInteraction);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.currentStepId]);

  const currentStep = React.useMemo(
    () =>
      flow.steps.find((s) => s.id === state.currentStepId) ?? flow.steps[0],
    [flow, state.currentStepId]
  );

  const updateContext = React.useCallback((patch: Partial<FlowContextBase>) => {
    setState((prev) => ({ ...prev, context: { ...prev.context, ...patch } }));
  }, []);

  const advance = React.useCallback(() => {
    setState((prev) => {
      const step = flow.steps.find((s) => s.id === prev.currentStepId);
      if (!step) return prev;
      if (step.validate) {
        const v = step.validate(prev.context);
        if (v === false || typeof v === "string") return prev;
      }
      let nextId: string | null;
      if (step.next) {
        nextId = step.next(prev.context);
      } else {
        const idx = flow.steps.findIndex((s) => s.id === step.id);
        nextId =
          idx >= 0 && idx < flow.steps.length - 1
            ? flow.steps[idx + 1].id
            : null;
      }
      onEvent?.({
        type: "step_exited",
        flowId,
        stepId: step.id,
        advancedTo: nextId,
      });
      if (nextId === null) {
        flow.onComplete(prev.context);
        clearState(flowId);
        onEvent?.({ type: "flow_completed", flowId });
        return prev;
      }
      stepStack.current.push(nextId);
      onEvent?.({ type: "step_entered", flowId, stepId: nextId });
      return { ...prev, currentStepId: nextId };
    });
  }, [flow, flowId, onEvent]);

  const back = React.useCallback(() => {
    if (stepStack.current.length <= 1) return;
    stepStack.current.pop();
    const prevId = stepStack.current[stepStack.current.length - 1];
    setState((prev) => {
      onEvent?.({
        type: "step_exited",
        flowId,
        stepId: prev.currentStepId,
        advancedTo: prevId,
      });
      onEvent?.({ type: "step_entered", flowId, stepId: prevId });
      return { ...prev, currentStepId: prevId };
    });
  }, [flowId, onEvent]);

  const abort = React.useCallback(() => {
    onEvent?.({ type: "flow_aborted", flowId, atStep: state.currentStepId });
    flow.onAbort?.(state.context);
    clearState(flowId);
  }, [flow, flowId, onEvent, state.context, state.currentStepId]);

  const value = React.useMemo<FlowContextValue<FlowContextBase>>(
    () => ({
      flow,
      step: currentStep,
      context: state.context,
      updateContext,
      advance,
      back,
      abort,
    }),
    [flow, currentStep, state.context, updateContext, advance, back, abort]
  );

  return React.createElement(FlowReactContext.Provider, { value }, children);
};

/**
 * Hook used inside step bricks. Returns the live flow, current step,
 * context, and the four navigation helpers.
 *
 * Bricks normally declare their props as `FlowStepProps<TCtx>` and let
 * <FlowShell /> pass them. `useFlowState` is here for advanced cases
 * (debugging tools, conditional sub-flows, analytics inside a brick).
 */
export function useFlowState<
  TCtx extends FlowContextBase = FlowContextBase,
>(): FlowContextValue<TCtx> {
  const ctx = React.useContext(FlowReactContext);
  if (!ctx) {
    throw new Error("useFlowState must be called inside <FlowProvider>");
  }
  return ctx as FlowContextValue<TCtx>;
}

/**
 * Default renderer for the current step's brick. Drop this inside a
 * <FlowProvider> and it picks up everything from context. Custom shells
 * can render the brick themselves via `useFlowState()` — this is the
 * convenience path for the standard case.
 */
export const FlowShell: React.FC = () => {
  const { step, context, updateContext, advance, back, abort } = useFlowState();
  return React.createElement(step.brick, {
    context,
    updateContext,
    advance,
    back,
    abort,
  });
};
