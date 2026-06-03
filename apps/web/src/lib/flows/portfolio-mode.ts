/**
 * portfolio-mode — PRD-13b FlowDefinition.
 *
 * The first concrete flow shipped on the PRD-13a runtime. Triggered from:
 *   - Home page "Upload portfolio" CTA (PRD-11)
 *   - Strategy Builders multi-ticker template universe picker
 *     ("Use my portfolio" option)
 *
 * Importing this module has two side effects:
 *   1. registerFlow(PortfolioModeFlow) — adds the flow to the registry
 *   2. registerModeCopy("portfolio_mode", { … }) — for every label its
 *      bricks render. The mode-agnostic bricks (FlowBacktest / -Review /
 *      -Save) resolve their copy via `useFlowCopy(flow.id, key)`, so
 *      this file owns the portfolio-specific values for each of those
 *      keys — switching modes only changes the values, not the brick
 *      code.
 *
 * Sprint 2 (Mode 1 refactor / this PRD) generalised the backtest /
 * review / save bricks. The summary, upload, diagnose, and overlay
 * steps remain portfolio-specific.
 */

import type { FlowDefinition } from "./types";
import { getFlow, registerFlow } from "./registry";
import { registerModeCopy } from "./copy";
import { PortfolioUpload } from "./bricks/portfolio-upload";
import { PortfolioDiagnosis } from "./bricks/portfolio-diagnosis";
import { OverlayPicker } from "./bricks/overlay-picker";
import { PortfolioSummary } from "./bricks/portfolio-summary";
import type { PortfolioModeContext } from "./portfolio-mode-context";

// Mode-level copy for portfolio-specific bricks.
registerModeCopy("portfolio_mode", {
  flow_name: "Portfolio Overlay",
});

export const PortfolioModeFlow: FlowDefinition<PortfolioModeContext> = {
  id: "portfolio_mode",
  name: "Portfolio Overlay",
  triggers: [
    "home/upload_portfolio",
    "builders/multi_ticker_use_my_portfolio",
  ],
  initialStepId: "upload",
  steps: [
    { id: "upload",   brick: PortfolioUpload },
    { id: "diagnose", brick: PortfolioDiagnosis },
    { id: "overlay",  brick: OverlayPicker },
    { id: "summary",  brick: PortfolioSummary, next: () => null },
  ],
  onComplete: (ctx) => {
    // Summary navigates to /workspace, so onComplete is a no-op.
    // If the user somehow reaches this (e.g. direct URL), send home.
    if (typeof window !== "undefined") {
      window.location.assign("/");
    }
  },
};

// Self-registration side-effect. Top-level for predictable ordering —
// the universal /flow/[flowId] shell imports this file before mounting
// <FlowProvider>, so the registry is populated before any provider
// looks the id up.
//
// Guard via getFlow() instead of an unconditional registerFlow() so
// multiple import sites (the flow shell route + the strategy-builder
// modal both side-effect-import this module) don't trigger the
// "Flow already registered" throw. The runtime's duplicate-id check
// is for two *different* FlowDefinitions colliding on the same id,
// not for a single module legitimately being imported twice.
if (!getFlow(PortfolioModeFlow.id)) {
  registerFlow(PortfolioModeFlow);
}
