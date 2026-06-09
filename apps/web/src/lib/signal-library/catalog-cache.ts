/**
 * PRD-16a-4 — Signal catalog cache with version-stamped invalidation.
 *
 * Stores the most recently fetched `SignalPrimitivesResponse` in
 * localStorage under a key keyed by the catalog's `version_hash`. On
 * cold app load:
 *
 *   1. Check cache for the last-seen catalog.
 *   2. Fetch `GET /api/signal-primitives` with `If-None-Match: "<last_hash>"`.
 *   3. On 304, reuse the cached payload (zero network deserialization).
 *   4. On 200, the response body's `version_hash` is the new key —
 *      write the fresh catalog under that key.
 *
 * Why localStorage (not sessionStorage / IDB): catalog is ~55 entries
 * × ~500 bytes = ~30KB; localStorage's 5MB quota is plenty. SessionStorage
 * would re-fetch on every new tab — wasteful. IDB is overkill for a
 * key-value blob.
 *
 * Why version_hash instead of expires_at: the backend's ETag handles
 * freshness server-side; the client only needs "is this still the same
 * catalog?" — that's a content question, not a time question.
 *
 * SSR-safe: every cache method guards on `typeof window !== "undefined"`.
 * Build-time render won't touch localStorage.
 */
import type {
  SignalPrimitivesResponse,
} from "@/lib/contracts";

const CACHE_KEY = "livermore_signal_catalog";
const VERSION_KEY = "livermore_signal_catalog_version";

interface CacheEnvelope {
  version_hash: string;
  payload: SignalPrimitivesResponse;
  /** Wall-clock when this cache entry was last refreshed — used purely
   *  for debugging / dev-tools surfacing; expiry is content-addressed
   *  via version_hash, not time. */
  fetched_at: string;
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

/** Read the cached catalog (any version). Returns null when nothing's
 *  cached, the cache is corrupt, or we're SSR. */
export function readCatalogCache(): CacheEnvelope | null {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope;
    // Defensive: a partial cache without the required keys is corrupt.
    if (!parsed.version_hash || !parsed.payload) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Read just the last-seen version hash — used to populate the
 *  `If-None-Match` header without deserializing the full payload. */
export function readCachedVersionHash(): string | null {
  if (!isBrowser()) return null;
  try {
    return window.localStorage.getItem(VERSION_KEY);
  } catch {
    return null;
  }
}

/** Write a fresh catalog payload to the cache. Called by the api helper
 *  after a 200 response from `GET /api/signal-primitives`. */
export function writeCatalogCache(payload: SignalPrimitivesResponse): void {
  if (!isBrowser()) return;
  const envelope: CacheEnvelope = {
    version_hash: payload.version_hash,
    payload,
    fetched_at: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(envelope));
    window.localStorage.setItem(VERSION_KEY, payload.version_hash);
  } catch {
    // Quota exceeded / private mode / other — caller falls back to
    // re-fetching next time. Cache is an optimization, not a correctness
    // dependency.
  }
}

/** Drop everything — useful from a dev tool or if catalog corruption is
 *  ever surfaced as a recurring issue. */
export function clearCatalogCache(): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(CACHE_KEY);
    window.localStorage.removeItem(VERSION_KEY);
  } catch {
    // ignored
  }
}
