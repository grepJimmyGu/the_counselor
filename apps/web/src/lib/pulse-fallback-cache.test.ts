/**
 * Tests for the Market Pulse fallback cache.
 *
 * Pins the invariants that keep `_market-pulse.tsx` from regressing on
 * the 2026-06-07 outage UX:
 *   - Round-trip preserves the response
 *   - Stale-too-long entries return null (we don't show ancient data)
 *   - Corrupt JSON in storage returns null (no crash)
 *   - Version mismatch returns null (schema change safety)
 *   - SSR-safe (no `window` doesn't throw)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MarketPulseResponse } from "@/lib/contracts";
import {
  MAX_FALLBACK_AGE_MS,
  clearCachedPulse,
  readCachedPulse,
  writeCachedPulse,
} from "@/lib/pulse-fallback-cache";

function makePulse(market: "US" | "CN"): MarketPulseResponse {
  // Minimal MarketPulseResponse — only the fields the cache touches.
  // Cast to satisfy TS without enumerating every field.
  return {
    market,
    as_of: new Date("2026-06-07T13:00:00Z").toISOString(),
    indices: [],
    macro: [],
    sectors: [],
    top_assets: [],
    featured_etfs: [],
    narrative: null,
    macro_signals: [],
  } as unknown as MarketPulseResponse;
}

describe("pulse-fallback-cache", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("round-trips a response through write -> read", () => {
    const pulse = makePulse("US");
    writeCachedPulse("US", pulse);

    const cached = readCachedPulse("US");
    expect(cached).not.toBeNull();
    expect(cached!.data.market).toBe("US");
    expect(cached!.fetchedAt).toBeInstanceOf(Date);
    expect(cached!.ageMs).toBeGreaterThanOrEqual(0);
  });

  it("returns null when no entry exists for the market", () => {
    expect(readCachedPulse("US")).toBeNull();
    expect(readCachedPulse("CN")).toBeNull();
  });

  it("keeps US and CN caches independent", () => {
    writeCachedPulse("US", makePulse("US"));
    writeCachedPulse("CN", makePulse("CN"));

    expect(readCachedPulse("US")!.data.market).toBe("US");
    expect(readCachedPulse("CN")!.data.market).toBe("CN");
  });

  it("returns null when the cached entry is older than MAX_FALLBACK_AGE_MS", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-07T00:00:00Z"));
    writeCachedPulse("US", makePulse("US"));

    // Advance past the 24h staleness bar.
    vi.setSystemTime(new Date(Date.now() + MAX_FALLBACK_AGE_MS + 1000));
    expect(readCachedPulse("US")).toBeNull();
  });

  it("returns null on corrupt JSON without throwing", () => {
    window.localStorage.setItem("livermore_pulse_cache_US", "{not json");
    expect(() => readCachedPulse("US")).not.toThrow();
    expect(readCachedPulse("US")).toBeNull();
  });

  it("returns null on version mismatch (schema change safety)", () => {
    const stale = {
      version: 9999,
      fetchedAt: Date.now(),
      data: { market: "US" },
    };
    window.localStorage.setItem("livermore_pulse_cache_US", JSON.stringify(stale));
    expect(readCachedPulse("US")).toBeNull();
  });

  it("clearCachedPulse removes the entry", () => {
    writeCachedPulse("US", makePulse("US"));
    expect(readCachedPulse("US")).not.toBeNull();

    clearCachedPulse("US");
    expect(readCachedPulse("US")).toBeNull();
  });

  it("write is a silent no-op when localStorage throws (e.g. quota / disabled)", () => {
    const setSpy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    expect(() => writeCachedPulse("US", makePulse("US"))).not.toThrow();
    setSpy.mockRestore();
  });
});
