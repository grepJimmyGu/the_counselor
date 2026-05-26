/**
 * Unit tests for Top Movers visible-card selection.
 *
 * Run directly with Node 24's TypeScript stripping:
 *
 *   cd apps/web
 *   node --experimental-strip-types \
 *     src/components/market-pulse/top-movers-selection.test.ts
 */

import { strict as assert } from "node:assert";
import type { AssetCard } from "@/lib/contracts";
import {
  selectVisibleMoverItems,
  type MoverItem,
} from "./top-movers-selection.ts";

function card(symbol: string, perf: number, cmf = 0): AssetCard {
  return {
    symbol,
    name: symbol,
    sector: "Technology",
    price: 100,
    perf_1d: perf,
    cmf_20: cmf,
    market_cap: null,
    latest_date: "2026-05-22",
    is_stale: false,
  };
}

function stock(symbol: string, perf: number, cmf = 0): MoverItem {
  return {
    card: card(symbol, perf, cmf),
    category: "Stock",
    href: `/stocks/${symbol}`,
  };
}

function etf(symbol: string, perf: number, cmf = 0): MoverItem {
  return {
    card: card(symbol, perf, cmf),
    category: "ETF",
    href: `/stocks/${symbol}`,
  };
}

function test(name: string, fn: () => void): void {
  try {
    fn();
    console.log(`  ✓ ${name}`);
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${(err as Error).message}`);
    process.exitCode = 1;
  }
}

console.log("top-movers-selection\n");

test("500 stock items render only the visible 10 after ranking", () => {
  const items = Array.from({ length: 500 }, (_, i) =>
    stock(`S${i}`, i / 1000),
  );

  const visible = selectVisibleMoverItems(items, "all", "gainers");

  assert.equal(visible.length, 10);
  assert.deepEqual(visible.map((item) => item.card.symbol), [
    "S499",
    "S498",
    "S497",
    "S496",
    "S495",
    "S494",
    "S493",
    "S492",
    "S491",
    "S490",
  ]);
});

test("changing sort changes the visible symbols", () => {
  const items = [
    stock("LOWEST", -0.05),
    stock("MIDDLE", 0.01),
    stock("HIGHEST", 0.08),
  ];

  const gainers = selectVisibleMoverItems(items, "all", "gainers", 2)
    .map((item) => item.card.symbol);
  const losers = selectVisibleMoverItems(items, "all", "losers", 2)
    .map((item) => item.card.symbol);

  assert.deepEqual(gainers, ["HIGHEST", "MIDDLE"]);
  assert.deepEqual(losers, ["LOWEST", "MIDDLE"]);
});

test("ETF filter still returns visible ETF cards", () => {
  const items = [
    stock("AAPL", 0.10),
    stock("MSFT", 0.08),
    etf("SPY", 0.01),
    etf("QQQ", 0.02),
  ];

  const symbols = selectVisibleMoverItems(items, "etf", "gainers")
    .map((item) => item.card.symbol);

  assert.deepEqual(symbols, ["QQQ", "SPY"]);
});
