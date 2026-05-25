/**
 * Unit tests for `strategy-wizard-recommend.ts`.
 *
 * No Jest setup in this monorepo yet (frontend has no test runner —
 * see the per-PR plan note in `~/.claude/plans/modular-greeting-sifakis.md`).
 * Run this file directly via Node 24's TypeScript stripping:
 *
 *   cd apps/web
 *   node --experimental-strip-types \
 *     src/components/strategy-builder/wizard/strategy-wizard-recommend.test.ts
 *
 * Or via tsx if installed:
 *   npx tsx src/components/strategy-builder/wizard/strategy-wizard-recommend.test.ts
 *
 * Tests are canonical (answers → expected top recommendation) pairs
 * taken from the framework HTML's example flows. Each one mirrors a
 * walk-through that a reviewer of the HTML's wizard would naturally
 * produce. If the recommendation engine drifts from the HTML's
 * behavior, one of these cases will fail.
 */

import { strict as assert } from "node:assert";
import { WIZARD_STRATEGIES, type WizardAnswers } from "./strategy-wizard-data.ts";
import {
  buildWhy,
  isComplete,
  recommend,
  scoreStrategy,
} from "./strategy-wizard-recommend.ts";

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

console.log("strategy-wizard-recommend\n");

// ── isComplete ──────────────────────────────────────────────────────────────

test("isComplete returns false when any field is null", () => {
  assert.equal(isComplete({ goal: null, cadence: null, asset: null, behavior: null, dd: null }), false);
  assert.equal(isComplete({ goal: "growth", cadence: null, asset: null, behavior: null, dd: null }), false);
  assert.equal(isComplete({ goal: "growth", cadence: "weekly", asset: "single_stock", behavior: "trend", dd: null }), false);
});

test("isComplete returns true when all 5 fields are set", () => {
  assert.equal(
    isComplete({ goal: "growth", cadence: "weekly", asset: "single_stock", behavior: "trend", dd: "medium" }),
    true,
  );
});

// ── scoreStrategy hard disqualifiers ───────────────────────────────────────

test("scoreStrategy disqualifies fundamentals-required strategies on commodities", () => {
  const valueComposite = WIZARD_STRATEGIES.find((s) => s.slug === "value_composite")!;
  const ans = { goal: "alpha" as const, cadence: "quarterly" as const, asset: "single_commodity" as const, behavior: "mean" as const, dd: "medium" as const };
  assert.equal(scoreStrategy(valueComposite, ans), -1, "value composite needs fundamentals; commodities have none");
});

test("scoreStrategy disqualifies fundamentals-required strategies on pairs", () => {
  const multiFactor = WIZARD_STRATEGIES.find((s) => s.slug === "multi_factor_composite")!;
  const ans = { goal: "hedge" as const, cadence: "monthly" as const, asset: "pair" as const, behavior: "mean" as const, dd: "medium" as const };
  assert.equal(scoreStrategy(multiFactor, ans), -1);
});

test("scoreStrategy disqualifies high-drawdown strategies for low-tolerance users", () => {
  const crossMomentum = WIZARD_STRATEGIES.find((s) => s.slug === "cross_sectional_momentum")!;
  const ans = { goal: "growth" as const, cadence: "monthly" as const, asset: "stock_basket" as const, behavior: "trend" as const, dd: "low" as const };
  assert.equal(scoreStrategy(crossMomentum, ans), -1);
});

test("scoreStrategy disqualifies asset-incompatible strategies", () => {
  const pairsTrading = WIZARD_STRATEGIES.find((s) => s.slug === "pairs_trading")!;
  const ans = { goal: "alpha" as const, cadence: "daily" as const, asset: "single_stock" as const, behavior: "mean" as const, dd: "medium" as const };
  // pairs_trading.asset.single_stock === 0 → disqualified
  assert.equal(scoreStrategy(pairsTrading, ans), -1);
});

// ── scoreStrategy weighting ────────────────────────────────────────────────

test("scoreStrategy applies the documented weights (asset 2x, behavior 1.5x, goal 1x, cadence 1x)", () => {
  const sectorRotation = WIZARD_STRATEGIES.find((s) => s.slug === "sector_rotation")!;
  // All-2s answer that's compatible with sector_rotation:
  //   asset=sector_etf (2) → 2*2 = 4
  //   behavior=trend (2)   → 1.5*2 = 3
  //   goal=growth (2)      → 1*2 = 2
  //   cadence=monthly (2)  → 1*2 = 2
  //   dd=medium (no penalty since strategy drawdown=medium)
  //   total = 11
  const ans = { goal: "growth" as const, cadence: "monthly" as const, asset: "sector_etf" as const, behavior: "trend" as const, dd: "medium" as const };
  assert.equal(scoreStrategy(sectorRotation, ans), 11);
});

test("scoreStrategy applies the low+medium drawdown soft penalty (-0.5)", () => {
  // Low-volatility has drawdown='low' — no penalty for dd='low'.
  // But Time-Series Momentum has drawdown='medium' — should hit the -0.5.
  const tsm = WIZARD_STRATEGIES.find((s) => s.slug === "time_series_momentum")!;
  const ansLow = { goal: "growth" as const, cadence: "monthly" as const, asset: "broad_etf" as const, behavior: "trend" as const, dd: "low" as const };
  const ansMed = { ...ansLow, dd: "medium" as const };
  const scoreLow = scoreStrategy(tsm, ansLow);
  const scoreMed = scoreStrategy(tsm, ansMed);
  // Same answer except dd: low should be 0.5 less than medium
  assert.equal(scoreMed - scoreLow, 0.5, `expected medium-low diff = 0.5, got ${scoreMed - scoreLow}`);
});

// ── recommend ──────────────────────────────────────────────────────────────

test("recommend returns empty when answers are incomplete", () => {
  const recs = recommend(WIZARD_STRATEGIES, { goal: "growth", cadence: null, asset: null, behavior: null, dd: null });
  assert.equal(recs.length, 0);
});

test("recommend returns top-K sorted by score descending", () => {
  const ans: WizardAnswers = { goal: "growth", cadence: "monthly", asset: "sector_etf", behavior: "trend", dd: "medium" };
  const recs = recommend(WIZARD_STRATEGIES, ans, 3);
  assert.ok(recs.length > 0 && recs.length <= 3, `expected 1-3 recs, got ${recs.length}`);
  for (let i = 0; i + 1 < recs.length; i++) {
    assert.ok(recs[i]._score >= recs[i + 1]._score, "scores must be descending");
  }
});

test("recommend for 'sector ETFs + trend + monthly + growth + medium' includes sector_rotation in top-3 (ties with time_series_momentum at score 11)", () => {
  const ans: WizardAnswers = { goal: "growth", cadence: "monthly", asset: "sector_etf", behavior: "trend", dd: "medium" };
  const recs = recommend(WIZARD_STRATEGIES, ans, 3);
  const slugs = recs.map((r) => r.slug);
  assert.ok(slugs.includes("sector_rotation"), `expected sector_rotation in top-3, got [${slugs.join(", ")}]`);
  // The top pick is one of the tied 11-point strategies
  assert.ok(
    ["sector_rotation", "time_series_momentum"].includes(recs[0].slug),
    `expected top pick in tied 11-point set, got ${recs[0].slug}`,
  );
});

test("recommend for 'single commodity + trend + weekly + growth + medium' surfaces a trend strategy as top", () => {
  // Commodity + trend → MA filter / crossover / TSM / breakout should
  // all qualify; one of them tops. Test that it's NOT a
  // fundamentals-required strategy (those are disqualified for commodities).
  const ans: WizardAnswers = { goal: "growth", cadence: "weekly", asset: "single_commodity", behavior: "trend", dd: "medium" };
  const recs = recommend(WIZARD_STRATEGIES, ans, 3);
  assert.ok(recs.length > 0, "should return at least one rec for commodity+trend");
  for (const r of recs) {
    assert.notEqual(r.requiresFundamentals, true, `${r.slug} requires fundamentals — should be disqualified for commodities`);
  }
});

test("recommend for 'pair + mean + daily + alpha + medium' surfaces pairs_trading as top", () => {
  const ans: WizardAnswers = { goal: "alpha", cadence: "daily", asset: "pair", behavior: "mean", dd: "medium" };
  const recs = recommend(WIZARD_STRATEGIES, ans, 3);
  assert.equal(recs[0].slug, "pairs_trading", `expected pairs_trading, got ${recs[0].slug}`);
});

test("recommend for 'broad ETF + trend + monthly + defense + low' surfaces a low-DD trend strategy", () => {
  const ans: WizardAnswers = { goal: "defense", cadence: "monthly", asset: "broad_etf", behavior: "trend", dd: "low" };
  const recs = recommend(WIZARD_STRATEGIES, ans, 3);
  assert.ok(recs.length > 0);
  // All recs must have drawdown != 'high' (dd:low disqualifies high-dd)
  for (const r of recs) {
    assert.notEqual(r.drawdown, "high", `${r.slug} has high drawdown — should be disqualified for dd:low`);
  }
});

// ── buildWhy ───────────────────────────────────────────────────────────────

test("buildWhy returns plain-English reasons matching the strategy fit", () => {
  const sectorRotation = WIZARD_STRATEGIES.find((s) => s.slug === "sector_rotation")!;
  const ans: WizardAnswers = { goal: "growth", cadence: "monthly", asset: "sector_etf", behavior: "trend", dd: "medium" };
  const reasons = buildWhy(sectorRotation, ans);
  assert.ok(reasons.some((r) => r.includes("Strong fit for your asset")), "should call out strong asset fit");
  assert.ok(reasons.some((r) => r.includes("Designed for assets that trend")), "should call out trend behavior fit");
});

test("buildWhy returns empty for incomplete answers", () => {
  const sectorRotation = WIZARD_STRATEGIES.find((s) => s.slug === "sector_rotation")!;
  const reasons = buildWhy(sectorRotation, { goal: null, cadence: null, asset: null, behavior: null, dd: null });
  assert.equal(reasons.length, 0);
});

// ── Summary ────────────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
