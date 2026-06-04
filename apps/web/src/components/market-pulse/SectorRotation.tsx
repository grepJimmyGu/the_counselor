"use client";

import { useMemo, useState } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SectorCard } from "@/lib/contracts";
import { useMarketCopy } from "@/lib/market-copy";
import { SectorHeatmap } from "./SectorHeatmap";
import { SectorTable } from "./SectorTable";
import { SectorComparisonChart } from "./SectorComparisonChart";

/**
 * Section 3 — Sector Rotation container.
 *
 * - Interpretive one-line headline above the visualization. Phase 0 uses
 *   the deterministic narrative (`sectorRotation` from buildNarrative);
 *   Phase 1 will swap to the LLM-generated sentence from
 *   `data.narrative.sector_rotation`.
 * - Heatmap-default / table-toggle. Heatmap fronts perf_1d for retail
 *   intuition; table view preserves the CMF-sorted analyst surface.
 * - Sort dropdown (heatmap view only) re-orders client-side.
 */

type View = "heatmap" | "table";
type Sort = "cmf" | "perf_1d" | "rs_vs_spy";

export function SectorRotation({
  sectors,
  rotationHeadline,
  market = "US" as "US" | "CN",
}: {
  sectors: SectorCard[];
  rotationHeadline?: string;
  market?: "US" | "CN";
}) {
  const t = (key: string) => useMarketCopy(key, market);
  const [view, setView] = useState<View>("heatmap");
  const [sort, setSort] = useState<Sort>("cmf");
  // Per 2026-05-21 feedback: click a heatmap tile → expand inline below
  // with a sector ETF vs S&P 500 comparison chart + returns table.
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);

  const sorted = useMemo(() => sortSectors(sectors, sort), [sectors, sort]);
  const activeSector = sorted.find((s) => s.symbol === activeSymbol) ?? null;

  return (
    <section id="sectors" aria-labelledby="sectors-heading" className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2
            id="sectors-heading"
            className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
          >
            {t("sectors_heading")}
          </h2>
          {rotationHeadline && (
            <p className="mt-1 text-sm text-foreground/80">{rotationHeadline}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {view === "heatmap" && (
            <select
              aria-label="Sort sectors by"
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              className="rounded-md border border-border bg-white px-2 py-1 text-xs focus-visible:outline-2 focus-visible:outline-primary"
            >
              <option value="cmf">Sort: CMF flow</option>
              <option value="perf_1d">Sort: 1D performance</option>
              <option value="rs_vs_spy">Sort: RS vs SPY (5D)</option>
            </select>
          )}
          <Tabs value={view} onValueChange={(v) => setView(v as View)}>
            <TabsList className="h-7">
              <TabsTrigger value="heatmap" className="text-xs px-2.5">
                Heatmap
              </TabsTrigger>
              <TabsTrigger value="table" className="text-xs px-2.5">
                Table
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {view === "heatmap" ? (
        <>
          <SectorHeatmap
            sectors={sorted}
            activeSymbol={activeSymbol}
            onTileClick={(sym) =>
              setActiveSymbol((current) => (current === sym ? null : sym))
            }
          />
          {activeSector && (
            <SectorComparisonChart
              sector={activeSector}
              onClose={() => setActiveSymbol(null)}
            />
          )}
        </>
      ) : (
        <SectorTable sectors={sorted} />
      )}
    </section>
  );
}

function sortSectors(sectors: SectorCard[], sort: Sort): SectorCard[] {
  const arr = [...sectors];
  if (sort === "cmf") {
    return arr.sort((a, b) => (b.cmf_20 ?? -Infinity) - (a.cmf_20 ?? -Infinity));
  }
  if (sort === "perf_1d") {
    return arr.sort(
      (a, b) => (b.perf_1d ?? -Infinity) - (a.perf_1d ?? -Infinity),
    );
  }
  return arr.sort(
    (a, b) => (b.rs_vs_spy_5d ?? -Infinity) - (a.rs_vs_spy_5d ?? -Infinity),
  );
}
