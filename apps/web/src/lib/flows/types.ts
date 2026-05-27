/**
 * Flow runtime — type contracts.
 *
 * Every Sprint 1+ entry mode (Portfolio, Thesis, Custom Build, etc.) is a
 * `FlowDefinition` object satisfying these types. The runtime in
 * `./runtime.ts` consumes the definition; UI surfaces consume it via
 * `startFlow(flowId, …)`.
 */
import type { ComponentType } from "react";

/**
 * Bag of state a flow accumulates as the user progresses through steps.
 * Each mode extends this with its own fields (declared in the mode's
 * FlowDefinition). The runtime is generic over TCtx so mode authors get
 * type-safe `context` access inside bricks.
 */
export interface FlowContextBase {
  /**
   * Identifier of the UI surface that launched the flow.
   * Format: `"<surface>/<action>"` — e.g. `"home/upload_portfolio"`,
   * `"builders/multi_ticker"`, `"stock_page/apply_strategy"`.
   * Used for analytics and surface-specific copy variants.
   */
  fromTrigger: string;
}

export interface FlowStepProps<TCtx extends FlowContextBase = FlowContextBase> {
  context: TCtx;
  updateContext: (patch: Partial<TCtx>) => void;
  advance: () => void;
  back: () => void;
  abort: () => void;
}

export interface FlowStep<TCtx extends FlowContextBase = FlowContextBase> {
  id: string;
  brick: ComponentType<FlowStepProps<TCtx>>;
  /**
   * Optional validator. Returns `true` to allow advance, `false` to block,
   * or a string error message (which the brick is responsible for
   * surfacing to the user).
   */
  validate?: (context: TCtx) => boolean | string;
  /**
   * Optional next-step predicate. Returns the next step id, or `null` to
   * mark this step terminal. Defaults to the next step in the `steps`
   * array.
   */
  next?: (context: TCtx) => string | null;
  /**
   * Optional idle-prefetch hook. Called after the step has been rendered
   * for ~300ms without user interaction. Use to warm up the next step's
   * API calls.
   */
  prefetch?: (context: TCtx) => Promise<void>;
}

export interface FlowDefinition<TCtx extends FlowContextBase = FlowContextBase> {
  id: string;
  name: string;
  /** Documented entry points (format: `"<surface>/<action>"`). */
  triggers: string[];
  steps: FlowStep<TCtx>[];
  initialStepId: string;
  /**
   * Called when the user completes the terminal step. Use to navigate to
   * a result page, save state, fire analytics, etc.
   */
  onComplete: (context: TCtx) => void;
  /**
   * Called when the user aborts the flow. Use to clean up partial state
   * or fire abandonment analytics.
   */
  onAbort?: (context: TCtx) => void;
}

/**
 * Emitted by the runtime on every step transition. Subscribe via
 * `<FlowProvider onEvent={…}>`. A downstream PRD wires this to PostHog.
 */
export type FlowEvent =
  | { type: "flow_started"; flowId: string; trigger: string }
  | { type: "step_entered"; flowId: string; stepId: string }
  | { type: "step_exited"; flowId: string; stepId: string; advancedTo: string | null }
  | { type: "step_idle"; flowId: string; stepId: string }
  | { type: "flow_completed"; flowId: string }
  | { type: "flow_aborted"; flowId: string; atStep: string };
