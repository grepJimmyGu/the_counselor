/**
 * OneAssetModeContext — typed flow context for the `one_asset_mode`
 * FlowDefinition (Sprint 2 / Mode 1 refactor PRD).
 *
 * Kept in its own file (separate from `one-asset-mode.ts`) so individual
 * bricks can import only the context shape without pulling the flow
 * registration side-effect. Matches the portfolio-mode-context.ts split.
 *
 * Mode 1 flow:
 *   ticker → template-pick → summary → backtest → review → save
 *
 * Each step writes its slot into context, the runtime persists context to
 * sessionStorage between steps, and the terminal save's `onComplete`
 * navigates to /strategies/<slug>.
 */
import type { BacktestResult, ResearchTemplate, StrategyJson } from "@/lib/contracts";
import type { RiskPreset } from "@/components/strategy-builder/summary-step";
import type { FlowContextBase } from "./types";

export interface OneAssetModeContext extends FlowContextBase {
  /** Set on the ticker step (or via initialContext when the user lands
   *  here from a stock detail page). Required by template-pick + every
   *  step downstream. */
  ticker?: string;
  /** Set on the template-pick step. The ResearchTemplate the user chose
   *  (via the existing 5-question wizard). */
  template?: ResearchTemplate;
  /** Set on the template-pick step — derived from the wizard's "dd"
   *  answer. Consumed by SummaryStep as `initialRiskPreset`. */
  riskPreset?: RiskPreset;
  /** Set on the summary step once the user clicks "Run backtest". The
   *  built strategy that gets handed to <FlowBacktest>. */
  strategyJson?: StrategyJson;
  /** Set on the backtest step once the API responds. */
  backtestResult?: BacktestResult;
  /** Set on the save step once /api/strategies/save succeeds. Drives
   *  the onComplete navigation to /strategies/<slug>. */
  savedSlug?: string;
}
