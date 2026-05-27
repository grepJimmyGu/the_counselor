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
import { FlowBacktest } from "./bricks/flow-backtest";
import { FlowReview } from "./bricks/flow-review";
import { FlowSave } from "./bricks/flow-save";
import type { PortfolioModeContext } from "./portfolio-mode-context";

// Mode-level copy. Bricks that own their own labels still
// registerModeCopy at module load (upload / diagnose / overlay /
// summary); the keys below are the ones the mode-agnostic
// FlowBacktest / FlowReview / FlowSave bricks read.
registerModeCopy("portfolio_mode", {
  flow_name: "Portfolio Overlay",
  // FlowBacktest
  backtest_title: "Running backtest",
  backtest_subtitle:
    "Computing the overlay's historical performance on your book.",
  backtest_retry: "Retry",
  backtest_error: "Backtest failed. Try again.",
  // FlowReview
  review_title: "Backtest result",
  review_subtitle:
    "Past performance is not a guarantee of future results — this is a research tool, not investment advice.",
  review_save: "Save strategy →",
  // FlowSave
  save_title: "Save this overlay",
  save_subtitle: "Give it a name; we'll add it to your saved strategies.",
  save_label: "Strategy name",
  save_placeholder: "Defensive overlay on my book",
  save_signin: "Sign in to save this strategy.",
  save_error: "Couldn't save. Try again.",
  save_done: "Saved! Redirecting…",
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
    { id: "summary",  brick: PortfolioSummary },
    { id: "backtest", brick: FlowBacktest },
    { id: "review",   brick: FlowReview },
    { id: "save",     brick: FlowSave, next: () => null },
  ],
  onComplete: (ctx) => {
    // Navigate to the saved-strategy detail page when a save succeeded;
    // otherwise back to home. (FlowSave only `advance()`s on a
    // successful save, so savedSlug is always set on this path.)
    if (typeof window !== "undefined") {
      const slug = (ctx as PortfolioModeContext & { savedSlug?: string }).savedSlug;
      if (slug) {
        window.location.assign(`/strategies/${slug}`);
      } else {
        window.location.assign("/");
      }
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
