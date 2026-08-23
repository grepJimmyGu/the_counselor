"use client";

/**
 * PRD-26 — promote a screen into a backtestable strategy.
 *
 * A standing-universe screen currently dead-ends: you can save/track it, but
 * there's no route to a validated, saveable strategy. Promote opens that route
 * and adds the two things a screen can't express on its own:
 *
 *   1. **Seeded parameters** — the best-matching KB template's entry/exit
 *      thresholds for the primitives the screen already uses
 *      (`matchSignalCombosToTemplates`, unchanged).
 *   2. **A calculated exit** — most primitives cannot express one at all, so
 *      the default exit is volatility-scaled: a stop/target ladder derived from
 *      `natr` (ATR as a percent of price, so no price lookup is needed) times
 *      the KB's multiples, clamped to a sane band.
 *
 * When the ladder CANNOT be calculated (no natr series for the symbol), we
 * return null and the caller must ask the user for an exit — we never
 * fabricate one silently.
 *
 * Everything downstream already ships: setting `context.strategyJson` and
 * advancing lands on the existing backtest → review → save chain.
 */

import { matchSignalCombosToTemplates, previewSignalPrimitive } from "@/lib/api";
import type {
  ExitLadderDefaults,
  ExitTier,
  StrategyJson,
  TemplateMatch,
} from "@/lib/contracts";

import type { BuildRule, CustomBuildModeContext } from "./custom-build-mode-context";
import {
  applyTemplateThresholdsToRules,
  buildCustomBuildStrategyJson,
} from "./custom-build-strategy-json";

/** Mirrors the KB's DEFAULT_EXIT_LADDER so a promote still works if an older
 *  backend omits the field. Kept in sync with
 *  apps/api/app/data/template_signal_metadata.py. */
export const FALLBACK_LADDER_DEFAULTS: ExitLadderDefaults = {
  atr_period: 14,
  stop_atr_multiple: 2.0,
  target_atr_multiples: [3.0, 5.0],
  target_fractions: [0.5, 1.0],
  stop_pct_clamp: [-15.0, -4.0],
  target_pct_clamp: [6.0, 60.0],
};

export interface PromoteDraft {
  symbol: string;
  strategyJson: StrategyJson;
  rules: BuildRule[];
  /** Which KB template seeded the thresholds (null = nothing matched). */
  seededFromTemplate: string | null;
  similarity: number | null;
  /** primitive_id → the thresholds applied, for display. */
  seededThresholds: Record<string, Record<string, number | string>>;
  /** Picks the KB has no exit for — surface these. */
  entryOnlyPrimitives: string[];
  /** null when it could not be calculated — ask the user instead. */
  exitLadder: ExitTier[] | null;
  /** The natr reading the ladder came from, for display (percent). */
  natrPct: number | null;
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(Math.max(value, lo), hi);
}

/** Latest non-null value of a preview series. */
function latestValue(series: Array<{ value: number | null }>): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    const v = series[i]?.value;
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

/**
 * Turn a percent-ATR reading into a stop/target ladder.
 *
 * Pure so the arithmetic is testable without the network. `natrPct` is ATR as
 * a percent of price (the `natr` primitive is literally `100 * atr / close`).
 *
 * UNITS — the bug this function shipped with, and why the /100 is load-bearing.
 * `trigger_pct` is a FRACTION everywhere it is consumed:
 *
 *   - `exit_ladder.py` compares it to `(close - entry) / entry`
 *   - `ExitTier`'s own docstring says "-0.10 = -10% stop"
 *   - `<ExitLadderEditor>` renders `trigger_pct * 100` and stores `input / 100`
 *
 * This function used to return the percent number unconverted, so a promoted
 * screen with 3% ATR got a stop at `-6.0` — read by the evaluator as -600%.
 * Every tier was unreachable: the stop needed the stock at -$500 from a $100
 * entry. Nothing errored, no test failed, and the backtest of such a strategy
 * silently ran with no exits at all.
 *
 * The KB's clamps ARE authored in percent (`stop_pct_clamp: [-15, -4]`), which
 * is where the confusion came from — so clamp in percent, then convert once,
 * here, at the boundary.
 */
const PCT_TO_FRACTION = 100;

export function ladderFromNatr(
  natrPct: number,
  defaults: ExitLadderDefaults = FALLBACK_LADDER_DEFAULTS,
): ExitTier[] | null {
  if (!Number.isFinite(natrPct) || natrPct <= 0) return null;

  const [stopLo, stopHi] = defaults.stop_pct_clamp;
  const [tgtLo, tgtHi] = defaults.target_pct_clamp;

  // Round in PERCENT space (2dp = 0.01% granularity) before converting, so a
  // -6.00% stop lands on exactly -0.06 rather than a float with a tail.
  const asFraction = (pct: number): number =>
    Number((Number(pct.toFixed(2)) / PCT_TO_FRACTION).toFixed(6));

  const tiers: ExitTier[] = [
    {
      trigger_pct: asFraction(
        clamp(-(defaults.stop_atr_multiple * natrPct), stopLo, stopHi),
      ),
      action: "sell_all",
      label: `Stop · ${defaults.stop_atr_multiple}x ATR`,
    },
  ];

  defaults.target_atr_multiples.forEach((multiple, i) => {
    const fraction = defaults.target_fractions[i];
    if (fraction === undefined) return;
    const isLast = fraction >= 1.0;
    tiers.push({
      trigger_pct: asFraction(clamp(multiple * natrPct, tgtLo, tgtHi)),
      action: isLast ? "sell_all" : "sell_fraction",
      ...(isLast ? {} : { fraction }),
      label: `Target ${i + 1} · ${multiple}x ATR`,
    });
  });

  return tiers;
}

/** Fetch the symbol's percent-ATR. Returns null on any failure — the caller
 *  degrades to "no calculated exit" rather than guessing. */
export async function fetchNatrPct(
  symbol: string,
  period: number,
): Promise<number | null> {
  try {
    const preview = await previewSignalPrimitive("natr", {
      symbol,
      days: 60,
      paramOverrides: { period },
    });
    return latestValue(preview.series);
  } catch {
    return null;
  }
}

/**
 * Build the promote draft for `symbol` from the screen's composed rules.
 *
 * Two network calls, both to existing endpoints: the KB match, and the natr
 * preview. Neither is required for the draft to exist — a failed match yields
 * an unseeded draft, a failed natr yields `exitLadder: null`.
 */
export async function buildPromoteDraft(
  context: CustomBuildModeContext,
  symbol: string,
): Promise<PromoteDraft> {
  const primitiveIds = context.rules.map((r) => r.primitive_id).filter(Boolean);

  let match: TemplateMatch | null = null;
  try {
    const resp = await matchSignalCombosToTemplates({
      primitive_ids: primitiveIds,
      top_n: 1,
    });
    match = resp.matches[0] ?? null;
  } catch {
    match = null;
  }

  const seededThresholds = match?.thresholds_for_user_primitives ?? {};
  const ladderDefaults = match?.exit_ladder_defaults ?? FALLBACK_LADDER_DEFAULTS;

  const rules = Object.keys(seededThresholds).length
    ? applyTemplateThresholdsToRules(context.rules, seededThresholds)
    : context.rules;

  const natrPct = await fetchNatrPct(symbol, ladderDefaults.atr_period);
  const exitLadder = natrPct === null ? null : ladderFromNatr(natrPct, ladderDefaults);

  // Build against the seeded rules, then attach the ladder directly. Going
  // through `context.active_execution_enabled` would flip the strategy into
  // active-execution semantics, which is a different feature.
  const strategyJson = buildCustomBuildStrategyJson(
    { ...context, rules },
    { symbol, strategy_name: `${symbol} — promoted from screen` },
  ) as StrategyJson;

  if (exitLadder) {
    strategyJson.risk_management = {
      ...(strategyJson.risk_management ?? {}),
      exit_ladder: exitLadder,
    };
  }

  return {
    symbol,
    strategyJson,
    rules,
    seededFromTemplate: match?.template_id ?? null,
    similarity: match?.similarity ?? null,
    seededThresholds,
    entryOnlyPrimitives: match?.entry_only_primitives ?? [],
    exitLadder,
    natrPct,
  };
}
