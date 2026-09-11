/**
 * Turning a list of tickers into a portfolio-overlay `StrategyJson`.
 *
 * PRD-26b slice 2. Lifted verbatim out of `bricks/overlay-picker.tsx`, which
 * had it inline and private, so the SECOND caller — a screen basket becoming a
 * portfolio (PRD-26b §2) — reuses it instead of forking a copy.
 *
 * That forking is not hypothetical: two screener backends exist in this repo
 * because the same thing was written twice. The overlay cards are the next
 * obvious candidate, so the shared thing is extracted before the second caller
 * is written, not after.
 *
 * BEHAVIOUR IS BYTE-UNCHANGED for `portfolio_mode`. Every branch, constant and
 * default below came across as-is; the only addition is
 * `overlayStrategyFromTickers`, a convenience for callers that have symbols
 * with no weights (a screen basket), which routes to the same builder.
 */

import type { Holding, OverlayKind, StrategyJson } from "@/lib/contracts";
import { OVERLAY_METADATA } from "@/lib/overlay-metadata";

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function yearsAgoIso(years: number = 5): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
}

/** Explicit weights when every holding has one, equal-weight otherwise. A
 *  screen basket always takes the equal-weight branch — it has no weights, and
 *  inventing them would be inventing a portfolio the user never stated. */
export function makeWeights(holdings: Holding[]): Record<string, number> {
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

export function buildOverlayStrategyJson(
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
    start_date: yearsAgoIso(lookbackYears),
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

/** A screen basket is symbols with no weights. Named separately so the call
 *  site reads as what it is rather than constructing fake `Holding`s inline. */
export function overlayStrategyFromTickers(
  overlay: OverlayKind,
  tickers: string[],
  lookbackYears: number,
): StrategyJson {
  return buildOverlayStrategyJson(
    overlay,
    tickers.map((ticker) => ({ ticker })),
    lookbackYears,
  );
}

/** `rebalance` is excluded wherever the caller has no weights (PRD-26b §2.3):
 *  it targets explicit weights, and equal-weight rebalance is `defensive`
 *  without the filter. Exported so the UI states the reason rather than
 *  silently hiding a card. */
export const OVERLAYS_NEEDING_WEIGHTS: OverlayKind[] = ["rebalance"];
