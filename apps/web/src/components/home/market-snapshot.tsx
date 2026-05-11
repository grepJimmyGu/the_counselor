"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import type { Route } from "next";
import { getMarketOverview } from "@/lib/api";
import type { MarketSnapshotItem } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Sparkline } from "./sparkline";

const WATCHLIST = ["SPY", "QQQ", "GLD", "USO", "TLT", "DBC", "AAPL", "NVDA"];

const ASSET_LABELS: Record<string, string> = {
  SPY: "S&P 500",
  QQQ: "Nasdaq 100",
  GLD: "Gold",
  USO: "Crude Oil",
  TLT: "20Y Bonds",
  DBC: "Commodities",
  AAPL: "Apple",
  NVDA: "NVIDIA",
};

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="h-3 w-10 animate-pulse rounded bg-muted" />
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
        </div>
        <div className="h-8 w-20 animate-pulse rounded bg-muted" />
      </div>
      <div className="mt-3 flex items-end justify-between">
        <div className="h-5 w-16 animate-pulse rounded bg-muted" />
        <div className="h-4 w-12 animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}

function AssetCard({ item }: { item: MarketSnapshotItem }) {
  const isPositive = item.change_pct >= 0;
  const pctStr = `${isPositive ? "+" : ""}${(item.change_pct * 100).toFixed(2)}%`;
  const absStr = `${isPositive ? "+" : ""}${item.change_abs.toFixed(2)}`;
  const label = ASSET_LABELS[item.symbol] ?? item.name;

  return (
    <Link
      href={`/stocks/${item.symbol}` as Route}
      className="group block rounded-xl border border-border bg-white p-4 shadow-sm transition-all duration-200 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-sm font-bold text-foreground">{item.symbol}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </div>
        <Sparkline data={item.sparkline} positive={isPositive} width={72} height={28} />
      </div>
      <div className="mt-3 flex items-end justify-between">
        <div className="font-mono text-lg font-semibold">${item.last_price.toFixed(2)}</div>
        <div className={cn("flex items-center gap-1 text-xs font-semibold", isPositive ? "text-[var(--profit)]" : "text-[var(--loss)]")}>
          {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          <span>{pctStr}</span>
          <span className="font-normal opacity-70">({absStr})</span>
        </div>
      </div>
      <div className="mt-1.5 flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">{item.last_date}</span>
        <span className="flex items-center gap-0.5 text-[10px] text-primary opacity-0 transition-opacity group-hover:opacity-100">
          View analysis <ArrowRight className="h-2.5 w-2.5" />
        </span>
      </div>
    </Link>
  );
}

export function MarketSnapshot() {
  const [items, setItems] = useState<MarketSnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMarketOverview(WATCHLIST)
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-xl font-semibold">Market Snapshot</h2>
          <p className="text-sm text-muted-foreground">Click any asset for full analysis · End-of-day prices</p>
        </div>
        <Link
          href={"/stocks" as Route}
          className="flex items-center gap-1 text-sm font-medium text-primary transition-colors hover:underline"
        >
          Browse all stocks <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {loading
          ? WATCHLIST.map((s) => <SkeletonCard key={s} />)
          : items.map((item) => <AssetCard key={item.symbol} item={item} />)
        }
        {!loading && items.length === 0 && (
          <p className="col-span-full text-sm text-muted-foreground">
            Market data unavailable — run the backend to see prices.
          </p>
        )}
      </div>
    </section>
  );
}
