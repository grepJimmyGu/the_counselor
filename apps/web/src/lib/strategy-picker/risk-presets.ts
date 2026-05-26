/**
 * Risk preset → StrategyJSON mutation (PR-D, 2026-05-24).
 *
 * Implements the spec from `Quant Strategy/framework/risk_control_prompt.md`.
 * The summary step lets the user pick one of three presets:
 * Low / Medium / High. This helper translates that choice into the
 * four engine-side parameters that actually shape the backtest:
 *
 *   - `position_sizing.target_vol_annual`  (sizing scale; vol-target overlay)
 *   - `risk_management.max_drawdown_stop`  (portfolio kill switch)
 *   - `risk_management.stop_loss_pct`      (per-position kill switch)
 *
 * Per the doc: the engine code for all three was already in
 * `apps/api/app/services/backtester/engine.py` before this PR.
 * Frontend just needed to start sending the right StrategyJSON.
 *
 * Mapping table (verbatim from risk_control_prompt.md §"The four levers"):
 *
 *   | preset | target_vol | max_dd | stop_loss |
 *   |--------|-----------:|-------:|----------:|
 *   | low    |       0.08 |   0.15 |      0.08 |
 *   | medium |       0.12 |   0.25 |      0.12 |
 *   | high   |       null |   0.40 |      null |
 *
 * Null = "do not set" (no vol scaling, no per-position stop). The
 * helper preserves any existing strategy fields that the preset
 * doesn't override — risk is additive, not destructive.
 */
import type { StrategyJson } from "@/lib/contracts";
import type { RiskPreset } from "@/components/strategy-builder/summary-step";

const PROFILES: Record<
  RiskPreset,
  { target_vol: number | null; max_dd: number; stop_loss: number | null }
> = {
  low: { target_vol: 0.08, max_dd: 0.15, stop_loss: 0.08 },
  medium: { target_vol: 0.12, max_dd: 0.25, stop_loss: 0.12 },
  high: { target_vol: null, max_dd: 0.4, stop_loss: null },
};

/**
 * Mutate a copy of the strategy with the preset's risk + sizing
 * parameters. Returns a NEW object (does not mutate the input);
 * safe to call repeatedly without compounding effects.
 *
 * Behavior:
 *  - When `target_vol` is set, switches `position_sizing.method` to
 *    `vol_target` and writes `target_vol_annual`. Other sizing fields
 *    (e.g. `max_positions`) are preserved.
 *  - When `target_vol` is null (high preset), the existing
 *    `position_sizing` block is preserved untouched — no vol scaling,
 *    user keeps whatever sizing the template specified.
 *  - `max_drawdown_stop` is always set (even for "high" — at 40%).
 *  - `stop_loss_pct` is only set for low/medium; null for high.
 */
export function applyRiskLevel(strategy: StrategyJson, preset: RiskPreset): StrategyJson {
  const profile = PROFILES[preset];

  const nextPositionSizing =
    profile.target_vol !== null
      ? {
          ...strategy.position_sizing,
          method: "vol_target" as const,
          target_vol_annual: profile.target_vol,
        }
      : { ...strategy.position_sizing };

  const nextRiskManagement = {
    ...strategy.risk_management,
    max_drawdown_stop: profile.max_dd,
    ...(profile.stop_loss !== null ? { stop_loss_pct: profile.stop_loss } : {}),
  };

  return {
    ...strategy,
    position_sizing: nextPositionSizing,
    risk_management: nextRiskManagement,
  };
}

/**
 * Inverse-lookup: classify an existing strategy's risk profile from
 * its current `target_vol_annual` value, so the summary step can
 * pre-select the right preset when editing a saved strategy. Returns
 * 'medium' as a safe default when no match.
 */
export function detectRiskPreset(strategy: StrategyJson): RiskPreset {
  const tv = strategy.position_sizing.target_vol_annual;
  if (tv === undefined || tv === null) return "high";
  if (tv <= 0.09) return "low";
  if (tv <= 0.13) return "medium";
  return "high";
}
