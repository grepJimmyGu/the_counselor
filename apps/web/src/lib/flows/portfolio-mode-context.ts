/**
 * PortfolioModeContext — typed flow context for the `portfolio_mode`
 * FlowDefinition (PRD-13b).
 *
 * Kept in its own file (separate from `portfolio-mode.ts`) so individual
 * bricks can import only the context shape without pulling the flow
 * registration side-effect. The flow definition + bricks both reference
 * this type; the flow file imports the bricks; the bricks import the
 * context. Import cycle avoided.
 */
import type { Holding, OverlayKind, PortfolioDiagnosis, StrategyJson } from "@/lib/contracts";
import type { FlowContextBase } from "./types";

export interface PortfolioModeContext extends FlowContextBase {
  /** Set on the upload step. Required by diagnose + every step downstream. */
  holdings?: Holding[];
  /** Set on the diagnose step once the API responds. */
  diagnosis?: PortfolioDiagnosis;
  /** Set on the overlay-picker step. */
  selectedOverlay?: OverlayKind;
  /** Set on the overlay-picker step — the constructed strategy ready to
   *  hand off to SummaryStep / BacktestRunner. */
  strategyJson?: StrategyJson;
  /** If launched from a multi-ticker template, carries the template id
   *  so the OverlayPicker can default to "rotation" when the user picked
   *  Sector Rotation, etc. */
  fromTemplate?: string;
}
