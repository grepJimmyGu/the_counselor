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

export function IndicesHeroSkeleton() {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="rounded-xl border border-border bg-white p-4 lg:col-span-2">
        <Skeleton className="h-4 w-24 mb-2" />
        <Skeleton className="h-10 w-32 mb-3" />
        <Skeleton className="h-[200px] w-full" />
      </div>
      <div className="flex flex-col gap-2">
        <IndexRowSkeleton />
        <IndexRowSkeleton />
        <IndexRowSkeleton />
      </div>
    </div>
  );
}

function IndexRowSkeleton() {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-white p-3.5">
      <div className="space-y-1">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-3 w-20" />
      </div>
      <div className="text-right space-y-1">
        <Skeleton className="h-4 w-16 ml-auto" />
        <Skeleton className="h-3 w-12 ml-auto" />
      </div>
    </div>
  );
}

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

export function MoverRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg">
      <Skeleton className="h-5 w-14" />
      <Skeleton className="h-5 flex-1" />
      <Skeleton className="h-5 w-16" />
      <Skeleton className="h-5 w-12" />
      <Skeleton className="h-5 w-20" />
    </div>
  );
}

export function TopMoversSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-1 rounded-xl border border-border bg-white p-2">
      {Array.from({ length: rows }).map((_, i) => (
        <MoverRowSkeleton key={i} />
      ))}
    </div>
  );
}
