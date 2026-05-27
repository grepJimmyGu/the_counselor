"use client";

/**
 * <OverlayPicker> — PRD-13b brick.
 *
 * Step 3 of portfolio_mode. Shows three overlay cards (Defensive /
 * Rotation / Rebalance) ranked by the diagnose endpoint's
 * `recommended_overlays`. Each card carries NEUTRAL copy in Sprint 1 —
 * the live mini-backtest "tease" is deferred to Sprint 2 (per PRD
 * §"Backtest tease — DEFERRED").
 *
 * Picking a card materializes a StrategyJson with `inherited_universe`
 * + the right `portfolio_*_overlay` strategy_type and pushes it onto
 * the flow context for the next (Summary) step.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import type { Holding, OverlayKind, StrategyJson } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  overlay_title: "Pick an overlay",
  overlay_subtitle:
    "All three apply on top of your existing book — they don't change which names you hold (rotation moves between them).",
  overlay_defensive: "Defensive",
  overlay_rotation: "Rotation",
  overlay_rebalance: "Rebalance",
  overlay_defensive_desc:
    "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside.",
  overlay_rotation_desc:
    "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength.",
  overlay_rebalance_desc:
    "Periodically re-weights back to your target allocation. Best when you want discipline without timing.",
  overlay_continue: "Continue → Summary",
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
  // If all holdings have explicit weights, use them; otherwise equal-weight.
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
    // Normalize to sum=1 if user input doesn't already.
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
  const strategyType =
    overlay === "defensive"
      ? "portfolio_defensive_overlay"
      : overlay === "rotation"
        ? "portfolio_rotation_overlay"
        : "portfolio_rebalance_overlay";
  // Rotation uses equal_weight + a top-K rule; defensive/rebalance use the
  // user's target weights via fixed_weight.
  const isRotation = overlay === "rotation";
  return {
    strategy_name: `Portfolio ${overlay} overlay`,
    strategy_type: strategyType,
    universe: tickers,
    inherited_universe: tickers,
    benchmark: "SPY",
    start_date: fiveYearsAgoIso(),
    end_date: todayIso(),
    initial_capital: 100_000,
    rebalance_frequency: "monthly",
    transaction_cost_bps: 5,
    slippage_bps: 5,
    rules: isRotation
      ? [{ ranking_lookback_days: 126, top_n: Math.min(3, tickers.length) }]
      : overlay === "defensive"
        ? [{ lookback_days: 200, source: "close", indicator: "moving_average", operator: "gt" }]
        : [],
    position_sizing: isRotation
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
  const defensiveLabel = useFlowCopy("portfolio_mode", "overlay_defensive");
  const rotationLabel = useFlowCopy("portfolio_mode", "overlay_rotation");
  const rebalanceLabel = useFlowCopy("portfolio_mode", "overlay_rebalance");
  const defensiveDesc = useFlowCopy("portfolio_mode", "overlay_defensive_desc");
  const rotationDesc = useFlowCopy("portfolio_mode", "overlay_rotation_desc");
  const rebalanceDesc = useFlowCopy("portfolio_mode", "overlay_rebalance_desc");

  const overlayCopy: Record<OverlayKind, { label: string; desc: string }> = {
    defensive: { label: defensiveLabel, desc: defensiveDesc },
    rotation: { label: rotationLabel, desc: rotationDesc },
    rebalance: { label: rebalanceLabel, desc: rebalanceDesc },
  };

  const [selected, setSelected] = React.useState<OverlayKind | undefined>(
    context.selectedOverlay,
  );

  // Re-derive ordering: respect any backend `recommended_overlays` ordering
  // we have stashed in context, falling back to the canonical 3-card order.
  // (Diagnosis brick stores diagnosis but not recommendations; rather than
  // thread them through context, the PRD's Sprint 1 OverlayPicker uses a
  // fixed ordering — recommendations are a Sprint 2 polish.)
  const orderedOverlays: OverlayKind[] = ["defensive", "rotation", "rebalance"];

  const holdings = context.holdings || [];

  const onPick = (overlay: OverlayKind) => {
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

  return (
    <section className="space-y-6" data-testid="overlay-picker">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-3">
        {orderedOverlays.map((overlay) => {
          const { label, desc } = overlayCopy[overlay];
          const isSelected = selected === overlay;
          return (
            <button
              key={overlay}
              type="button"
              onClick={() => onPick(overlay)}
              aria-pressed={isSelected}
              data-testid={`overlay-card-${overlay}`}
              className={[
                "cursor-pointer rounded-xl border p-4 text-left transition-all duration-150",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                isSelected
                  ? "border-primary bg-primary/8 ring-1 ring-primary shadow-sm"
                  : "border-border hover:border-primary/40 hover:bg-muted/30",
              ].join(" ")}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{label}</span>
                {isSelected ? (
                  <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
                    Selected
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{desc}</p>
            </button>
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
