/**
 * portfolio-mode — PRD-13b FlowDefinition.
 *
 * The first concrete flow shipped on the PRD-13a runtime. Triggered from:
 *   - Home page "Upload portfolio" CTA (PRD-11 wires this; this file
 *     pre-registers the flow so PRD-11 only needs a one-line call)
 *   - Strategy Builders multi-ticker template universe picker
 *     ("Use my portfolio" option — wired in PRD-13b)
 *
 * Importing this module has two side effects:
 *   1. registerFlow(PortfolioModeFlow) — adds the flow to the registry
 *   2. registerModeCopy("portfolio_mode", { … }) — by transitive imports
 *      of each brick, which calls registerModeCopy at module load
 *
 * Both are idempotent — importing the module multiple times throws only
 * for registerFlow (registry rejects duplicates), so the conventional
 * import pattern at the universal /flow/[flowId] shell is:
 *   import "@/lib/flows/portfolio-mode";   // side-effect only
 *
 * Sprint 2 cleanup: when Mode 1 (One Asset) also migrates to the runtime,
 * SummaryStep / BacktestRunner / ResultViewer / SaveStrategy can be
 * extracted into mode-agnostic bricks; the portfolio-specific adapters
 * below collapse into thin wrappers around those.
 */

import type { FlowDefinition } from "./types";
import { getFlow, registerFlow } from "./registry";
import { registerModeCopy } from "./copy";
import { PortfolioUpload } from "./bricks/portfolio-upload";
import { PortfolioDiagnosis } from "./bricks/portfolio-diagnosis";
import { OverlayPicker } from "./bricks/overlay-picker";
import { PortfolioSummary } from "./bricks/portfolio-summary";
import { PortfolioBacktest } from "./bricks/portfolio-backtest";
import { PortfolioReview } from "./bricks/portfolio-review";
import { PortfolioSave } from "./bricks/portfolio-save";
import type { PortfolioModeContext } from "./portfolio-mode-context";

// Framework-level overrides that bricks reference via useFlowCopy. The
// individual brick modules also registerModeCopy() for their own keys
// (uploaded transitively when this file imports them above).
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
    { id: "summary",  brick: PortfolioSummary },
    { id: "backtest", brick: PortfolioBacktest },
    { id: "review",   brick: PortfolioReview },
    { id: "save",     brick: PortfolioSave, next: () => null },
  ],
  onComplete: (ctx) => {
    // Navigate to the saved-strategy detail page when a save succeeded;
    // otherwise back to home. (PortfolioSave only `advance()`s on a
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
