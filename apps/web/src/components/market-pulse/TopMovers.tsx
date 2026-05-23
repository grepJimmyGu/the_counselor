"use client";

import { useMemo, useState } from "react";
import type { AssetCard } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { MoverRow, type MoverRowProps } from "./MoverRow";

/**
 * Section 5 — Top Movers (unified ranked list).
 *
 * Renamed from "Movers" on 2026-05-21 per Jimmy's preview feedback.
 * Drops commodities from the list (the page composition no longer
 * appends the static commodity stub array). Filter chips: All · Stocks
 * · ETFs.
 *
 * Sort defaults to "Top gainers" (most-natural retail framing per Yahoo
 * / Robinhood). The 2026-05-22 review surfaced that the previous "Most
 * active (CMF flow)" option sorted identically to "CMF flow" — both
 * comparators returned `cmf_20` descending. Dropped "Most active" here
 * until per-stock `volume_ratio` ships (Phase 2 ticket in PROJECT_BACKLOG.md
 * §4b follow-ups).
 */

export interface MoverItem {
  card: AssetCard;
  category: "Stock" | "ETF";
  href: string;
}

type Filter = "all" | "stock" | "etf";
type Sort = "gainers" | "losers" | "cmf";

export function TopMovers({ items }: { items: MoverItem[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("gainers");

  const filtered = useMemo(() => {
    const byCat =
      filter === "all"
        ? items
        : items.filter((i) => i.category.toLowerCase() === filter);
    return sortItems(byCat, sort);
  }, [items, filter, sort]);

  const counts = useMemo(() => countByCategory(items), [items]);

  return (
    <section
      id="movers"
      aria-labelledby="movers-heading"
      className="space-y-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <h2
          id="movers-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Top Movers
        </h2>
        <select
          aria-label="Sort top movers by"
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          className="rounded-md border border-border bg-white px-2 py-1 text-xs focus-visible:outline-2 focus-visible:outline-primary"
        >
          <option value="gainers">Sort: Top gainers</option>
          <option value="losers">Sort: Top losers</option>
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
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-white px-3 py-6 text-center text-xs text-muted-foreground">
          No matches.
        </div>
      ) : (
        // 2-row × N-col grid (per 2026-05-21 redo). Take the top 10 cards
        // (5 per row × 2 rows) so the visual fits 2 rows on desktop without
        // wrapping. Mobile: 2 cols × 5 rows keeps the same cards reachable
        // without horizontal scroll.
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {filtered.slice(0, 10).map(({ card, category, href }) => (
            <MoverRow
              key={`${category}-${card.symbol}`}
              card={card}
              category={category as MoverRowProps["category"]}
              href={href}
            />
          ))}
        </div>
      )}
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

function countByCategory(items: MoverItem[]): { stock: number; etf: number } {
  return items.reduce(
    (acc, i) => {
      const k = i.category.toLowerCase() as keyof typeof acc;
      acc[k]++;
      return acc;
    },
    { stock: 0, etf: 0 },
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
  // sort === "cmf" — money-flow proxy until `volume_ratio` lands for stocks.
  return arr.sort(
    (a, b) => (b.card.cmf_20 ?? -Infinity) - (a.card.cmf_20 ?? -Infinity),
  );
}
