/**
 * PRD-24a §3.10 (B1) — deep-link reader for the /sentiment hub.
 *
 * The Home "Themes firing today" cards link to
 *   /sentiment?toolkit=<id>&autorun=1[&display=<label>]
 * so a click should land on the hub with that toolkit focused and — when
 * `autorun=1` — already running, instead of dumping the user on the generic
 * toolkit grid (the bug this fixes; same class as the `?template=` one).
 *
 * Pure reader (no React) so it's trivially unit-testable; the page wires
 * the result into a one-shot effect.
 */

export interface SentimentDeepLink {
  /** The toolkit id from `?toolkit=` (null if absent). */
  toolkitId: string | null;
  /** `?autorun=1` → run the toolkit immediately on land. */
  autorun: boolean;
  /** `?display=` label override for the results header (§8.1), humanized. */
  displayLabel: string | null;
}

/** Title-case a snake/kebab token: "mainstream_buyers" → "Mainstream Buyers". */
export function humanizeDisplayLabel(raw: string): string {
  return raw
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Parse the sentiment deep-link params. Pass an explicit `search` string in
 * tests; in the browser it defaults to `window.location.search`.
 */
export function readSentimentDeepLink(search?: string): SentimentDeepLink {
  const qs =
    search ?? (typeof window !== "undefined" ? window.location.search : "");
  let params: URLSearchParams;
  try {
    params = new URLSearchParams(qs);
  } catch {
    return { toolkitId: null, autorun: false, displayLabel: null };
  }
  const display = params.get("display");
  return {
    toolkitId: params.get("toolkit") || null,
    autorun: params.get("autorun") === "1",
    displayLabel: display ? humanizeDisplayLabel(display) : null,
  };
}
