// Generates the parity fixture for LivermoreKit's Swift port of the company
// scores, by running the web's own TypeScript implementation.
//
//   node apps/ios/scripts/gen_scoring_golden.mjs
//
// Re-run whenever apps/web/src/lib/evaluation/scoring.ts changes; the Swift
// test then fails until StockScoring.swift is changed to match.
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const scoring = await import(resolve(here, "../../web/src/lib/evaluation/scoring.ts"));
const out = resolve(here, "../LivermoreKit/Tests/LivermoreKitTests/Fixtures/scoring-golden.json");

// Deterministic PRNG so the fixture is reproducible.
let seed = 20261116;
function rand() {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

// Every threshold the scoring branches on, so cases land on and around them.
const edges = {
  price: [50, 100, 250],
  revenueYoy: [-0.05, 0, 0.05, 0.1, 0.2],
  grossMargin: [0.2, 0.35, 0.5],
  operatingMargin: [0, 0.1, 0.2],
  roe: [-0.4, 0, 0.1, 0.2, 0.3, 0.5, 1.3],
  fcfMargin: [0, 0.05, 0.15, 0.25],
  fcfConversion: [0.5, 0.8, 1.0],
  netDebt: [-1e9, 0, 5e9, 20e9, 50e9],
  debtToEquity: [0.3, 0.75, 1.5, 3],
  currentRatio: [0.75, 1, 1.5, 2],
  peRatio: [12, 18, 25, 35, 50],
  pegRatio: [0.8, 1.2, 2, 3],
  evEbitda: [8, 12, 18, 25, 35],
  fcfYield: [0.01, 0.03, 0.05, 0.08],
  perf3m: [-0.1, 0, 0.05, 0.15],
  perf12m: [-0.2, 0, 0.1, 0.25],
  ma50: [48, 95, 100, 105, 240],
  ma200: [45, 90, 100, 110, 230],
  rsVsSector: [-0.1, -0.03, 0.03, 0.1],
};
const fields = Object.keys(edges);

function value(field) {
  const r = rand();
  if (r < 0.18) return null;
  const e = edges[field];
  const base = e[Math.floor(rand() * e.length)];
  if (r < 0.45) return base;                                   // exactly on a threshold
  const span = Math.abs(base) > 1e6 ? 3e9 : Math.max(Math.abs(base), 0.05);
  return base + (rand() - 0.5) * span;                         // around it
}

const cases = [];
const blank = Object.fromEntries(fields.map((f) => [f, null]));
const inputs = [blank];
for (let i = 0; i < 400; i++) inputs.push(Object.fromEntries(fields.map((f) => [f, value(f)])));

for (const input of inputs) {
  const health = scoring.calculateStockHealthScore(input);
  const valuation = scoring.calculateStockValuationScore(input);
  const trend = scoring.calculateStockTrendScore(input);
  const overall = scoring.getFinalScore(health, valuation, trend);
  cases.push({
    input,
    expected: {
      health, valuation, trend, overall,
      label: scoring.getFinalLabel(overall),
      status: [health, valuation, trend].map(scoring.getScoreStatus),
    },
  });
}

writeFileSync(out, JSON.stringify({ source: "apps/web/src/lib/evaluation/scoring.ts", cases }, null, 0) + "\n");
console.log(`${cases.length} cases -> ${out}`);
