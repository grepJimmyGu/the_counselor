"use client";

/**
 * <HomeMarketStrip> — PRD-24a §0.3 — a compact Market Pulse line for the hero.
 *
 * A thin, above-the-fold row of the four major US equity indices with their
 * day-over-day % (the §3.8 cardinal rule). Deliberately a different visual
 * register from the body's <MarketSnapshot> 4-card grid: this is an
 * at-a-glance "where's the market right now" accent, not a browse surface.
 *
 * Reuses the light `getMarketOverview` endpoint (NOT the heavier
 * `/api/market/pulse`, which can cold-path to ~20s — unacceptable above the
 * fold). Each index links to its /stocks/<symbol> analysis page.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { getMarketOverview } from "@/lib/api";
import type { MarketSnapshotItem } from "@/lib/contracts";
import { cn } from "@/lib/utils";

// The four major US equity indices (ETF proxies). Distinct from the body
// <MarketSnapshot> watchlist (SPY/QQQ/GLD/NVDA) so the strip reads as a
// dedicated "index board" rather than a duplicate.
const INDEX_SYMBOLS = ["SPY", "QQQ", "DIA", "IWM"] as const;
const INDEX_LABELS: Record<string, string> = {
  SPY: "S&P 500",
  QQQ: "Nasdaq 100",
  DIA: "Dow Jones",
  IWM: "Russell 2000",
};

function pctString(changePct: number): string {
  const sign = changePct >= 0 ? "+" : "";
  return `${sign}${(changePct * 100).toFixed(2)}%`;
}

function IndexPill({ item }: { item: MarketSnapshotItem }) {
  const positive = item.change_pct >= 0;
  return (
    <Link
      href={`/stocks/${item.symbol}` as Route}
      data-testid={`home-market-strip-${item.symbol}`}
      className="group inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/70 px-3 py-1.5 text-xs shadow-sm backdrop-blur-sm transition-all hover:border-primary/40 hover:shadow"
    >
      <span className="font-medium text-foreground">
        {INDEX_LABELS[item.symbol] ?? item.symbol}
      </span>
      <span
        className={cn(
          "font-mono font-semibold tabular-nums",
          positive ? "text-[var(--profit)]" : "text-[var(--loss)]",
        )}
      >
        {pctString(item.change_pct)}
      </span>
    </Link>
  );
}

function SkeletonPill() {
  return (
    <span className="inline-flex h-7 w-28 animate-pulse rounded-full bg-white/50" />
  );
}

export function HomeMarketStrip() {
  const [items, setItems] = useState<MarketSnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getMarketOverview([...INDEX_SYMBOLS])
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch(() => {
        // Stay silent — the strip is a non-essential accent; if the endpoint
        // is down the hero simply renders without it.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Nothing to show and not loading → render nothing (don't leave an empty gap).
  if (!loading && items.length === 0) return null;

  // Order the results to match INDEX_SYMBOLS (the endpoint may reorder).
  const ordered = INDEX_SYMBOLS.map((s) =>
    items.find((it) => it.symbol === s),
  ).filter((it): it is MarketSnapshotItem => Boolean(it));

  return (
    <div
      data-testid="home-market-strip"
      className="mt-8 flex flex-wrap items-center justify-center gap-2"
    >
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Markets
      </span>
      {loading
        ? INDEX_SYMBOLS.map((s) => <SkeletonPill key={s} />)
        : ordered.map((item) => <IndexPill key={item.symbol} item={item} />)}
    </div>
  );
}
