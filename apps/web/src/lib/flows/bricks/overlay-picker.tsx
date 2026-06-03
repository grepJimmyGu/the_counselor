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
import type { Holding, OverlayKind, StrategyJson } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  overlay_title: "Pick an overlay",
  overlay_subtitle:
    "All six apply on top of your existing book — they don't change which names you hold (rotation moves between them).",
  overlay_defensive: "Defensive",
  overlay_rotation: "Rotation",
  overlay_rebalance: "Rebalance",
  overlay_dual_momentum: "Dual Momentum",
  overlay_defense_first: "Defense-First",
  overlay_stability_tilt: "Stability Tilt",
  overlay_defensive_desc:
    "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside.",
  overlay_rotation_desc:
    "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength.",
  overlay_rebalance_desc:
    "Periodically re-weights back to your target allocation. Best when you want discipline without timing.",
  overlay_dual_momentum_desc:
    "Invest in your strongest holdings, but only if they're going up. When everything's falling, moves to cash.",
  overlay_defense_first_desc:
    "Check the market's health first — when most holdings look weak, automatically reduce your exposure.",
  overlay_stability_tilt_desc:
    "Give larger positions to calm holdings and smaller ones to wild ones — same stocks, less drama.",
  overlay_continue: "Continue → Summary",
  overlay_advanced_header: "Advanced Overlays",
  overlay_core_header: "Core Overlays",
  overlay_estimate_label: "Estimate:",
  overlay_source_label: "Source:",
  overlay_how_it_works: "How it works",
  overlay_advanced_badge: "ADVANCED",
});

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function fiveYearsAgoIso(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 5);
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

function buildStrategyJson(overlay: OverlayKind, holdings: Holding[]): StrategyJson {
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
    start_date: fiveYearsAgoIso(),
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
  const coreHeaderLabel = useFlowCopy("portfolio_mode", "overlay_core_header");
  const advancedHeaderLabel = useFlowCopy("portfolio_mode", "overlay_advanced_header");
  const estimateLabel = useFlowCopy("portfolio_mode", "overlay_estimate_label");
  const sourceLabel = useFlowCopy("portfolio_mode", "overlay_source_label");
  const howItWorksLabel = useFlowCopy("portfolio_mode", "overlay_how_it_works");
  const advancedBadgeLabel = useFlowCopy("portfolio_mode", "overlay_advanced_badge");

  const [selected, setSelected] = React.useState<OverlayKind | undefined>(
    context.selectedOverlay,
  );

  const holdings = context.holdings || [];

  const onPick = (overlay: OverlayKind) => {
    const meta = OVERLAY_METADATA[overlay];
    if (holdings.length < meta.minHoldings) return; // silently reject under-qualified
    setSelected(overlay);
    updateContext({
      selectedOverlay: overlay,
      strategyJson: buildStrategyJson(overlay, holdings),
    });
  };

  const onContinue = () => {
    if (!selected) return;
    advance();
  };

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

  return (
    <section className="space-y-6" data-testid="overlay-picker">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {OVERLAY_DISPLAY_ORDER.map((overlay) => {
          const meta = OVERLAY_METADATA[overlay];
          const isSelected = selected === overlay;
          const isAdvanced = meta.tier === "advanced";
          const insufficient = holdings.length < meta.minHoldings;
          const showGroupHeader = meta.tier !== lastTier;
          lastTier = meta.tier;

          return (
            <React.Fragment key={overlay}>
              {showGroupHeader && (
                <div className="col-span-full mt-2 first:mt-0">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {meta.tier === "core" ? coreHeaderLabel : advancedHeaderLabel}
                  </h2>
                </div>
              )}
              <button
                type="button"
                onClick={() => onPick(overlay)}
                aria-pressed={isSelected}
                disabled={insufficient}
                data-testid={`overlay-card-${overlay}`}
                className={[
                  "cursor-pointer rounded-xl border p-4 text-left transition-all duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  insufficient
                    ? "cursor-not-allowed border-muted/30 bg-muted/10 opacity-60"
                    : isSelected
                      ? "border-primary bg-primary/8 ring-1 ring-primary shadow-sm"
                      : "border-border hover:border-primary/40 hover:bg-muted/30",
                ].join(" ")}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    {meta.label}
                    {isAdvanced && (
                      <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                        {advancedBadgeLabel}
                      </span>
                    )}
                    {insufficient && (
                      <span className="ml-1.5 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
                        Needs {meta.minHoldings}+ holdings
                      </span>
                    )}
                  </span>
                  {isSelected && (
                    <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
                      Selected
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{meta.shortDesc}</p>

                {/* Credibility annotations for advanced overlays */}
                {isAdvanced && (
                  <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
                    <p className="text-[11px] text-muted-foreground">
                      <span className="font-medium">{estimateLabel} </span>
                      {meta.historicalEstimate}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      <span className="font-medium">{sourceLabel} </span>
                      {meta.researchSource}
                    </p>
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[11px] font-medium text-primary hover:underline">
                        {howItWorksLabel}
                      </summary>
                      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                        {meta.mechanicSummary}
                      </p>
                    </details>
                  </div>
                )}
              </button>
            </React.Fragment>
          );
        })}
      </div>

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
