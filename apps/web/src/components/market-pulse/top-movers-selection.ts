import type { AssetCard } from "@/lib/contracts";
import type { LiveQuote } from "@/lib/useLiveQuotes";

export const TOP_MOVERS_VISIBLE_LIMIT = 10;

export interface MoverItem {
  card: AssetCard;
  category: "Stock" | "ETF";
  href: string;
}

export type MoverFilter = "all" | "stock" | "etf";
export type MoverSort = "gainers" | "losers" | "cmf";

export function selectVisibleMoverItems(
  items: MoverItem[],
  filter: MoverFilter,
  sort: MoverSort,
  limit = TOP_MOVERS_VISIBLE_LIMIT,
): MoverItem[] {
  const byCat =
    filter === "all"
      ? items
      : items.filter((i) => i.category.toLowerCase() === filter);
  return sortMoverItems(byCat, sort).slice(0, limit);
}

export function liveSymbolsForMoverItems(items: MoverItem[]): string[] {
  return Array.from(new Set(items.map((i) => i.card.symbol.toUpperCase())));
}

export function applyLiveQuoteToMoverItem(
  item: MoverItem,
  quotes: Record<string, LiveQuote>,
): MoverItem {
  const live = quotes[item.card.symbol.toUpperCase()];
  if (!live) return item;
  return {
    ...item,
    card: {
      ...item.card,
      price: live.price,
      perf_1d: live.change_percent / 100,
    },
  };
}

export function countMoverItemsByCategory(
  items: MoverItem[],
): { stock: number; etf: number } {
  return items.reduce(
    (acc, i) => {
      const k = i.category.toLowerCase() as keyof typeof acc;
      acc[k]++;
      return acc;
    },
    { stock: 0, etf: 0 },
  );
}

function sortMoverItems(items: MoverItem[], sort: MoverSort): MoverItem[] {
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
  return arr.sort(
    (a, b) => (b.card.cmf_20 ?? -Infinity) - (a.card.cmf_20 ?? -Infinity),
  );
}
