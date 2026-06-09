/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SignalPrimitivesResponse } from "@/lib/contracts";
import {
  clearCatalogCache,
  readCachedVersionHash,
  readCatalogCache,
  writeCatalogCache,
} from "../catalog-cache";

function _payload(version: string): SignalPrimitivesResponse {
  return {
    primitives: [
      {
        id: "rsi",
        category: "mean_reversion",
        family: "RSI",
        name: "RSI",
        description: "Measures overbought/oversold extremes over recent gains/losses.",
        long_description: null,
        parameters: [
          {
            name: "period",
            default: 14,
            min_value: 2,
            max_value: 100,
            description: "Look-back window",
          },
        ],
        default_thresholds: { upper: 70, lower: 30 },
        asset_compat: ["equity"],
        evidence_tier: "A",
        provider_impl: "rsi",
        data_source: "price",
        resolution: ["daily"],
        is_ranking: false,
        compute_strategy: "local",
      },
    ],
    categories: [
      "trend",
      "mean_reversion",
      "momentum",
      "volume",
      "volatility",
      "fundamental",
      "sentiment",
      "cross_sectional",
    ],
    version_hash: version,
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("catalog-cache", () => {
  it("returns null when nothing has been written", () => {
    expect(readCatalogCache()).toBeNull();
    expect(readCachedVersionHash()).toBeNull();
  });

  it("round-trips a payload through write → read", () => {
    const payload = _payload("v1");
    writeCatalogCache(payload);
    const cached = readCatalogCache();
    expect(cached).not.toBeNull();
    expect(cached!.version_hash).toBe("v1");
    expect(cached!.payload.primitives[0].id).toBe("rsi");
    expect(readCachedVersionHash()).toBe("v1");
  });

  it("overwrites prior cache when a new version is written", () => {
    writeCatalogCache(_payload("v1"));
    writeCatalogCache(_payload("v2"));
    expect(readCachedVersionHash()).toBe("v2");
    expect(readCatalogCache()!.payload.version_hash).toBe("v2");
  });

  it("clear() removes both keys", () => {
    writeCatalogCache(_payload("v1"));
    clearCatalogCache();
    expect(readCatalogCache()).toBeNull();
    expect(readCachedVersionHash()).toBeNull();
  });

  it("returns null on corrupt JSON", () => {
    window.localStorage.setItem("livermore_signal_catalog", "not-json");
    expect(readCatalogCache()).toBeNull();
  });

  it("returns null when the envelope is missing required keys", () => {
    window.localStorage.setItem(
      "livermore_signal_catalog",
      JSON.stringify({ payload: {} }),
    );
    expect(readCatalogCache()).toBeNull();
  });
});
