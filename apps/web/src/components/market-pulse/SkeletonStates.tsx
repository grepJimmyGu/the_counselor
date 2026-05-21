"use client";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * Centralized loading placeholders for the redesigned Market Pulse.
 *
 * Each skeleton matches the final-state component's layout closely enough
 * that the transition from skeleton → real content does NOT cause layout
 * shift (CLS = 0). If you change a component's structure, mirror it here.
 */

export function BriefSkeleton() {
  return (
    <div className="rounded-2xl border border-border bg-gradient-to-br from-slate-50 to-white p-6 md:p-8">
      <Skeleton className="h-7 w-3/4 mb-3" />
      <Skeleton className="h-7 w-2/3 mb-3" />
      <Skeleton className="h-7 w-1/2 mb-5" />
      <div className="flex flex-wrap gap-3">
        <Skeleton className="h-9 w-28 rounded-full" />
        <Skeleton className="h-9 w-32 rounded-full" />
        <Skeleton className="h-9 w-28 rounded-full" />
      </div>
    </div>
  );
}

// IndicesHeroSkeleton removed 2026-05-21 — the IndicesHero section was
// folded into MarketBrief as an inline 4-cell ticker. Its skeleton is
// part of BriefSkeleton if/when that needs to mirror the new layout.

export function SectorHeatmapSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <Skeleton className="h-4 w-1/2 mb-3" />
      <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-11 gap-1.5">
        {Array.from({ length: 11 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        ))}
      </div>
    </div>
  );
}

export function MacroStripSkeleton() {
  return (
    <div className="flex gap-2 overflow-hidden">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-[64px] w-[160px] shrink-0 rounded-lg" />
      ))}
    </div>
  );
}

export function MoverCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-white p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <Skeleton className="h-4 w-14" />
          <Skeleton className="h-3 w-20" />
        </div>
        <Skeleton className="h-4 w-12" />
      </div>
      <Skeleton className="h-5 w-20" />
      <Skeleton className="h-2 w-full" />
    </div>
  );
}

export function TopMoversSkeleton({ rows = 10 }: { rows?: number }) {
  // 2 rows × ~5 cols grid (cards, not rows) per the 2026-05-21 redo.
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <MoverCardSkeleton key={i} />
      ))}
    </div>
  );
}
