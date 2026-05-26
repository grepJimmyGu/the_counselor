/**
 * Unit tests for Top Movers live-quote selection.
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
  liveSymbolsForMoverItems,
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

test("500 stock items request live quotes for only the visible 10", () => {
  const items = Array.from({ length: 500 }, (_, i) =>
    stock(`S${i}`, i / 1000),
  );

  const visible = selectVisibleMoverItems(items, "all", "gainers");
  const symbols = liveSymbolsForMoverItems(visible);

  assert.equal(visible.length, 10);
  assert.deepEqual(symbols, [
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

test("changing sort changes the requested live symbols", () => {
  const items = [
    stock("LOWEST", -0.05),
    stock("MIDDLE", 0.01),
    stock("HIGHEST", 0.08),
  ];

  const gainers = liveSymbolsForMoverItems(
    selectVisibleMoverItems(items, "all", "gainers", 2),
  );
  const losers = liveSymbolsForMoverItems(
    selectVisibleMoverItems(items, "all", "losers", 2),
  );

  assert.deepEqual(gainers, ["HIGHEST", "MIDDLE"]);
  assert.deepEqual(losers, ["LOWEST", "MIDDLE"]);
});

test("ETF filter still requests live quotes for visible ETF cards", () => {
  const items = [
    stock("AAPL", 0.10),
    stock("MSFT", 0.08),
    etf("SPY", 0.01),
    etf("QQQ", 0.02),
  ];

  const symbols = liveSymbolsForMoverItems(
    selectVisibleMoverItems(items, "etf", "gainers"),
  );

  assert.deepEqual(symbols, ["QQQ", "SPY"]);
});
