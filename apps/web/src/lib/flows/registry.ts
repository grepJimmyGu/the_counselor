/**
 * Flow registry.
 *
 * Each mode self-registers via a side-effect import:
 *
 *   // apps/web/src/lib/flows/portfolio-mode.ts (PRD-13b)
 *   registerFlow(portfolioFlow);
 *
 * Consumers look up by id via `getFlow(flowId)`.
 *
 * Sprint 1+ population:
 *   PRD-13b → portfolio_mode
 *   PRD-15  → thesis_mode
 *   PRD-16  → custom_build_mode
 */
import type { FlowContextBase, FlowDefinition } from "./types";

// The registry intentionally erases TCtx — it stores any FlowDefinition
// and trusts callers to cast on the way out. The PRD-13a contract calls
// for `<string, FlowDefinition<any>>`; `unknown` doesn't work here
// because FlowDefinition uses TCtx in both input and output positions.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFlow = FlowDefinition<any>;

const REGISTRY = new Map<string, AnyFlow>();

export function registerFlow<TCtx extends FlowContextBase>(
  flow: FlowDefinition<TCtx>
): void {
  if (REGISTRY.has(flow.id)) {
    throw new Error(`Flow already registered: ${flow.id}`);
  }
  REGISTRY.set(flow.id, flow);
}

export function getFlow<TCtx extends FlowContextBase = FlowContextBase>(
  flowId: string
): FlowDefinition<TCtx> | undefined {
  return REGISTRY.get(flowId) as FlowDefinition<TCtx> | undefined;
}

export function listFlows(): readonly AnyFlow[] {
  return Array.from(REGISTRY.values());
}

export const FLOW_REGISTRY = {
  register: registerFlow,
  get: getFlow,
  list: listFlows,
};

/**
 * Test-only escape hatch. Clears the registry so tests can reset state
 * between runs. Not exported via FLOW_REGISTRY because production code
 * has no reason to clear; only tests should touch this.
 */
export function __resetRegistryForTests(): void {
  REGISTRY.clear();
}
