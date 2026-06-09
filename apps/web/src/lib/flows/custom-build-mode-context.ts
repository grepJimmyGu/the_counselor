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
import type {
  BacktestResult,
  SignalPrimitive,
  StrategyJson,
} from "@/lib/contracts";

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

/** PRD-16c — single tier in a multi-tier exit ladder. Mirrors backend
 *  `ExitTier`: trigger_pct signed (negative = stop, positive = TP);
 *  action 'sell_all' (close) or 'sell_fraction' (partial out + fraction
 *  required); optional label rendered in the dashboard. */
export interface ExitTier {
  trigger_pct: number;
  action: "sell_all" | "sell_fraction";
  fraction?: number;
  label?: string;
}

/** PRD-16c — bar resolution for active execution. 'daily' is the
 *  conventional default; '5min' / '15min' / '30min' / '60min' activate
 *  the intraday data + monitor cron paths. */
export type BarResolution = "daily" | "5min" | "15min" | "30min" | "60min";

export interface CustomBuildModeContext extends FlowContextBase {
  /** Single-symbol universe for v1. The composer renders a small
   *  picker; PRD-16b-3 extends this to a multi-symbol picker. */
  symbol: string | null;
  /** Ordered rule list. First rule has `logic_with_prior: null`; every
   *  subsequent rule has it set. */
  rules: BuildRule[];
  /** Whether the user enabled "Active execution". PRD-16b shipped this
   *  scaffold disabled; PRD-16c flips it live + reveals the
   *  bar-resolution picker + exit-ladder editor below. */
  active_execution_enabled: boolean;
  /** PRD-16c — bar resolution chosen for active execution. Ignored
   *  when `active_execution_enabled === false`. Default 'daily' matches
   *  the backend engine's default. */
  bar_resolution: BarResolution;
  /** PRD-16c — ordered multi-tier exit ladder. Empty list = use the
   *  single-stop / single-TP from `risk_management` instead. Validator
   *  on the backend enforces ≥1 stop + ascending order; the editor
   *  surfaces those constraints inline so the user never sees a
   *  backend 422. */
  exit_ladder: ExitTier[];

  // ── PRD-16 UX wire-up: transient flow fields ────────────────────────
  // Populated as the user advances through the chain.
  // Mirrors one_asset_mode / portfolio_mode conventions so the
  // mode-agnostic FlowBacktest / FlowReview / FlowSave bricks work.

  /** Synthesized StrategyJson after the user clicks "Run backtest →".
   *  FlowBacktest reads this to call the backtest endpoint. */
  strategyJson?: StrategyJson;
  /** Backtest API response. FlowReview renders from this. */
  backtestResult?: BacktestResult;
  /** Slug returned by the save endpoint. The flow's `onComplete` reads
   *  this to navigate to /strategies/{slug}. */
  savedSlug?: string;
}

export const INITIAL_CUSTOM_BUILD_CONTEXT: Omit<
  CustomBuildModeContext,
  "fromTrigger"
> = {
  symbol: null,
  rules: [],
  active_execution_enabled: false,
  bar_resolution: "daily",
  exit_ladder: [],
};
