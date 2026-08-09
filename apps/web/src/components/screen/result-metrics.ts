/**
 * Column definitions for the query-results table.
 *
 * Two kinds of column, and the distinction matters:
 *
 *   DEFAULT   — always present regardless of what was screened. Price, change,
 *               market cap, volume. These are what make a row read as a STOCK
 *               rather than a score; without them the table is a lookup sheet.
 *   CONDITION — one per screened condition, carrying that name's actual value.
 *               Derived at runtime from the query, so not listed here.
 *
 * A third kind (optional metrics the user adds) is grouped below. Grouping is
 * by where the number COMES FROM, because that's what determines whether we
 * can show it at all: quote fields are free (already fetched), fundamentals
 * come from `symbols`, technicals from the daily snapshot.
 */

import type { LiveQuote } from "@/lib/useLiveQuotes";

export type MetricSource = "quote" | "fundamental" | "technical";

export interface MetricDef {
  key: string;
  label: string;
  source: MetricSource;
  /** Right-aligned numerics vs left-aligned text. */
  align?: "left" | "right";
  format: (v: number | null | undefined) => string;
}

/** Compact money: 4.6T, 812.3B, 45.2M. Full digits are unreadable at a glance
 *  and the exact figure is on the stock page anyway. */
export function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(2);
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function num(v: number | null | undefined, dp = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(dp);
}

/** Always shown. Jimmy's spec: price, change %, market value, volume. */
export const DEFAULT_METRICS: MetricDef[] = [
  { key: "price", label: "Price", source: "quote", align: "right", format: (v) => num(v) },
  { key: "change_percent", label: "Change %", source: "quote", align: "right", format: pct },
  { key: "market_cap", label: "Market cap", source: "quote", align: "right", format: money },
  { key: "volume", label: "Volume", source: "quote", align: "right", format: money },
];

/**
 * Optional metrics, grouped for the picker.
 *
 * Only metrics we can actually source are listed. A picker offering a field we
 * can't fill produces a column of em dashes, which reads as broken data rather
 * than as an unavailable metric — worse than not offering it.
 */
export const METRIC_GROUPS: { key: string; label: string; metrics: MetricDef[] }[] = [
  {
    key: "quote",
    label: "Price & volume",
    metrics: [
      { key: "day_high", label: "Day high", source: "quote", align: "right", format: (v) => num(v) },
      { key: "day_low", label: "Day low", source: "quote", align: "right", format: (v) => num(v) },
      { key: "change", label: "Change", source: "quote", align: "right", format: (v) => num(v) },
    ],
  },
  {
    key: "fundamental",
    label: "Fundamentals",
    metrics: [
      { key: "pe_ratio", label: "P/E", source: "fundamental", align: "right", format: (v) => num(v) },
      {
        key: "dividend_yield",
        label: "Div yield",
        source: "fundamental",
        align: "right",
        // Stored as a FRACTION (0.0071 = 0.71%) — see the dividend-units fix.
        format: (v) =>
          v === null || v === undefined || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(2)}%`,
      },
      { key: "beta", label: "Beta", source: "fundamental", align: "right", format: (v) => num(v) },
      { key: "week_52_high", label: "52w high", source: "fundamental", align: "right", format: (v) => num(v) },
      { key: "week_52_low", label: "52w low", source: "fundamental", align: "right", format: (v) => num(v) },
    ],
  },
];

export const ALL_OPTIONAL_METRICS: MetricDef[] = METRIC_GROUPS.flatMap((g) => g.metrics);

/** Pull a metric off whichever source holds it. */
export function readMetric(
  key: string,
  quote: LiveQuote | undefined,
  fundamentals: Record<string, number | null> | undefined,
  conditionValues: Record<string, number> | undefined,
): number | null | undefined {
  if (conditionValues && key in conditionValues) return conditionValues[key];
  if (quote && key in quote) return (quote as unknown as Record<string, number | null>)[key];
  if (fundamentals && key in fundamentals) return fundamentals[key];
  return undefined;
}
