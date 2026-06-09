/**
 * custom_build_mode — PRD-16b Custom Build composer FlowDefinition.
 *
 * v1 ships a single step (`compose_signals`) backed by
 * `<CustomBuildCanvas>`. PRD-16b-3 extends the step chain with the
 * backtest + review steps (mode-agnostic `<FlowBacktest>` /
 * `<FlowReview>` from the existing strategy-builder pipeline).
 *
 * Triggers (per PRD spec):
 *   - `strategy_builders/custom_build_cta` — the "Custom Build" entry
 *     button on the Strategy Builders surface (PRD-16b-3 wires the CTA).
 *   - `stock_page/customize_template` — future PRD-15 hook for the
 *     stock-page "Customize" flow.
 *
 * Steps:
 *   compose_signals — the canvas. Terminal for v1 (next: () => null).
 *   PRD-16b-3 chain: → set_universe → set_risk → review_summary →
 *   backtest → review (mode-agnostic existing bricks).
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
import type { CustomBuildModeContext } from "./custom-build-mode-context";

registerModeCopy("custom_build_mode", {
  flow_name: "Custom Build",
  compose_title: "Compose your strategy",
  compose_subtitle:
    "Pick signal primitives, set their thresholds, and combine them with AND / OR. Suggestions on the right show how your combination maps to existing templates.",
  compose_empty: "Pick a primitive from the catalog to begin.",
  compose_run_backtest: "Run backtest →",
});

export const CustomBuildModeFlow: FlowDefinition<CustomBuildModeContext> = {
  id: "custom_build_mode",
  name: "Custom Build",
  triggers: [
    "strategy_builders/custom_build_cta",
    "stock_page/customize_template",
  ],
  initialStepId: "compose_signals",
  steps: [
    {
      id: "compose_signals",
      brick: CustomBuildCanvas,
      // v1 terminal — PRD-16b-3 extends the chain.
      next: () => null,
      validate: (ctx) => {
        if (ctx.rules.length === 0) return "Add at least one rule.";
        return true;
      },
    },
  ],
  onComplete: (ctx) => {
    // PRD-16b-3 wires the actual backtest path. For v1, completion is a
    // no-op (the user lands back on Strategy Builders) — but we log to
    // console in dev so the integration point is visible.
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.info(
        "[custom_build_mode] completed (v1 no-op):",
        ctx.rules.length,
        "rules",
      );
    }
  },
};

if (!getFlow(CustomBuildModeFlow.id)) {
  registerFlow(CustomBuildModeFlow);
}
