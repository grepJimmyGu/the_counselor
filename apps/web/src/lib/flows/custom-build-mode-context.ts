/**
 * Custom Build mode — flow context type.
 *
 * The composer (PRD-16b-2) builds up a list of `BuildRule` entries as
 * the user drags primitives in from PRD-16a's catalog browser. Each
 * `BuildRule` mirrors the backend's `StrategyRule` shape for the
 * `custom_build` strategy_type (primitive_id + operator + threshold +
 * primitive_params + logic_with_prior).
 *
 * The context also tracks the user's chosen symbol (single-asset for
 * v1) and a snapshot of the catalog primitive that PRD-16b-3 will use
 * to render parameter editors on the canvas.
 */
import type { FlowContextBase } from "./types";
import type { SignalPrimitive } from "@/lib/contracts";

/** One row in the composer's rules list. Mirrors backend
 *  `StrategyRule` for `custom_build` strategy_type. */
export interface BuildRule {
  /** Unique id for React keys. NOT sent to backend; the backend keys
   *  rules by list order. */
  uid: string;
  /** Catalog primitive id (e.g. "rsi", "sma"). Matches a row in
   *  `SIGNAL_PRIMITIVES`. */
  primitive_id: string;
  /** Snapshot of the primitive at the moment it was added. Lets the
   *  canvas render parameter editors without re-fetching the catalog.
   *  Stale if the catalog changes mid-session — refresh via `fetch`. */
  primitive: SignalPrimitive;
  /** Runtime parameter overrides. Empty object = use primitive defaults. */
  primitive_params: Record<string, number | string | boolean>;
  /** Threshold comparison operator. Optional for primitives that
   *  themselves return 0/1 (e.g. donchian_breakout). */
  operator?: "gt" | "gte" | "lt" | "lte";
  /** Threshold value. None → primitive is treated as boolean. */
  threshold?: number;
  /** Fold operator joining THIS rule to the previous rule. First rule
   *  has `null`. The schema validator on the backend (PRD-16b-1)
   *  enforces this. */
  logic_with_prior: "AND" | "OR" | null;
}

export interface CustomBuildModeContext extends FlowContextBase {
  /** Single-symbol universe for v1. The composer renders a small
   *  picker; PRD-16b-3 extends this to a multi-symbol picker. */
  symbol: string | null;
  /** Ordered rule list. First rule has `logic_with_prior: null`; every
   *  subsequent rule has it set. */
  rules: BuildRule[];
  /** Whether the user enabled "Active execution" — toggle disabled in
   *  PRD-16b; wired up in PRD-16c. The schema scaffold is here so the
   *  composer renders the toggle as visible-but-disabled per pitfall B. */
  active_execution_enabled: boolean;
}

export const INITIAL_CUSTOM_BUILD_CONTEXT: Omit<
  CustomBuildModeContext,
  "fromTrigger"
> = {
  symbol: null,
  rules: [],
  active_execution_enabled: false,
};
