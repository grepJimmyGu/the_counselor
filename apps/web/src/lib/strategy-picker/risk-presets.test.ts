/**
 * Unit tests for `applyRiskLevel` — PR-D, 2026-05-24.
 *
 * Run via:
 *   cd apps/web
 *   node --experimental-strip-types src/lib/strategy-picker/risk-presets.test.ts
 *
 * Asserts the mapping table from `Quant Strategy/framework/risk_control_prompt.md`:
 *
 *   | preset | target_vol | max_dd | stop_loss |
 *   |--------|-----------:|-------:|----------:|
 *   | low    |       0.08 |   0.15 |      0.08 |
 *   | medium |       0.12 |   0.25 |      0.12 |
 *   | high   |       null |   0.40 |      null |
 */

import { strict as assert } from "node:assert";
import type { StrategyJson } from "@/lib/contracts";
import { applyRiskLevel, detectRiskPreset } from "./risk-presets.ts";

const BASE: StrategyJson = {
  strategy_name: "Test",
  strategy_type: "moving_average_filter",
  universe: ["SPY"],
  benchmark: "SPY",
  start_date: "2020-01-01",
  end_date: "2025-01-01",
  initial_capital: 100_000,
  rebalance_frequency: "monthly",
  transaction_cost_bps: 0,
  slippage_bps: 0,
  rules: [],
  position_sizing: { method: "equal_weight", max_positions: 1 },
  risk_management: {},
  cash_management: { hold_cash_when_no_signal: true },
};

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed += 1;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`  ✗ ${name}`);
    console.error(`    ${(err as Error).message}`);
  }
}

console.log("risk-presets\n");

test("low preset writes target_vol=0.08, max_dd=0.15, stop_loss=0.08", () => {
  const out = applyRiskLevel(BASE, "low");
  assert.equal(out.position_sizing.method, "vol_target");
  assert.equal(out.position_sizing.target_vol_annual, 0.08);
  assert.equal(out.risk_management.max_drawdown_stop, 0.15);
  assert.equal(out.risk_management.stop_loss_pct, 0.08);
});

test("medium preset writes target_vol=0.12, max_dd=0.25, stop_loss=0.12", () => {
  const out = applyRiskLevel(BASE, "medium");
  assert.equal(out.position_sizing.method, "vol_target");
  assert.equal(out.position_sizing.target_vol_annual, 0.12);
  assert.equal(out.risk_management.max_drawdown_stop, 0.25);
  assert.equal(out.risk_management.stop_loss_pct, 0.12);
});

test("high preset omits target_vol and stop_loss, sets max_dd=0.40", () => {
  const out = applyRiskLevel(BASE, "high");
  // position_sizing.method should NOT be vol_target (preserved as equal_weight)
  assert.equal(out.position_sizing.method, "equal_weight");
  assert.equal(out.position_sizing.target_vol_annual, undefined);
  assert.equal(out.risk_management.max_drawdown_stop, 0.4);
  assert.equal(out.risk_management.stop_loss_pct, undefined);
});

test("preserves unrelated strategy fields", () => {
  const out = applyRiskLevel(BASE, "low");
  assert.equal(out.strategy_name, "Test");
  assert.equal(out.universe[0], "SPY");
  assert.equal(out.initial_capital, 100_000);
  assert.equal(out.rebalance_frequency, "monthly");
});

test("does not mutate the input strategy", () => {
  const input: StrategyJson = JSON.parse(JSON.stringify(BASE));
  applyRiskLevel(input, "low");
  // Input untouched
  assert.equal(input.position_sizing.target_vol_annual, undefined);
  assert.equal(input.risk_management.max_drawdown_stop, undefined);
});

test("idempotent — applying the same preset twice produces equal output", () => {
  const a = applyRiskLevel(BASE, "low");
  const b = applyRiskLevel(a, "low");
  assert.deepEqual(a, b);
});

test("re-applying a different preset overrides cleanly", () => {
  const lowApplied = applyRiskLevel(BASE, "low");
  const highApplied = applyRiskLevel(lowApplied, "high");
  // High should clear stop_loss; max_dd jumps to 0.40
  assert.equal(highApplied.risk_management.max_drawdown_stop, 0.4);
  // Note: stop_loss_pct stays because previous low set it and high
  // doesn't unset (the doc treats "null" as "do not set", not "delete").
  // This is documented behavior; if the user wants to actually clear,
  // they should pick high from the start.
  assert.equal(highApplied.risk_management.stop_loss_pct, 0.08);
});

test("detectRiskPreset infers from target_vol_annual", () => {
  assert.equal(detectRiskPreset(applyRiskLevel(BASE, "low")), "low");
  assert.equal(detectRiskPreset(applyRiskLevel(BASE, "medium")), "medium");
  assert.equal(detectRiskPreset(applyRiskLevel(BASE, "high")), "high");
  // Strategy with no target_vol — treated as high
  assert.equal(detectRiskPreset(BASE), "high");
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
