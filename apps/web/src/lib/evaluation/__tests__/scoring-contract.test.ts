/**
 * The TypeScript half of the 3-dimensional score contract.
 *
 * `scoring.ts` drives the score gauges on the stock detail page. The
 * server-rendered daily share card needs the same three numbers and cannot
 * call TypeScript, so `apps/api/app/services/evaluation_scoring.py` is a
 * faithful port.
 *
 * Two implementations of one score drift silently. The failure mode is a
 * shared card claiming "Valuation 78" linking to a page that says 71 — the
 * product contradicting itself in front of a reader who clicked through
 * precisely to check.
 *
 * Both sides read the SAME fixture. This test fails if the TypeScript
 * arithmetic changes; `apps/api/tests/test_evaluation_scoring.py` fails if
 * the Python does. Fix both, regenerate, or accept a divergent card.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  calculateStockHealthScore,
  calculateStockValuationScore,
  calculateStockTrendScore,
  getFinalScore,
  getFinalLabel,
} from "../scoring";
import type { StockMetricsInput } from "../types";

const FIXTURE = join(
  __dirname,
  "../../../../../api/tests/fixtures/evaluation_scoring_cases.json",
);

type Case = {
  name: string;
  input: Record<string, unknown>;
  expected: { health: number; valuation: number; trend: number; final: number; label: string };
};

const { cases } = JSON.parse(readFileSync(FIXTURE, "utf8")) as { cases: Case[] };

/** Every field null, then the case's inputs on top — mirrors how the fixture
 *  was generated, so an absent key means "no data", never zero. */
function toMetrics(over: Record<string, unknown>): StockMetricsInput {
  return {
    ticker: "T", companyName: "T", sector: null, marketCap: null, price: null,
    revenueYoy: null, revenue3yCagr: null, grossMargin: null, operatingMargin: null,
    netMargin: null, roe: null, freeCashFlow: null, fcfMargin: null, fcfConversion: null,
    cash: null, netDebt: null, debtToEquity: null, currentRatio: null,
    interestCoverage: null, peRatio: null, pegRatio: null, evEbitda: null,
    fcfYield: null, perf3m: null, perf12m: null, ma50: null, ma200: null,
    rsVsSector: null, ...over,
  } as unknown as StockMetricsInput;
}

describe("3-dimensional score — cross-language contract", () => {
  it("has a non-empty fixture", () => {
    // An emptied fixture would make every case below vacuous rather than red.
    expect(cases.length).toBeGreaterThanOrEqual(10);
  });

  it.each(cases)("$name", ({ input, expected }) => {
    const m = toMetrics(input);
    const health = calculateStockHealthScore(m);
    const valuation = calculateStockValuationScore(m);
    const trend = calculateStockTrendScore(m);
    const final = getFinalScore(health, valuation, trend);
    expect({ health, valuation, trend, final, label: getFinalLabel(final) }).toEqual(expected);
  });
});
