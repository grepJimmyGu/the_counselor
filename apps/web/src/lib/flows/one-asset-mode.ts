/**
 * one-asset-mode — Sprint 2 Mode 1 refactor FlowDefinition.
 *
 * The second concrete flow on the PRD-13a runtime, after PRD-13b's
 * `portfolio_mode`. Closes the architectural gap §7 of the HANDOFF
 * flagged: the two Mode 1 secondary triggers (stock-page "⚡ Apply a
 * strategy" + Home picker "Pick an asset") now route through the
 * runtime instead of opening the legacy in-page <StrategyBuilderModal>.
 *
 * Triggers:
 *   - `stock_page/apply_strategy` — ticker comes via initialContext and
 *     pre-fills the summary's single-ticker field.
 *   - `home/pick_asset` (Home "Try out strategy template" card) — no
 *     ticker; the user picks the single ticker in the summary step.
 *
 * Steps:
 *   template-pick → summary → backtest → review → save
 *
 * There is no dedicated ticker step — the template is picked first, and
 * the single ticker is chosen in the summary (`singleTicker`). A ticker
 * seeded from a stock page flows through context into the summary prefill.
 *
 * The backtest / review / save bricks are mode-agnostic
 * (`flow-backtest.tsx`, `flow-review.tsx`, `flow-save.tsx`) — they read
 * their copy via `useFlowCopy(flow.id, key)` and we register the
 * `one_asset_mode` overrides below. Same pattern PRD-13b uses for
 * `portfolio_mode`.
 *
 * Importing this module has two side effects:
 *   1. registerFlow(OneAssetModeFlow) — adds the flow to the registry
 *   2. registerModeCopy("one_asset_mode", { … }) — every label this
 *      mode's bricks render. Idempotent via the getFlow() guard below.
 */

import type { FlowDefinition } from "./types";
import { getFlow, registerFlow } from "./registry";
import { registerModeCopy } from "./copy";
import { OneAssetTemplatePick } from "./bricks/one-asset-template-pick";
import { OneAssetSummary } from "./bricks/one-asset-summary";
import { FlowBacktest } from "./bricks/flow-backtest";
import { FlowReview } from "./bricks/flow-review";
import { FlowSave } from "./bricks/flow-save";
import type { OneAssetModeContext } from "./one-asset-mode-context";

registerModeCopy("one_asset_mode", {
  flow_name: "Apply a Strategy",

  // OneAssetSummary fallback when the picker advanced without a
  // template mapping. Sprint 2 PRD-16 (Custom Build) replaces this.
  summary_missing_template:
    "No template was selected. Go back to pick a strategy.",
  summary_missing_template_back: "← Back to template picker",

  // FlowBacktest
  backtest_title: "Running backtest",
  backtest_subtitle:
    "Computing how this strategy would have performed on the chosen ticker.",
  backtest_retry: "Retry",
  backtest_error: "Backtest failed. Try again.",

  // FlowReview
  review_title: "Backtest result",
  review_subtitle:
    "Past performance is not a guarantee of future results — this is a research tool, not investment advice.",
  review_save: "Save strategy →",

  // FlowSave
  save_title: "Save this strategy",
  save_subtitle:
    "Give it a name; we'll add it to your saved strategies and tag the ticker.",
  save_label: "Strategy name",
  save_placeholder: "Momentum on AAPL",
  save_signin: "Sign in to save this strategy.",
  save_error: "Couldn't save. Try again.",
  save_done: "Saved! Redirecting…",
});

export const OneAssetModeFlow: FlowDefinition<OneAssetModeContext> = {
  id: "one_asset_mode",
  name: "Apply a Strategy",
  triggers: [
    "stock_page/apply_strategy",
    "home/pick_asset",
  ],
  initialStepId: "template-pick",
  steps: [
    { id: "template-pick", brick: OneAssetTemplatePick },
    { id: "summary",       brick: OneAssetSummary },
    { id: "backtest",      brick: FlowBacktest },
    { id: "review",        brick: FlowReview },
    { id: "save",          brick: FlowSave, next: () => null },
  ],
  onComplete: (ctx) => {
    // Navigate to the saved-strategy detail page when a save succeeded;
    // otherwise back to the stock detail page (if we have a ticker) or
    // home. FlowSave only `advance()`s on a successful save, so on the
    // happy path savedSlug is always set.
    if (typeof window !== "undefined") {
      const slug = (ctx as OneAssetModeContext & { savedSlug?: string }).savedSlug;
      if (slug) {
        window.location.assign(`/strategies/${slug}`);
      } else if (ctx.ticker) {
        window.location.assign(`/stocks/${ctx.ticker}`);
      } else {
        window.location.assign("/");
      }
    }
  },
};

// Self-registration side-effect. Top-level for predictable ordering —
// the universal /flow/[flowId] shell + every trigger site
// side-effect-imports this module before calling startFlow, so the
// registry is populated before any provider looks the id up.
//
// Guard via getFlow() so multiple import sites (the flow shell route,
// the home picker, the stock detail page) don't trigger the "Flow
// already registered" throw. The runtime's duplicate-id check is for
// two *different* FlowDefinitions colliding on the same id, not for a
// single module legitimately being imported twice.
if (!getFlow(OneAssetModeFlow.id)) {
  registerFlow(OneAssetModeFlow);
}
