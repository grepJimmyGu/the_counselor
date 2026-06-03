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
import type { Holding, OverlayKind, StrategyJson } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { StrategyCard } from "@/components/strategy-picker/strategy-card";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

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

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function fiveYearsAgoIso(years: number = 5): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

function makeWeights(holdings: Holding[]): Record<string, number> {
  const explicit: Record<string, number> = {};
  let hasAll = true;
  for (const h of holdings) {
    if (h.weight !== undefined && h.weight > 0) {
      explicit[h.ticker] = h.weight;
    } else {
      hasAll = false;
    }
  }
  if (hasAll && holdings.length > 0) {
    const total = Object.values(explicit).reduce((a, b) => a + b, 0);
    if (total > 0) {
      const out: Record<string, number> = {};
      for (const [k, v] of Object.entries(explicit)) out[k] = v / total;
      return out;
    }
  }
  const equal = 1 / Math.max(1, holdings.length);
  const out: Record<string, number> = {};
  for (const h of holdings) out[h.ticker] = equal;
  return out;
}

function buildStrategyJson(
  overlay: OverlayKind,
  holdings: Holding[],
  lookbackYears: number,
): StrategyJson {
  const tickers = holdings.map((h) => h.ticker);
  const weights = makeWeights(holdings);
  const meta = OVERLAY_METADATA[overlay];

  // Overlays that use fixed target weights (all except rotation and dual_momentum)
  const usesEqualWeight = overlay === "rotation" || overlay === "dual_momentum";

  // Build rules based on overlay kind
  let rules: Array<Record<string, unknown>> = [];
  if (overlay === "rotation") {
    rules = [{ ranking_lookback_days: 126, top_n: Math.min(3, tickers.length) }];
  } else if (overlay === "dual_momentum") {
    rules = [{
      ranking_lookback_days: 126,
      top_n: Math.min(3, tickers.length),
      lookback_days: 252,
    }];
  } else if (overlay === "defensive") {
    rules = [{ lookback_days: 200, source: "close", indicator: "moving_average", operator: "gt" }];
  } else if (overlay === "defense_first") {
    rules = [{ lookback_days: 200, threshold: 0.5, value: 0.5, source: "close", indicator: "moving_average", operator: "gt" }];
  } else if (overlay === "stability_tilt") {
    rules = [{ lookback_days: 63, value: 0.25 }];
  }
  // rebalance: no rules

  return {
    strategy_name: meta.label + " Overlay",
    strategy_type: meta.strategyType,
    universe: tickers,
    inherited_universe: tickers,
    benchmark: "SPY",
    start_date: fiveYearsAgoIso(lookbackYears),
    end_date: todayIso(),
    initial_capital: 100_000,
    rebalance_frequency: "monthly",
    transaction_cost_bps: 5,
    slippage_bps: 5,
    rules: rules as StrategyJson["rules"],
    position_sizing: usesEqualWeight
      ? { method: "equal_weight" }
      : { method: "fixed_weight", weights },
    risk_management: {},
    cash_management: { hold_cash_when_no_signal: true, cash_yield_bps: 0 },
  };
}

export function OverlayPicker({
  context,
  updateContext,
  advance,
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
      strategyJson: buildStrategyJson(overlay, holdings, DATE_RANGE_YEARS[dateRange]),
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
        strategyJson: buildStrategyJson(selected, holdings, DATE_RANGE_YEARS[dateRange]),
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
