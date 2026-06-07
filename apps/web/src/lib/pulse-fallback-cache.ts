/**
 * Client-side fallback cache for Market Pulse responses.
 *
 * **Why this exists.** When the backend `/api/market/pulse` returns 5xx
 * or times out (as during the 2026-06-07 outage — 180s hangs), the
 * frontend used to show only an amber error banner with no data
 * beneath. This module lets the page degrade gracefully: persist the
 * last successful response per market in `localStorage`, then on a
 * failed fetch surface the previous response with a "data may be
 * outdated" banner instead of a useless empty state.
 *
 * Design choices:
 *   - localStorage (not sessionStorage) so the fallback survives page
 *     reloads — exactly when the user is most likely to be hitting
 *     refresh during an outage.
 *   - Per-market keys (`livermore_pulse_cache_US`, `_CN`) so switching
 *     markets doesn't blow away the other's cache.
 *   - 24h staleness bar: if the cached response is older than
 *     `MAX_FALLBACK_AGE_MS`, don't surface it — anything older is more
 *     confusing than informative for a market data product.
 *   - SSR-safe: every function guards against `window` / `localStorage`
 *     being undefined.
 */
import type { MarketPulseResponse } from "@/lib/contracts";

const STORAGE_KEY_PREFIX = "livermore_pulse_cache_";

/** Anything older than this is considered too stale to surface as fallback. */
export const MAX_FALLBACK_AGE_MS = 24 * 60 * 60 * 1000;

interface CachedPulseEnvelope {
  /** Wall-clock time the response landed in the browser. */
  fetchedAt: number;
  /** The raw response. */
  data: MarketPulseResponse;
  /** Schema version — bump when MarketPulseResponse shape changes
   *  meaningfully, so old caches don't try to render against new code. */
  version: number;
}

const SCHEMA_VERSION = 1;

function storageKey(market: "US" | "CN"): string {
  return `${STORAGE_KEY_PREFIX}${market}`;
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

/**
 * Persist a successful response. Called from the page on every
 * load-success. Silent no-op on SSR or storage-disabled browsers.
 */
export function writeCachedPulse(market: "US" | "CN", data: MarketPulseResponse): void {
  if (!isBrowser()) return;
  try {
    const envelope: CachedPulseEnvelope = {
      fetchedAt: Date.now(),
      data,
      version: SCHEMA_VERSION,
    };
    window.localStorage.setItem(storageKey(market), JSON.stringify(envelope));
  } catch {
    // localStorage can throw QuotaExceededError or be disabled (private
    // mode, Safari ITP). Failure to cache is non-critical — just skip.
  }
}

export interface CachedPulse {
  data: MarketPulseResponse;
  /** `Date` of when this response was originally fetched. */
  fetchedAt: Date;
  /** Age in milliseconds. */
  ageMs: number;
}

/**
 * Read the last good response, if present and not too stale. Returns
 * null when there's nothing usable — caller should render the error UI.
 */
export function readCachedPulse(market: "US" | "CN"): CachedPulse | null {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(market));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedPulseEnvelope;
    if (parsed.version !== SCHEMA_VERSION) return null;
    if (!parsed.data || typeof parsed.fetchedAt !== "number") return null;
    const ageMs = Date.now() - parsed.fetchedAt;
    if (ageMs > MAX_FALLBACK_AGE_MS) return null;
    return {
      data: parsed.data,
      fetchedAt: new Date(parsed.fetchedAt),
      ageMs,
    };
  } catch {
    // Corrupt JSON or other parse error — discard.
    return null;
  }
}

/** Convenience: clear the cache for a market. Used by tests; production
 *  code doesn't need this. */
export function clearCachedPulse(market: "US" | "CN"): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(storageKey(market));
  } catch {
    // ignore
  }
}
