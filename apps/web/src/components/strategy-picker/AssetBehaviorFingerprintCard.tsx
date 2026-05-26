"use client";

/**
 * AssetBehaviorFingerprintCard — Module 2 (2026-05-26).
 *
 * Diagnostic card that helps users understand how an asset has tended to
 * behave BEFORE they pick a strategy template. Surfaces:
 *
 *   • Symbol + asset type (single stock / sector ETF / commodity / ...)
 *   • Current regime (trending / range_bound / volatile / mixed)
 *   • Trending vs. mean-reverting behaviour as percentages
 *   • 1-year and 5-year annualised volatility
 *   • 5-year max drawdown
 *   • Data quality bucket
 *   • Plain-English implication for strategy family selection
 *
 * Design constraints (per spec):
 *   - No buy/sell verbs. No forward-looking claims.
 *   - "Not enough data" instead of crashing on null metrics.
 *   - Insufficient-data state shows a clear amber warning + still renders
 *     the symbol + asset type so the user knows what was looked up.
 *   - Reusable: either pass `symbol` and the component fetches itself, or
 *     pass a pre-fetched `fingerprint` (useful for SSR / parent-managed
 *     loading states).
 */

import { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDown, ArrowUp,
  BarChart3, Loader2, Repeat, TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getAssetBehavior } from "@/lib/api";
import type {
  AssetBehaviorFingerprint,
  AssetType,
  CurrentRegime,
  DataQuality,
} from "@/lib/contracts";

// ── Label maps — keep all jargon-to-plain-English here ─────────────────────

const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  single_stock:  "Single stock",
  commodity_etf: "Commodity ETF",
  broad_etf:     "Broad market ETF",
  sector_etf:    "Sector ETF",
  pair:          "Pair of assets",
  basket:        "Basket of assets",
  unknown:       "Unclassified",
};

const REGIME_LABEL: Record<CurrentRegime, string> = {
  trending:    "Trending",
  range_bound: "Range-bound",
  volatile:    "Volatile",
  mixed:       "Mixed",
};

const REGIME_BADGE: Record<CurrentRegime, string> = {
  trending:    "border-emerald-300 bg-emerald-50 text-emerald-800",
  range_bound: "border-sky-300 bg-sky-50 text-sky-800",
  volatile:    "border-amber-300 bg-amber-50 text-amber-900",
  mixed:       "border-border bg-muted/30 text-foreground/70",
};

const DATA_QUALITY_LABEL: Record<DataQuality, string> = {
  good:         "Good — 3+ years of daily data",
  limited:      "Limited — 1 to 3 years of daily data",
  insufficient: "Insufficient — less than 1 year of daily data",
};

const DATA_QUALITY_BADGE: Record<DataQuality, string> = {
  good:         "border-emerald-300 bg-emerald-50 text-emerald-800",
  limited:      "border-amber-300 bg-amber-50 text-amber-900",
  insufficient: "border-rose-300 bg-rose-50 text-rose-900",
};

// ── Formatting helpers ─────────────────────────────────────────────────────

function fmtPct(value: number | null, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Not enough data";
  return `${value.toFixed(digits)}%`;
}

function fmtVol(value: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Not enough data";
  // Service returns annualised stdev as a decimal (0.18 = 18%).
  return `${(value * 100).toFixed(1)}%`;
}

function fmtDrawdown(value: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Not enough data";
  // Drawdown is a negative decimal; flip the sign for display.
  return `${(value * 100).toFixed(1)}%`;
}

function trendingPlainLabel(pct: number | null): string {
  if (pct === null) return "Not enough data";
  if (pct >= 70) return "Frequently trending";
  if (pct >= 50) return "Often trending";
  if (pct >= 30) return "Sometimes trending";
  return "Rarely trending";
}

function meanRevertingPlainLabel(pct: number | null): string {
  if (pct === null) return "Not enough data";
  if (pct >= 70) return "Frequently reverts after extremes";
  if (pct >= 50) return "Often reverts after extremes";
  if (pct >= 30) return "Sometimes reverts after extremes";
  return "Rarely reverts after extremes";
}

// ── Component props ────────────────────────────────────────────────────────

export interface AssetBehaviorFingerprintCardProps {
  /** Provide either `symbol` (the card fetches itself) or `fingerprint`
   *  (pre-fetched payload — useful for SSR / parent-managed loading). */
  symbol?: string;
  fingerprint?: AssetBehaviorFingerprint;
  className?: string;
}

// ── Component ──────────────────────────────────────────────────────────────

export function AssetBehaviorFingerprintCard({
  symbol,
  fingerprint: passedFingerprint,
  className,
}: AssetBehaviorFingerprintCardProps): React.ReactElement {
  const [data, setData] = useState<AssetBehaviorFingerprint | null>(passedFingerprint ?? null);
  const [loading, setLoading] = useState<boolean>(!passedFingerprint && !!symbol);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Self-fetch when only `symbol` is provided.
    if (passedFingerprint || !symbol) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getAssetBehavior(symbol)
      .then((fp) => { if (!cancelled) setData(fp); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load behavior fingerprint.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, passedFingerprint]);

  // ── Loading state ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className={cn(
          "rounded-2xl border border-border bg-card p-5 shadow-sm",
          className,
        )}
        role="status"
        aria-busy="true"
      >
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading {symbol ? symbol.toUpperCase() : "asset"} behavior fingerprint…
        </div>
      </div>
    );
  }

  // ── Error state ──────────────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div
        className={cn(
          "rounded-2xl border border-rose-200 bg-rose-50 p-5",
          className,
        )}
        role="alert"
      >
        <div className="flex items-start gap-2 text-sm text-rose-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Couldn&apos;t load behavior fingerprint.</p>
            <p className="mt-0.5 text-xs text-rose-900/80">
              {error || "Try refreshing in a moment, or pick a different ticker."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const insufficient = data.data_quality === "insufficient";

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-border bg-card shadow-sm",
        className,
      )}
      data-testid="asset-behavior-fingerprint-card"
    >
      {/* Header — symbol + asset type + regime + data-quality badges */}
      <div className="border-b border-border bg-gradient-to-br from-primary/5 via-transparent to-transparent px-5 pt-5 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Asset behavior fingerprint
            </p>
            <h3 className="mt-1 font-heading text-xl font-bold tracking-tight">
              {data.symbol} <span className="text-sm font-normal text-muted-foreground">behavior summary</span>
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {ASSET_TYPE_LABEL[data.asset_type] ?? "Unclassified"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                REGIME_BADGE[data.current_regime],
              )}
              title="Current regime, inferred from the last year of price action"
            >
              {REGIME_LABEL[data.current_regime]}
            </span>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                DATA_QUALITY_BADGE[data.data_quality],
              )}
            >
              {data.data_quality === "good" ? "3y+ data" :
               data.data_quality === "limited" ? "Limited data" :
               "Insufficient data"}
            </span>
          </div>
        </div>
      </div>

      {/* Insufficient-data warning banner */}
      {insufficient && (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-3">
          <div className="flex items-start gap-2 text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>
              <strong>Limited history available.</strong>{" "}
              Some metrics below are shown as &ldquo;Not enough data&rdquo;. The implication is generic until more history is loaded.
            </span>
          </div>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-1 divide-y divide-border/60 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
        <div className="space-y-3 p-5">
          <Metric
            icon={<TrendingUp className="h-3.5 w-3.5" />}
            label="Trending behavior"
            primary={trendingPlainLabel(data.trending_pct)}
            secondary={data.trending_pct === null
              ? undefined
              : `${fmtPct(data.trending_pct)} of 200-day windows`}
          />
          <Metric
            icon={<Repeat className="h-3.5 w-3.5" />}
            label="Mean-reversion behavior"
            primary={meanRevertingPlainLabel(data.mean_reverting_pct)}
            secondary={data.mean_reverting_pct === null
              ? undefined
              : `${fmtPct(data.mean_reverting_pct)} of extreme events reverted within 10 days`}
          />
        </div>
        <div className="space-y-3 p-5">
          <Metric
            icon={<Activity className="h-3.5 w-3.5" />}
            label="1-year realised volatility"
            primary={fmtVol(data.realized_vol_1y)}
            secondary={data.realized_vol_1y === null ? undefined : "Annualised stdev of daily returns"}
          />
          <Metric
            icon={<BarChart3 className="h-3.5 w-3.5" />}
            label="5-year realised volatility"
            primary={fmtVol(data.realized_vol_5y)}
            secondary={data.realized_vol_5y === null ? undefined : "Long-run baseline for comparison"}
          />
          <Metric
            icon={<ArrowDown className="h-3.5 w-3.5" />}
            label="5-year max drawdown"
            primary={fmtDrawdown(data.max_drawdown_5y)}
            secondary={data.max_drawdown_5y === null
              ? undefined
              : "Worst peak-to-trough loss in the period"}
            tone={data.max_drawdown_5y === null ? "neutral" : "warn"}
          />
        </div>
      </div>

      {/* Strategy implication footer */}
      <div className="border-t border-border bg-muted/20 px-5 py-4">
        <div className="flex items-start gap-2">
          <ArrowUp className="mt-0.5 h-4 w-4 rotate-45 text-primary" aria-hidden="true" />
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Strategy implication
            </p>
            <p className="mt-1 text-sm leading-relaxed text-foreground/90">
              {data.strategy_implication}
            </p>
            <p className="mt-2 text-[11px] italic text-muted-foreground">
              For strategy selection only — not investment advice or a prediction of future returns.
            </p>
          </div>
        </div>
      </div>

      {/* Footer — data-quality fine print */}
      <div className="border-t border-border bg-muted/10 px-5 py-2 text-[11px] text-muted-foreground">
        Data quality: <span className="font-medium text-foreground/70">{DATA_QUALITY_LABEL[data.data_quality]}</span>
      </div>
    </div>
  );
}

// ── Small row helper ───────────────────────────────────────────────────────

function Metric({
  icon, label, primary, secondary, tone = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  primary: string;
  secondary?: string;
  tone?: "neutral" | "warn";
}): React.ReactElement {
  const primaryEmpty = primary === "Not enough data";
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        <span className="text-muted-foreground/70" aria-hidden="true">{icon}</span>
        {label}
      </div>
      <p
        className={cn(
          "mt-0.5 text-sm font-semibold leading-snug",
          primaryEmpty ? "text-muted-foreground/70 italic font-normal" :
          tone === "warn" ? "text-rose-700" : "text-foreground",
        )}
      >
        {primary}
      </p>
      {secondary && (
        <p className="text-[11px] text-muted-foreground/80 leading-snug">{secondary}</p>
      )}
    </div>
  );
}
