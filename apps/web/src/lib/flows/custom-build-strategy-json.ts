/**
 * PRD-16b-3 — converter from `CustomBuildModeContext` to `StrategyJson`.
 *
 * The canvas state (rules + symbol) is the user's editing surface; the
 * backend wants a fully-realized `StrategyJson` payload to backtest.
 * This module is the seam: takes the canvas state + a few defaults
 * (date range, capital, rebalance frequency) and produces a valid
 * `StrategyJson` with `strategy_type="custom_build"`.
 *
 * Backend validators (PRD-16b-1) enforce the contract:
 *   - First rule has no `logic_with_prior`.
 *   - Subsequent rules must have `logic_with_prior` set.
 *   - Every rule must have `primitive_id`.
 *   - At least one rule.
 *
 * This converter mirrors those constraints — `buildCustomBuildStrategyJson`
 * throws on the same errors so the canvas surfaces them before POST.
 */
import type {
  RebalanceFrequency,
  StrategyJson,
  StrategyRule,
} from "@/lib/contracts";
import type {
  BuildRule,
  CustomBuildModeContext,
} from "./custom-build-mode-context";

export interface CustomBuildBackoutOptions {
  /** Strategy display name. Defaults to a primitive-list summary. */
  strategy_name?: string;
  /** Universe — single symbol for v1. Falls back to `context.symbol`. */
  symbol?: string;
  /** Benchmark — defaults to SPY (matches existing template defaults). */
  benchmark?: string;
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  rebalance_frequency?: RebalanceFrequency;
}

function _defaultStart(): string {
  // ~3 years back; matches existing builder defaults.
  const d = new Date();
  d.setFullYear(d.getFullYear() - 3);
  return d.toISOString().slice(0, 10);
}

function _defaultEnd(): string {
  return new Date().toISOString().slice(0, 10);
}

function _toStrategyRule(rule: BuildRule): StrategyRule {
  const out: StrategyRule = {
    primitive_id: rule.primitive_id,
    operator: rule.operator,
    threshold: rule.threshold,
    logic_with_prior: rule.logic_with_prior,
  };
  // Only attach primitive_params if there are overrides — keeps the
  // payload compact and avoids round-tripping empty dicts through the
  // backend.
  if (Object.keys(rule.primitive_params).length > 0) {
    out.primitive_params = rule.primitive_params;
  }
  return out;
}

/** PRD-23b — the composed rules as the backend `rules` field for a screen
 *  scan/count/rank request body. Same mapping the backtest uses, so the
 *  screen filter matches the backtest evaluation. */
export function buildScreenRules(rules: BuildRule[]): StrategyRule[] {
  return rules.map(_toStrategyRule);
}

/**
 * PRD-16c live-tracking guard.
 *
 * A strategy is only live-trackable — i.e. it shows up in
 * /account/strategies, renders the live dashboard, and is picked up by
 * the monitor cron — when the backend save bridge
 * `_maybe_create_saved_strategy_for_active_execution`
 * (apps/api/app/api/routes/strategy_storage.py) creates a `SavedStrategy`
 * row. That bridge fires ONLY when the persisted `strategy_json` carries
 * BOTH a non-daily `bar_resolution` AND a non-empty
 * `risk_management.exit_ladder`. Saving "5min + no ladder" therefore
 * produces a backtest that silently never appears in My Strategies and
 * can never be tracked live.
 *
 * This predicate is true in exactly that silent-failure window so the
 * composer can block the advance / surface a warning before save. It
 * mirrors the emit conditions in `buildCustomBuildStrategyJson` below:
 * the top-level `bar_resolution` key is written only when active
 * execution is on AND the resolution is non-daily, and the exit ladder
 * is attached only when it is non-empty. Daily strategies (the common
 * backtest path) never trip it — they don't need a ladder to be useful.
 */
export function activeExecutionNeedsExitLadder(
  context: Pick<
    CustomBuildModeContext,
    "active_execution_enabled" | "bar_resolution" | "exit_ladder"
  >,
): boolean {
  return (
    context.active_execution_enabled === true &&
    context.bar_resolution !== "daily" &&
    (!Array.isArray(context.exit_ladder) || context.exit_ladder.length === 0)
  );
}

export function buildCustomBuildStrategyJson(
  context: CustomBuildModeContext,
  opts: CustomBuildBackoutOptions = {},
): StrategyJson {
  const symbol = opts.symbol ?? context.symbol;
  if (!symbol) {
    throw new Error(
      "Pick a symbol before running the backtest.",
    );
  }
  if (context.rules.length === 0) {
    throw new Error("Add at least one rule before running the backtest.");
  }
  if (context.rules[0].logic_with_prior !== null) {
    throw new Error(
      "First rule cannot have a logic operator — only rules 2+ join to the prior rule.",
    );
  }
  for (let i = 1; i < context.rules.length; i++) {
    if (context.rules[i].logic_with_prior === null) {
      throw new Error(
        `Rule ${i + 1} is missing AND/OR — every rule after the first must join to the prior rule.`,
      );
    }
  }

  const benchmark = opts.benchmark ?? "SPY";
  const rules: StrategyRule[] = context.rules.map(_toStrategyRule);

  // PRD-16c: when active execution is on AND the user has at least one
  // tier, attach exit_ladder. Empty ladder = omit (backend treats
  // `exit_ladder: null` the same as not setting it, but the validator
  // would reject `exit_ladder: []`).
  const risk_management: StrategyJson["risk_management"] = {};
  if (
    context.active_execution_enabled &&
    Array.isArray(context.exit_ladder) &&
    context.exit_ladder.length > 0
  ) {
    risk_management.exit_ladder = context.exit_ladder;
  }

  const out: StrategyJson = {
    strategy_name:
      opts.strategy_name ??
      `Custom build — ${context.rules.map((r) => r.primitive.family).join(" + ")}`,
    strategy_type: "custom_build",
    universe: [symbol.toUpperCase()],
    benchmark,
    start_date: opts.start_date ?? _defaultStart(),
    end_date: opts.end_date ?? _defaultEnd(),
    initial_capital: opts.initial_capital ?? 100_000,
    rebalance_frequency: opts.rebalance_frequency ?? "monthly",
    transaction_cost_bps: 5,
    slippage_bps: 5,
    rules,
    position_sizing: { method: "equal_weight" },
    risk_management,
    cash_management: { hold_cash_when_no_signal: true },
  };

  // bar_resolution is persisted as a top-level key on the JSON, NOT on
  // StrategyJson itself — the backend reads it off `strategy_json` in
  // the cron + the engine's run() call (PRD-16c-2 + 16c-3b). Active
  // execution off → bar_resolution defaults to 'daily' (the only
  // currently-supported resolution in the engine path).
  if (context.active_execution_enabled && context.bar_resolution !== "daily") {
    (out as unknown as Record<string, unknown>).bar_resolution =
      context.bar_resolution;
  }

  return out;
}

/**
 * Apply a `TemplateMatch.thresholds_for_user_primitives` payload onto
 * the canvas rules. Used by the "Use these defaults →" CTA on
 * `<TemplateMatchSuggestion>`.
 *
 * For each rule whose primitive_id is in the threshold map:
 *   - Set the rule's `primitive_params` from the map's
 *     non-threshold-shaped keys (period, std_dev, etc.).
 *   - Set the rule's `threshold` + `operator` if a `enter_*` / `exit_*`
 *     pattern is present.
 *
 * Rules whose primitive_id isn't in the map are left unchanged. The
 * shape of the threshold map is editorial (PRD-16a-3's per-template
 * metadata authors it), so this function is lenient about which keys
 * map to what.
 */
const THRESHOLD_KEYS_RX = /^(enter|exit|threshold|min|max|upper|lower|strong_buy|positive|breakout|trending)/i;

const OPERATOR_FROM_KEY: Record<string, "gt" | "gte" | "lt" | "lte" | undefined> = {
  enter_lt: "lt",
  enter_lte: "lte",
  enter_gt: "gt",
  enter_gte: "gte",
  exit_gt: "gt",
  exit_gte: "gte",
  exit_lt: "lt",
  exit_lte: "lte",
  upper: "gt",
  lower: "lt",
  positive: "gt",
};

export function applyTemplateThresholdsToRules(
  rules: BuildRule[],
  thresholds: Record<string, Record<string, number | string>>,
): BuildRule[] {
  return rules.map((rule) => {
    const t = thresholds[rule.primitive_id];
    if (!t) return rule;
    const next: BuildRule = {
      ...rule,
      primitive_params: { ...rule.primitive_params },
    };
    let appliedThreshold = false;
    for (const [key, raw] of Object.entries(t)) {
      const val = typeof raw === "number" ? raw : Number(raw);
      const isThresholdKey = THRESHOLD_KEYS_RX.test(key);
      if (isThresholdKey && Number.isFinite(val) && !appliedThreshold) {
        // First threshold-shaped key wins. Multiple thresholds (e.g.
        // upper + lower) on a single rule would need a richer UI; v1
        // takes the first.
        next.threshold = val;
        const op = OPERATOR_FROM_KEY[key.toLowerCase()];
        if (op) next.operator = op;
        appliedThreshold = true;
      } else if (!isThresholdKey) {
        // Treat as a primitive_params override.
        next.primitive_params[key] = raw;
      }
    }
    return next;
  });
}
