"use client";

import Link from "next/link";
import type { Route } from "next";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { SectorCard } from "@/lib/contracts";
import { fmtPct, interpretCmf } from "@/lib/market-pulse-format";

/**
 * Section 3 — Sector heatmap view (2 rows × 6+5 tiles on desktop).
 *
 * Revised 2026-05-21 per Jimmy's feedback ("sector rotation heatmap can
 * be in 2 rows with each grid having metrics number shown"). Each tile
 * is bigger now (~140×100px on desktop) and shows 5 metrics directly:
 *   1. Sector name (top, semibold) + symbol below in mono
 *   2. perf_1d (large, color-coded against tile background)
 *   3. perf_5d (smaller, secondary)
 *   4. CMF mini-bar (bottom, full-width)
 *   5. volume_ratio chip (only when elevated, e.g. >1.15×)
 *
 * Tile background color-interpolated by perf_1d (diverging emerald↔red,
 * clamped at ±1.5%). Click → /stocks/{symbol}. Hover (desktop) →
 * tooltip with the same 5 metrics + interpretation chip; tooltip is
 * now mostly redundant with the visible numbers but kept for the
 * `interpretCmf` label and screen-reader users.
 */

const CLAMP = 0.015; // ±1.5% — matches the "tuning knob" decision in the plan.

export function SectorHeatmap({ sectors }: { sectors: SectorCard[] }) {
  if (!sectors?.length) return null;

  return (
    <TooltipProvider delayDuration={200}>
      <div
        // Mobile: 2 cols → ~6 rows; tablet: 3 cols; desktop: 6 cols (so 11
        // tiles split 6 + 5 across two rows).
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2"
        role="list"
        aria-label="Sector performance heatmap"
      >
        {sectors.map((s) => (
          <SectorTile key={s.symbol} sector={s} />
        ))}
      </div>
    </TooltipProvider>
  );
}

function SectorTile({ sector }: { sector: SectorCard }) {
  const perf = sector.perf_1d;
  const { backgroundColor, textColor, mutedTextColor } = tileColors(perf);
  const cmfRead = interpretCmf(sector.cmf_20);
  const ariaLabel = [
    sector.name,
    perf != null ? `${fmtPct(perf)} today` : "no data",
    sector.perf_5d != null ? `5-day ${fmtPct(sector.perf_5d)}` : "",
    cmfRead.label.toLowerCase(),
    sector.volume_ratio != null && sector.volume_ratio > 1.15
      ? `volume ${sector.volume_ratio.toFixed(1)}x elevated`
      : "",
  ]
    .filter(Boolean)
    .join(", ");

  const showVolChip = sector.volume_ratio != null && sector.volume_ratio > 1.15;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={`/stocks/${sector.symbol}` as Route}
          role="listitem"
          aria-label={ariaLabel}
          className="block min-h-[104px] rounded-lg p-3 transition-transform hover:scale-[1.02] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          style={{ backgroundColor, color: textColor }}
        >
          {/* Row 1 — name + symbol */}
          <div className="flex items-baseline justify-between gap-1 min-w-0">
            <div
              className="text-[11px] font-semibold leading-tight truncate"
              title={sector.name}
            >
              {shortSectorName(sector.name)}
            </div>
            <div
              className="font-mono text-[10px] shrink-0"
              style={{ color: mutedTextColor }}
            >
              {sector.symbol}
            </div>
          </div>

          {/* Row 2 — perf_1d big, perf_5d smaller */}
          <div className="mt-1 flex items-baseline gap-2">
            <div className="font-mono text-lg font-bold tabular-nums leading-none">
              {perf != null ? fmtPct(perf, 1) : "—"}
            </div>
            {sector.perf_5d != null && (
              <div
                className="font-mono text-[10px] tabular-nums"
                style={{ color: mutedTextColor }}
              >
                5D {fmtPct(sector.perf_5d, 1)}
              </div>
            )}
          </div>

          {/* Row 3 — CMF mini-bar + optional volume chip */}
          <div className="mt-2 flex items-center gap-1.5">
            <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-black/15">
              <CmfMiniBar value={sector.cmf_20} />
            </div>
            {showVolChip && (
              <span
                className="rounded-full px-1.5 py-0.5 font-mono text-[9px] font-medium"
                style={{
                  backgroundColor: "rgba(0,0,0,0.18)",
                  color: textColor,
                }}
                title={`Volume ratio ${sector.volume_ratio!.toFixed(2)}×`}
              >
                {sector.volume_ratio!.toFixed(1)}×
              </span>
            )}
          </div>
        </Link>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[240px]">
        <div className="space-y-1 text-xs">
          <div className="font-semibold">{sector.name} ({sector.symbol})</div>
          <div className="text-muted-foreground">
            1D: {fmtPct(sector.perf_1d)} · 5D: {fmtPct(sector.perf_5d)}
          </div>
          <div className="text-muted-foreground">
            CMF: {sector.cmf_20?.toFixed(2) ?? "—"} ({cmfRead.label})
          </div>
          <div className="text-muted-foreground">
            RS vs SPY (5D): {fmtPct(sector.rs_vs_spy_5d)}
          </div>
          {sector.volume_ratio != null && (
            <div className="text-muted-foreground">
              Vol ratio: {sector.volume_ratio.toFixed(2)}×
              {sector.volume_ratio > 1.15 ? " (elevated)" : ""}
            </div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

// ── Color interpolation ───────────────────────────────────────────────────────

function tileColors(perf: number | null | undefined): {
  backgroundColor: string;
  textColor: string;
  mutedTextColor: string;
} {
  if (perf == null)
    return {
      backgroundColor: "#f3f4f6",
      textColor: "#6b7280",
      mutedTextColor: "#9ca3af",
    };
  const clamped = Math.max(-CLAMP, Math.min(CLAMP, perf));
  const intensity = Math.abs(clamped) / CLAMP; // 0..1

  if (perf >= 0) {
    // Light emerald (0.0) → dark emerald (1.0)
    const rgb = lerpRgb([209, 250, 229], [5, 150, 105], intensity);
    const onDark = intensity > 0.55;
    return {
      backgroundColor: `rgb(${rgb.join(",")})`,
      textColor: onDark ? "#ffffff" : "#064e3b",
      mutedTextColor: onDark ? "rgba(255,255,255,0.75)" : "#065f46",
    };
  }
  // Light red → dark red
  const rgb = lerpRgb([254, 226, 226], [220, 38, 38], intensity);
  const onDark = intensity > 0.55;
  return {
    backgroundColor: `rgb(${rgb.join(",")})`,
    textColor: onDark ? "#ffffff" : "#7f1d1d",
    mutedTextColor: onDark ? "rgba(255,255,255,0.75)" : "#991b1b",
  };
}

function lerpRgb(
  from: [number, number, number],
  to: [number, number, number],
  t: number,
): [number, number, number] {
  return [
    Math.round(from[0] + (to[0] - from[0]) * t),
    Math.round(from[1] + (to[1] - from[1]) * t),
    Math.round(from[2] + (to[2] - from[2]) * t),
  ];
}

function shortSectorName(name: string): string {
  // Strip "Sector" / "Select Sector SPDR Fund" common suffixes for tile compactness.
  return name
    .replace(/select sector spdr fund/i, "")
    .replace(/sector/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

// ── CMF mini-bar (1px-tall, no text) ──────────────────────────────────────────

function CmfMiniBar({ value }: { value: number | null | undefined }) {
  if (value == null) return null;
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const isUp = value >= 0;
  const pct = (Math.abs(clamped) / 0.5) * 50; // 0..50% of half-width
  return (
    <div className="relative h-full w-full">
      <div className="absolute left-1/2 top-0 h-full w-px bg-black/20" />
      <div
        className={cn(
          "absolute top-0 h-full",
          isUp ? "left-1/2 bg-emerald-700" : "right-1/2 bg-red-700",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
