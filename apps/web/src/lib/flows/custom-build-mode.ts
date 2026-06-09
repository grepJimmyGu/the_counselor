/**
 * custom_build_mode — PRD-16b Custom Build composer FlowDefinition.
 *
 * Chain (PRD-16 UX wire-up): compose_signals → backtest → review → save.
 * The compose_signals step's canvas brick builds the StrategyJson when
 * the user clicks "Run backtest →"; the chain hands off to the
 * mode-agnostic FlowBacktest / FlowReview / FlowSave bricks the way
 * one_asset_mode and portfolio_mode do.
 *
 * Triggers:
 *   - `home/custom_build` — Home picker's third tile (PRD-16 wire-up).
 *   - `strategy_builders/custom_build_cta` — Strategy Builders surface.
 *   - `stock_page/customize_template` — future PRD-15 hook.
 *
 * Importing this module has two side effects:
 *   1. registerFlow(CustomBuildModeFlow)
 *   2. registerModeCopy("custom_build_mode", { … })
 * Both guarded against double-registration via getFlow().
 */

import type { FlowDefinition } from "./types";
import { getFlow, registerFlow } from "./registry";
import { registerModeCopy } from "./copy";
import { CustomBuildCanvas } from "./bricks/custom-build-canvas";
import { FlowBacktest } from "./bricks/flow-backtest";
import { FlowReview } from "./bricks/flow-review";
import { FlowSave } from "./bricks/flow-save";
import {
  INITIAL_CUSTOM_BUILD_CONTEXT,
  type CustomBuildModeContext,
} from "./custom-build-mode-context";

registerModeCopy("custom_build_mode", {
  flow_name: "Custom Build",
  compose_title: "Compose your strategy",
  compose_subtitle:
    "Pick signal primitives, set their thresholds, and combine them with AND / OR. Suggestions on the right show how your combination maps to existing templates.",
  compose_empty: "Pick a primitive from the catalog to begin.",
  compose_run_backtest: "Run backtest →",
  // FlowBacktest copy keys (mode-agnostic brick).
  backtest_title: "Running backtest",
  backtest_subtitle:
    "Computing how your custom strategy would have performed on the chosen symbol.",
  backtest_retry: "Retry",
  backtest_error: "Backtest failed. Try again.",
  // FlowReview copy keys.
  review_title: "Backtest result",
  review_subtitle:
    "Past performance is not a guarantee of future results — this is a research tool, not investment advice.",
  review_save: "Save strategy →",
  // FlowSave copy keys.
  save_title: "Save this strategy",
  save_subtitle:
    "Give it a name; we'll add it to your saved strategies. Active execution starts once it's saved.",
  save_label: "Strategy name",
  save_placeholder: "Custom momentum on NVDA",
  save_signin: "Sign in to save this strategy.",
  save_error: "Couldn't save. Try again.",
  save_done: "Saved! Redirecting…",
});

export const CustomBuildModeFlow: FlowDefinition<CustomBuildModeContext> = {
  id: "custom_build_mode",
  name: "Custom Build",
  triggers: [
    "home/custom_build",
    "strategy_builders/custom_build_cta",
    "stock_page/customize_template",
  ],
  // Defaults applied on BOTH the startFlow path (under the caller's
  // overrides) AND the direct-URL / refresh path (under
  // `fromTrigger: "direct"`). Without this, the canvas crashes on
  // direct URL access because `context.rules.map(...)` dereferences
  // undefined. See FlowDefinition.initialContext.
  initialContext: INITIAL_CUSTOM_BUILD_CONTEXT,
  // 3-pane composer (catalog + rules + suggestions) needs ~1440px to
  // render its internal grids without collisions. Default 768px
  // collapses the catalog's 180-px-sidebar + 2-column primitive grid
  // into overlapping narrow cards.
  shellMaxWidthClass: "max-w-[1440px]",
  initialStepId: "compose_signals",
  steps: [
    {
      id: "compose_signals",
      brick: CustomBuildCanvas,
      next: () => "backtest",
      validate: (ctx) => {
        if (ctx.rules.length === 0) return "Add at least one rule.";
        if (!ctx.symbol) return "Pick a backtest symbol.";
        // The canvas populates `strategyJson` when the user clicks
        // "Run backtest →". Block advance until it's set — guards
        // against runtime auto-advance on context restore from
        // sessionStorage without a fresh build.
        if (
          !(ctx as CustomBuildModeContext & { strategyJson?: unknown }).strategyJson
        )
          return "Click Run backtest to build the strategy.";
        return true;
      },
    },
    {
      id: "backtest",
      brick: FlowBacktest,
      next: () => "review",
    },
    {
      id: "review",
      brick: FlowReview,
      next: () => "save",
    },
    {
      id: "save",
      brick: FlowSave,
      next: () => null,
    },
  ],
  onComplete: (ctx) => {
    // Same pattern as one_asset_mode: FlowSave writes `savedSlug` on
    // success; we route to the public strategy detail page so the user
    // can immediately see their saved backtest (and, for active-
    // execution strategies, the live dashboard once 16c-3c is wired
    // into that surface).
    if (typeof window !== "undefined") {
      const slug = (ctx as CustomBuildModeContext & { savedSlug?: string })
        .savedSlug;
      if (slug) {
        window.location.assign(`/strategies/${slug}`);
      } else {
        window.location.assign("/");
      }
    }
  },
};

if (!getFlow(CustomBuildModeFlow.id)) {
  registerFlow(CustomBuildModeFlow);
}
