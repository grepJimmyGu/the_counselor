"use client";

/**
 * <OverlayPicker> — PRD-13b + PRD-13c brick.
 *
 * Step 3 of portfolio_mode. Shows six overlay cards grouped as Core
 * (Defensive / Rotation / Rebalance) and Advanced (Dual Momentum /
 * Defense-First / Stability Tilt). Advanced cards carry credibility
 * annotations: historical estimate, research source, expandable
 * "How it works" mechanic explanation.
 *
 * Picking a card materializes a StrategyJson with `inherited_universe`
 * + the right `portfolio_*_overlay` strategy_type and pushes it onto
 * the flow context for the next (Summary) step.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { OverlayKind, StrategyJson } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { StrategyCard } from "@/components/strategy-picker/strategy-card";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";
// PRD-26b slice 2 — shared with the screen-basket door; see
// `overlay-strategy-json.ts` for why it moved out of this file.
import { buildOverlayStrategyJson } from "../overlay-strategy-json";

type DateRange = "3Y" | "5Y" | "10Y";

const DATE_RANGE_YEARS: Record<DateRange, number> = { "3Y": 3, "5Y": 5, "10Y": 10 };

registerModeCopy("portfolio_mode", {
  overlay_title: "Pick an overlay",
  overlay_subtitle:
    "All six apply on top of your existing book — they don't change which names you hold (rotation moves between them).",
  overlay_continue: "Continue → Summary",
  overlay_advanced_header: "Advanced Overlays",
  overlay_basic_header: "Basic Overlays",
});

export function OverlayPicker({
  context,
  updateContext,
  advance,
  back,
}: FlowStepProps<PortfolioModeContext>) {
  const title = useFlowCopy("portfolio_mode", "overlay_title");
  const subtitle = useFlowCopy("portfolio_mode", "overlay_subtitle");
  const continueLabel = useFlowCopy("portfolio_mode", "overlay_continue");
  const coreHeaderLabel = useFlowCopy("portfolio_mode", "overlay_basic_header");
  const advancedHeaderLabel = useFlowCopy("portfolio_mode", "overlay_advanced_header");

  const [selected, setSelected] = React.useState<OverlayKind | undefined>(
    context.selectedOverlay,
  );
  const [dateRange, setDateRange] = React.useState<DateRange>("5Y");

  const holdings = context.holdings || [];

  const onPick = (overlay: OverlayKind) => {
    const meta = OVERLAY_METADATA[overlay];
    if (holdings.length < meta.minHoldings) return; // silently reject under-qualified
    setSelected(overlay);
    updateContext({
      selectedOverlay: overlay,
      strategyJson: buildOverlayStrategyJson(overlay, holdings, DATE_RANGE_YEARS[dateRange]),
    });
  };

  const onContinue = () => {
    if (!selected) return;
    advance();
  };

  // Rebuild strategyJson when date range changes while an overlay is
  // already selected (so the user can toggle dates without re-picking).
  React.useEffect(() => {
    if (selected) {
      updateContext({
        strategyJson: buildOverlayStrategyJson(selected, holdings, DATE_RANGE_YEARS[dateRange]),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange]);

  if (holdings.length === 0) {
    return (
      <section className="space-y-3" data-testid="overlay-picker-empty">
        <p className="text-sm text-red-600">
          No holdings supplied — go back to the upload step.
        </p>
      </section>
    );
  }

  let lastTier = "";

  const exampleTicker = holdings[0]?.ticker ?? "AAPL";
  const examplePrice = 180; // illustrative — actual prices come from price_bars

  return (
    <section className="space-y-6" data-testid="overlay-picker">
      <button
        type="button"
        onClick={back}
        className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        ← Back
      </button>
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {OVERLAY_DISPLAY_ORDER.map((overlay) => {
          const meta = OVERLAY_METADATA[overlay];
          const isSelected = selected === overlay;
          const showGroupHeader = meta.tier !== lastTier;
          lastTier = meta.tier;

          return (
            <React.Fragment key={overlay}>
              {showGroupHeader && (
                <div className="col-span-full mt-2 first:mt-0">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {meta.tier === "basic" ? coreHeaderLabel : advancedHeaderLabel}
                  </h2>
                </div>
              )}
              <StrategyCard
                meta={meta}
                ticker={exampleTicker}
                examplePrice={examplePrice}
                holdingsCount={holdings.length}
                isSelected={isSelected}
                isDisabled={holdings.length < meta.minHoldings}
                demo
                onSelect={() => onPick(overlay)}
              />
            </React.Fragment>
          );
        })}
      </div>

      {/* Date range — only shown after user selects an overlay */}
      {selected && (
        <div className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Backtest period
          </h2>
          <div className="flex gap-3">
            {(["3Y", "5Y", "10Y"] as const).map((range) => {
              const sel = dateRange === range;
              return (
                <button
                  key={range}
                  type="button"
                  onClick={() => setDateRange(range)}
                  aria-pressed={sel}
                  data-testid={`overlay-date-range-${range}`}
                  className={cn(
                    "cursor-pointer flex-1 rounded-xl border py-2 text-center font-semibold transition-all duration-150",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                    sel
                      ? "border-primary bg-primary/8 ring-1 ring-primary text-primary shadow-sm"
                      : "border-border hover:border-primary/40 hover:bg-muted/20",
                  )}
                >
                  {range}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <Button
          onClick={onContinue}
          disabled={!selected}
          data-testid="overlay-picker-continue"
        >
          {continueLabel}
        </Button>
      </div>
    </section>
  );
}
