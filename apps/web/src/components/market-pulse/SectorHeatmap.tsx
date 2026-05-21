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
 * Section 3 — Sector heatmap view.
 *
 * 11 sector tiles, each color-interpolated by `perf_1d` on a diverging
 * emerald↔red scale clamped at ±1.5%. Click → /stocks/{symbol}. Hover
 * (desktop) → tooltip with CMF + RS vs SPY + volume_ratio (the
 * previously-orphaned backend field finally surfaces here).
 *
 * Tile aria-label embeds the plain-English read so screen readers
 * don't depend on color alone.
 */

const CLAMP = 0.015; // ±1.5% — matches the "tuning knob" decision in the plan.

export function SectorHeatmap({ sectors }: { sectors: SectorCard[] }) {
  if (!sectors?.length) return null;

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-11 gap-1.5"
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
  const { backgroundColor, textColor } = tileColors(perf);
  const cmfRead = interpretCmf(sector.cmf_20);
  const ariaLabel = [
    sector.name,
    perf != null ? `${fmtPct(perf)} today` : "no data",
    cmfRead.label.toLowerCase(),
  ].join(", ");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={`/stocks/${sector.symbol}` as Route}
          role="listitem"
          aria-label={ariaLabel}
          className="block rounded-md p-2 transition-transform hover:scale-[1.03] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          style={{ backgroundColor, color: textColor }}
        >
          <div className="text-[10px] font-semibold leading-tight truncate">
            {shortSectorName(sector.name)}
          </div>
          <div className="mt-1 font-mono text-base font-bold tabular-nums">
            {perf != null ? fmtPct(perf, 1) : "—"}
          </div>
          <div className="mt-1 h-1 rounded-full overflow-hidden bg-black/15">
            <CmfMiniBar value={sector.cmf_20} />
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
} {
  if (perf == null) return { backgroundColor: "#f3f4f6", textColor: "#6b7280" };
  const clamped = Math.max(-CLAMP, Math.min(CLAMP, perf));
  const intensity = Math.abs(clamped) / CLAMP; // 0..1

  if (perf >= 0) {
    // Light emerald (0.05) → dark emerald (1.0)
    const rgb = lerpRgb([209, 250, 229], [5, 150, 105], intensity);
    const textColor = intensity > 0.55 ? "#ffffff" : "#064e3b";
    return { backgroundColor: `rgb(${rgb.join(",")})`, textColor };
  }
  // Light red → dark red
  const rgb = lerpRgb([254, 226, 226], [220, 38, 38], intensity);
  const textColor = intensity > 0.55 ? "#ffffff" : "#7f1d1d";
  return { backgroundColor: `rgb(${rgb.join(",")})`, textColor };
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
