"use client";

import { useMemo, useState } from "react";
import type { AssetCard } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { MoverRow, type MoverRowProps } from "./MoverRow";

/**
 * Section 5 — Movers (unified ranked list).
 *
 * Replaces the previous Stocks/ETFs/Commodities tabs with one ranked
 * list plus category filter chips and a sort dropdown. Sort defaults
 * to "Top gainers" (most-natural retail framing per Yahoo / Robinhood);
 * "Most active" surfaces the `volume_ratio` field (already in
 * `AssetCard` for assets returned by the backend; falls back to mid-
 * list ordering when unavailable).
 *
 * No backend change. Source: `top_assets + featured_etfs +
 * static-commodity-array`, de-duped by symbol.
 */

export interface MoverItem {
  card: AssetCard;
  category: "Stock" | "ETF" | "Commodity";
  href: string;
}

type Filter = "all" | "stock" | "etf" | "commodity";
type Sort = "gainers" | "losers" | "active" | "cmf";

export function MoversList({ items }: { items: MoverItem[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("gainers");

  const filtered = useMemo(() => {
    const byCat =
      filter === "all"
        ? items
        : items.filter(
            (i) => i.category.toLowerCase() === filter,
          );
    return sortItems(byCat, sort);
  }, [items, filter, sort]);

  const counts = useMemo(() => countByCategory(items), [items]);

  return (
    <section id="movers" aria-labelledby="movers-heading" className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <h2
          id="movers-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Movers
        </h2>
        <select
          aria-label="Sort movers by"
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          className="rounded-md border border-border bg-white px-2 py-1 text-xs focus-visible:outline-2 focus-visible:outline-primary"
        >
          <option value="gainers">Sort: Top gainers</option>
          <option value="losers">Sort: Top losers</option>
          <option value="active">Sort: Most active (CMF flow)</option>
          <option value="cmf">Sort: CMF flow</option>
        </select>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <FilterChip
          active={filter === "all"}
          onClick={() => setFilter("all")}
          label={`All (${items.length})`}
        />
        <FilterChip
          active={filter === "stock"}
          onClick={() => setFilter("stock")}
          label={`Stocks (${counts.stock})`}
        />
        <FilterChip
          active={filter === "etf"}
          onClick={() => setFilter("etf")}
          label={`ETFs (${counts.etf})`}
        />
        <FilterChip
          active={filter === "commodity"}
          onClick={() => setFilter("commodity")}
          label={`Commodities (${counts.commodity})`}
        />
      </div>

      <div className="rounded-xl border border-border bg-white divide-y divide-border/60">
        {filtered.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-muted-foreground">
            No matches.
          </div>
        ) : (
          filtered.map(({ card, category, href }) => (
            <MoverRow
              key={`${category}-${card.symbol}`}
              card={card}
              category={category as MoverRowProps["category"]}
              href={href}
            />
          ))
        )}
      </div>
    </section>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-primary",
        active
          ? "border-primary/40 bg-primary/10 text-primary"
          : "border-border bg-white text-muted-foreground hover:bg-muted/40",
      )}
    >
      {label}
    </button>
  );
}

function countByCategory(items: MoverItem[]): {
  stock: number;
  etf: number;
  commodity: number;
} {
  return items.reduce(
    (acc, i) => {
      const k = i.category.toLowerCase() as keyof typeof acc;
      acc[k]++;
      return acc;
    },
    { stock: 0, etf: 0, commodity: 0 },
  );
}

function sortItems(items: MoverItem[], sort: Sort): MoverItem[] {
  const arr = [...items];
  if (sort === "gainers") {
    return arr.sort(
      (a, b) => (b.card.perf_1d ?? -Infinity) - (a.card.perf_1d ?? -Infinity),
    );
  }
  if (sort === "losers") {
    return arr.sort(
      (a, b) => (a.card.perf_1d ?? Infinity) - (b.card.perf_1d ?? Infinity),
    );
  }
  // active + cmf both sort by cmf_20 descending — until `volume_ratio` is
  // surfaced for assets we use CMF as the proxy for "money flowing here."
  // The dropdown distinguishes them in copy so we can split logic later.
  return arr.sort(
    (a, b) => (b.card.cmf_20 ?? -Infinity) - (a.card.cmf_20 ?? -Infinity),
  );
}
