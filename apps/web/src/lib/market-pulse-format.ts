/**
 * Shared formatters for Market Pulse surfaces.
 *
 * Single source of truth — previously each card subcomponent inside
 * `_market-pulse.tsx` redefined these helpers. Lifting them here makes
 * the new market-pulse/* components consistent and lets us unit-test
 * edge cases like null inputs and CMF thresholds.
 */

/** Formats a decimal perf (0.0028 → "+0.28%"). Returns "—" for null. */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  const s = (v * 100).toFixed(digits);
  return v >= 0 ? `+${s}%` : `${s}%`;
}

/** Formats a price (123.45 → "$123.45"). Returns "—" for null. */
export function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${v.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Formats an ISO date "2026-05-20" → "May 20". Empty for null/invalid. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(`${iso}T00:00:00`);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/** Formats a market cap in human units (1.2e12 → "$1.2T"). */
export function fmtMktCap(v: number | null | undefined): string {
  if (v == null) return "";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  return `$${(v / 1e6).toFixed(0)}M`;
}

// ── CMF interpretation ────────────────────────────────────────────────────────

/**
 * Plain-English interpretation of a Chaikin Money Flow value.
 *
 * Thresholds derived from the CMF range observed in the Livermore dataset
 * (typical: −0.3 to +0.3). Powers the `SignalChip` component on sector
 * tiles, sector table tooltips, and Mover row hover.
 */
export type CmfBand =
  | "strong_inflow"
  | "mild_inflow"
  | "neutral"
  | "mild_outflow"
  | "strong_outflow"
  | "unknown";

export interface CmfInterpretation {
  band: CmfBand;
  label: string;
  /** Tailwind class to color the chip background. */
  colorClass: string;
}

export function interpretCmf(v: number | null | undefined): CmfInterpretation {
  if (v == null || Number.isNaN(v)) {
    return {
      band: "unknown",
      label: "No data",
      colorClass: "bg-muted text-muted-foreground",
    };
  }
  if (v >= 0.2) {
    return {
      band: "strong_inflow",
      label: "Strong inflow",
      colorClass: "bg-emerald-600 text-white",
    };
  }
  if (v >= 0.05) {
    return {
      band: "mild_inflow",
      label: "Mild inflow",
      colorClass: "bg-emerald-100 text-emerald-800",
    };
  }
  if (v > -0.05) {
    return {
      band: "neutral",
      label: "Neutral",
      colorClass: "bg-muted text-muted-foreground",
    };
  }
  if (v > -0.2) {
    return {
      band: "mild_outflow",
      label: "Mild outflow",
      colorClass: "bg-red-100 text-red-800",
    };
  }
  return {
    band: "strong_outflow",
    label: "Strong outflow",
    colorClass: "bg-red-600 text-white",
  };
}
