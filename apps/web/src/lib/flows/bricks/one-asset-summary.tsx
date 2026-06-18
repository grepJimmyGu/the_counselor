"use client";

/**
 * <OneAssetSummary> — Mode 1's review-before-backtest step.
 *
 * Wraps the existing `<SummaryStep>` (the 4-block "WHAT / WHEN IN /
 * HOW MUCH / WHEN OUT" UI from `components/strategy-builder/summary-step.tsx`)
 * and adapts the result into `context.strategyJson`. The summary
 * component is the canonical Sprint 1 surface for configuring a
 * single-ticker backtest, and was deliberately built ticker-aware
 * (`initialTickers` prop). Reusing it is the four-principles "don't
 * fork the wizard" path — we adapt, we don't replace.
 *
 * On submit:
 *   1. Build the StrategyJson from template + the user's tickers /
 *      risk / capital / cost-bps choices (mirrors
 *      strategy-builder-modal.tsx's `runBacktest` template-path).
 *   2. Apply the risk preset to mutate position_sizing + risk_management
 *      per `risk_control_prompt.md`'s mapping table.
 *   3. Drop the StrategyJson into context and `advance()` — the
 *      mode-agnostic <FlowBacktest> picks it up.
 */

import * as React from "react";
import {
  SummaryStep,
  type SummaryStepConfig,
} from "@/components/strategy-builder/summary-step";
import { applyRiskLevel } from "@/lib/strategy-picker/risk-presets";
import type { ResearchTemplate, StrategyJson } from "@/lib/contracts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import type { OneAssetModeContext } from "../one-asset-mode-context";

type DateRange = "3Y" | "5Y" | "10Y";

const DATE_RANGE_YEARS: Record<DateRange, number> = { "3Y": 3, "5Y": 5, "10Y": 10 };

function startDateForLookback(years: number): string {
  const now = new Date();
  return new Date(now.getFullYear() - years, now.getMonth(), now.getDate())
    .toISOString()
    .split("T")[0];
}

function endDateToday(): string {
  return new Date().toISOString().split("T")[0];
}

/**
 * Mirror of strategy-builder-modal.tsx's `runBacktest` template-path
 * (the `activeConfig && selectedTemplate` branch). Keeping this small
 * and local — Sprint 3 should consolidate it into a shared helper once
 * the legacy modal is deleted.
 */
function buildStrategyFromConfig(
  template: ResearchTemplate,
  config: SummaryStepConfig,
  strategyName: string,
  lookbackYears: number,
): StrategyJson {
  const tickerList = config.tickers
    .split(/[,\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  const weights =
    config.weightMode === "custom" && Object.keys(config.customWeights).length > 0
      ? Object.fromEntries(
          Object.entries(config.customWeights).map(([k, v]) => [k, v / 100]),
        )
      : undefined;
  const base: StrategyJson = {
    ...template.strategy,
    strategy_name: strategyName,
    universe: tickerList.length > 0 ? tickerList : template.defaultTickers,
    start_date: startDateForLookback(lookbackYears),
    end_date: endDateToday(),
    initial_capital: config.capital,
    transaction_cost_bps: config.costEnabled ? config.costBps : 0,
    slippage_bps: config.costEnabled ? config.costBps : 0,
    position_sizing: weights
      ? { method: "fixed_weight", weights }
      : { ...template.strategy.position_sizing },
  };
  return applyRiskLevel(base, config.riskPreset);
}

function autoName(template: ResearchTemplate, tickers: string): string {
  const list = tickers.split(/[,\s]+/).filter(Boolean);
  const suffix =
    list.length === 0
      ? template.defaultTickers.slice(0, 2).join(", ")
      : list.length <= 3
        ? list.join(", ")
        : `${list.slice(0, 2).join(", ")} +${list.length - 2}`;
  return `${template.name} — ${suffix}`;
}

export function OneAssetSummary({
  context,
  updateContext,
  advance,
  back,
}: FlowStepProps<OneAssetModeContext>) {
  const missingTemplateMsg = useFlowCopy(
    "one_asset_mode",
    "summary_missing_template",
  );
  const missingTemplateBack = useFlowCopy(
    "one_asset_mode",
    "summary_missing_template_back",
  );

  if (!context.template) {
    // User landed here via the "no template mapped" fallback in the
    // template-pick step. The legacy modal would dead-end with a blank
    // screen; we offer an explicit back-to-picker button instead.
    return (
      <section className="space-y-3" data-testid="one-asset-summary-empty">
        <p className="text-sm text-red-600">{missingTemplateMsg}</p>
        <Button
          variant="outline"
          onClick={back}
          data-testid="one-asset-summary-back"
        >
          {missingTemplateBack}
        </Button>
      </section>
    );
  }

  const template = context.template;
  // Single-asset mode: prefill exactly one ticker — the page's ticker (when
  // entered from a stock page), or the template's first default — never the
  // multi-name default list.
  const initialTickers = context.ticker ?? template.defaultTickers[0] ?? "";
  const initialRiskPreset = context.riskPreset ?? "medium";
  const [dateRange, setDateRange] = React.useState<DateRange>("5Y");

  const handleContinue = React.useCallback(
    (config: SummaryStepConfig) => {
      const strategyName = autoName(template, config.tickers);
      const strategyJson = buildStrategyFromConfig(
        template, config, strategyName, DATE_RANGE_YEARS[dateRange],
      );
      updateContext({ strategyJson });
      advance();
    },
    [template, updateContext, advance, dateRange],
  );

  return (
    <section data-testid="one-asset-summary" data-ticker={context.ticker}>
      {/* Date range toggle — matches legacy StrategyBuilderModal pattern */}
      <div className="mb-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Backtest period
        </h2>
        <div className="flex gap-3">
          {(["3Y", "5Y", "10Y"] as const).map((range) => {
            const selected = dateRange === range;
            return (
              <button
                key={range}
                type="button"
                onClick={() => setDateRange(range)}
                aria-pressed={selected}
                data-testid={`date-range-${range}`}
                className={cn(
                  "cursor-pointer flex-1 rounded-xl border py-3 text-center font-semibold transition-all duration-150",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  selected
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

      <SummaryStep
        template={template}
        initialRiskPreset={initialRiskPreset}
        initialTickers={initialTickers}
        singleTicker
        onContinue={handleContinue}
      />
    </section>
  );
}
