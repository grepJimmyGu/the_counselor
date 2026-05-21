"use client";

import Link from "next/link";
import type { Route } from "next";
import { cn } from "@/lib/utils";
import type { SectorCard } from "@/lib/contracts";
import { fmtPct } from "@/lib/market-pulse-format";

/**
 * Section 3 — Sector table (detail view).
 *
 * Lifted from the current `_market-pulse.tsx` SectorFlowRow with one
 * addition: a Vol Ratio column. The `volume_ratio` field was computed
 * by the backend but never rendered anywhere in the UI. Now it is —
 * net info gain at zero new backend cost.
 *
 * Desktop: 6-column table layout. Mobile: 2-line card layout (same
 * pattern as the previous implementation; preserved for parity).
 */

export function SectorTable({ sectors }: { sectors: SectorCard[] }) {
  if (!sectors?.length) return null;

  return (
    <div className="rounded-xl border border-border bg-white">
      {/* Desktop header */}
      <div className="hidden sm:grid grid-cols-[2rem_1fr_5rem_4rem_4rem_7rem] items-center gap-3 border-b border-border/60 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="text-right">#</span>
        <span>Sector</span>
        <span className="text-right">1D</span>
        <span className="text-right">RS 5D</span>
        <span className="text-right">Vol</span>
        <span>CMF flow</span>
      </div>

      <div className="divide-y divide-border/60">
        {sectors.map((s, i) => (
          <SectorRow key={s.symbol} sector={s} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}

function SectorRow({ sector, rank }: { sector: SectorCard; rank: number }) {
  const volStr =
    sector.volume_ratio == null ? "—" : `${sector.volume_ratio.toFixed(2)}×`;
  const volElevated = sector.volume_ratio != null && sector.volume_ratio > 1.15;

  return (
    <Link href={`/stocks/${sector.symbol}` as Route} className="block">
      {/* Desktop */}
      <div className="hidden sm:grid grid-cols-[2rem_1fr_5rem_4rem_4rem_7rem] items-center gap-3 px-3 py-2.5 min-h-[44px] transition-colors hover:bg-muted/40">
        <span className="text-[10px] font-mono text-muted-foreground text-right">
          {rank}
        </span>
        <div className="min-w-0">
          <div className="text-xs font-semibold truncate">{sector.name}</div>
          <div className="font-mono text-[10px] text-muted-foreground">
            {sector.symbol}
          </div>
        </div>
        <PerfBadge value={sector.perf_1d} />
        <RsCell value={sector.rs_vs_spy_5d} />
        <span
          className={cn(
            "font-mono text-[11px] tabular-nums text-right",
            volElevated ? "text-amber-700 font-semibold" : "text-muted-foreground",
          )}
        >
          {volStr}
        </span>
        <CMFBar value={sector.cmf_20} />
      </div>

      {/* Mobile */}
      <div className="sm:hidden flex items-center gap-3 px-3 py-3 min-h-[56px] transition-colors hover:bg-muted/40">
        <span className="text-[10px] font-mono text-muted-foreground w-4 shrink-0 text-right">
          {rank}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold truncate">{sector.name}</span>
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">
              {sector.symbol}
            </span>
          </div>
          <div className="mt-1 w-full">
            <CMFBar value={sector.cmf_20} />
          </div>
        </div>
        <div className="shrink-0 text-right">
          <PerfBadge value={sector.perf_1d} />
          {sector.rs_vs_spy_5d != null && (
            <div
              className={cn(
                "font-mono text-[10px] mt-0.5",
                sector.rs_vs_spy_5d > 0 ? "text-emerald-600" : "text-red-500",
              )}
            >
              {sector.rs_vs_spy_5d >= 0 ? "+" : ""}
              {(sector.rs_vs_spy_5d * 100).toFixed(1)}%
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

function PerfBadge({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return (
      <span className="font-mono text-xs text-muted-foreground text-right">—</span>
    );
  }
  return (
    <span
      className={cn(
        "font-mono text-xs font-semibold tabular-nums text-right",
        value > 0 ? "text-emerald-600" : value < 0 ? "text-red-500" : "text-muted-foreground",
      )}
    >
      {fmtPct(value)}
    </span>
  );
}

function RsCell({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return (
      <span className="font-mono text-[10px] text-muted-foreground text-right">
        —
      </span>
    );
  }
  return (
    <span
      className={cn(
        "font-mono text-[11px] font-medium tabular-nums text-right",
        value > 0 ? "text-emerald-600" : "text-red-500",
      )}
    >
      {value >= 0 ? "+" : ""}
      {(value * 100).toFixed(1)}%
    </span>
  );
}

function CMFBar({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return <div className="text-[10px] text-muted-foreground font-mono">—</div>;
  }
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const isPositive = value >= 0;
  const barPct = (Math.abs(clamped) / 0.5) * 50;

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "font-mono text-[11px] font-semibold tabular-nums",
            isPositive ? "text-emerald-600" : "text-red-500",
          )}
        >
          {value >= 0 ? "+" : ""}
          {value.toFixed(3)}
        </span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="absolute left-0 top-0 h-full w-1/2 overflow-hidden">
          {!isPositive && (
            <div
              className="absolute right-0 top-0 h-full bg-red-500 transition-all duration-500"
              style={{ width: `${barPct * 2}%` }}
            />
          )}
        </div>
        <div className="absolute right-0 top-0 h-full w-1/2 overflow-hidden">
          {isPositive && (
            <div
              className="absolute left-0 top-0 h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${barPct * 2}%` }}
            />
          )}
        </div>
        <div className="absolute left-1/2 top-0 h-full w-px bg-border/60" />
      </div>
    </div>
  );
}
