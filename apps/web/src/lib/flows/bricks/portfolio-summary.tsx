"use client";

/**
 * <PortfolioSummary> — PRD-13b adapter brick.
 *
 * Thin review-before-backtest surface for portfolio_mode. Shows the
 * constructed StrategyJson (the overlay + the user's holdings + their
 * normalized weights) and a single "Run backtest" CTA.
 *
 * Why not reuse strategy-builder/summary-step.tsx directly: that
 * component is wizard-flow specific (takes a `template` prop and emits
 * a SummaryStepConfig); portfolio_mode already has a fully formed
 * StrategyJson by this point — there's nothing to configure.
 * A future cleanup PRD will split summary-step into a generic brick
 * once Mode 1 also migrates to the flow runtime; until then this
 * adapter is the right minimum.
 */

import { Button } from "@/components/ui/button";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  summary_title: "Review and backtest",
  summary_subtitle:
    "We'll run this overlay against your holdings over the last 5 years.",
  summary_run: "Run backtest →",
});

export function PortfolioSummary({
  context,
  advance,
}: FlowStepProps<PortfolioModeContext>) {
  const title = useFlowCopy("portfolio_mode", "summary_title");
  const subtitle = useFlowCopy("portfolio_mode", "summary_subtitle");
  const runLabel = useFlowCopy("portfolio_mode", "summary_run");
  const whatLabel = useFlowCopy("portfolio_mode", "what_block_title");
  const whenInLabel = useFlowCopy("portfolio_mode", "when_in_block_title");
  const howMuchLabel = useFlowCopy("portfolio_mode", "how_much_block_title");
  const whenOutLabel = useFlowCopy("portfolio_mode", "when_out_block_title");

  const sj = context.strategyJson;
  if (!sj) {
    return (
      <section className="space-y-3" data-testid="portfolio-summary-empty">
        <p className="text-sm text-red-600">
          No overlay selected yet — go back to the overlay picker step.
        </p>
      </section>
    );
  }

  const targetWeights = sj.position_sizing.weights;
  const overlay = sj.strategy_type.replace("portfolio_", "").replace("_overlay", "");

  // WHEN IN / WHEN OUT descriptions are derived from the chosen overlay.
  const whenIn =
    sj.strategy_type === "portfolio_defensive_overlay"
      ? "Each holding is held only while above its 200-day moving average."
      : sj.strategy_type === "portfolio_rotation_overlay"
        ? "Each month, rotate into the top holdings by 6-month return."
        : "Re-weight to your target allocation on each rebalance date.";
  const whenOut =
    sj.strategy_type === "portfolio_defensive_overlay"
      ? "Holding moves to cash when its price breaks back below the MA."
      : sj.strategy_type === "portfolio_rotation_overlay"
        ? "Holdings outside the top-K go to cash until they re-enter."
        : "No exit logic — overlay restores weights mechanically.";

  return (
    <section className="space-y-6" data-testid="portfolio-summary">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {whatLabel}
          </h2>
          <p className="mt-2 text-sm font-medium capitalize">{overlay} overlay</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {sj.inherited_universe?.length || sj.universe.length} holdings • benchmark: {sj.benchmark}
          </p>
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {whenInLabel}
          </h2>
          <p className="mt-2 text-sm">{whenIn}</p>
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {howMuchLabel}
          </h2>
          {targetWeights ? (
            <ul className="mt-2 space-y-1 text-sm">
              {Object.entries(targetWeights)
                .sort((a, b) => b[1] - a[1])
                .map(([t, w]) => (
                  <li key={t} className="flex justify-between">
                    <span className="font-mono">{t}</span>
                    <span className="font-mono text-muted-foreground">
                      {(w * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              Equal-weight across {sj.inherited_universe?.length} holdings.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {whenOutLabel}
          </h2>
          <p className="mt-2 text-sm">{whenOut}</p>
        </div>
      </div>

      <div>
        <Button onClick={advance} data-testid="portfolio-summary-run">
          {runLabel}
        </Button>
      </div>
    </section>
  );
}
