"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { MoverRow, type MoverRowProps } from "./MoverRow";
import {
  applyLiveQuoteToMoverItem,
  countMoverItemsByCategory,
  liveSymbolsForMoverItems,
  selectVisibleMoverItems,
  type MoverFilter,
  type MoverItem,
  type MoverSort,
} from "./top-movers-selection";

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

export type { MoverItem } from "./top-movers-selection";

export function TopMovers({ items }: { items: MoverItem[] }) {
  const [filter, setFilter] = useState<MoverFilter>("all");
  const [sort, setSort] = useState<MoverSort>("gainers");

  const visibleItems = useMemo(() => {
    return selectVisibleMoverItems(items, filter, sort);
  }, [items, filter, sort]);

  const liveSymbols = useMemo(
    () => liveSymbolsForMoverItems(visibleItems),
    [visibleItems],
  );
  const { quotes: liveQuotes } = useLiveQuotes(liveSymbols);

  const visibleItemsWithLive = useMemo(() => {
    return visibleItems.map((item) => applyLiveQuoteToMoverItem(item, liveQuotes));
  }, [visibleItems, liveQuotes]);

  const counts = useMemo(() => countMoverItemsByCategory(items), [items]);

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
          onChange={(e) => setSort(e.target.value as MoverSort)}
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

      {visibleItems.length === 0 ? (
        <div className="rounded-xl border border-border bg-white px-3 py-6 text-center text-xs text-muted-foreground">
          No matches.
        </div>
      ) : (
        // 2-row × N-col grid (per 2026-05-21 redo). Take the top 10 cards
        // (5 per row × 2 rows) so the visual fits 2 rows on desktop without
        // wrapping. Mobile: 2 cols × 5 rows keeps the same cards reachable
        // without horizontal scroll.
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {visibleItemsWithLive.map(({ card, category, href }) => (
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
