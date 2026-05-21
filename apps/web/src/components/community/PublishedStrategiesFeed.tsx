"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Loader2, Sparkles, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VerifiedBadge } from "@/components/VerifiedBadge";
import { listPublishedStrategies } from "@/lib/api";
import type { PublishedStrategySummary } from "@/lib/contracts";

type Sort = "trending" | "newest";

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtNumber(v: number | null | undefined, digits = 2): string {
  if (v == null || isNaN(v)) return "—";
  return v.toFixed(digits);
}

/**
 * Stage 4b — community feed of published strategies (the new Stage 4a primitive).
 *
 * Distinct from the legacy "Public Strategies" section on /community which
 * shows PRD-02 backtests with slug != null. This feed reads the new
 * published_strategies table.
 */
export function PublishedStrategiesFeed() {
  const [items, setItems] = useState<PublishedStrategySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<Sort>("trending");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listPublishedStrategies({ sort, page_size: 12 })
      .then((feed) => {
        if (!cancelled) setItems(feed.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sort]);

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <h2 className="text-base font-semibold">Community publishes</h2>
          {!loading && (
            <Badge variant="outline" className="font-mono text-[10px]">
              {items.length}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <SortBtn current={sort} value="trending" onClick={() => setSort("trending")}>
            Trending
          </SortBtn>
          <SortBtn current={sort} value="newest" onClick={() => setSort("newest")}>
            Newest
          </SortBtn>
        </div>
      </div>

      {loading ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center">
          <Sparkles className="mx-auto h-8 w-8 text-muted-foreground/40" />
          <p className="mt-2 text-sm text-muted-foreground">
            No published strategies yet. Be the first.
          </p>
          <Link
            href={"/workspace" as Route}
            className="mt-2 inline-block text-xs font-medium text-primary hover:underline"
          >
            Build and publish your strategy →
          </Link>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((s) => (
            <Card key={s.id} s={s} />
          ))}
        </div>
      )}
    </section>
  );
}

function SortBtn({
  current,
  value,
  onClick,
  children,
}: {
  current: Sort;
  value: Sort;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <Button
      variant={active ? "default" : "ghost"}
      size="sm"
      onClick={onClick}
      className="h-7 px-2.5 text-xs"
    >
      {children}
    </Button>
  );
}

function Card({ s }: { s: PublishedStrategySummary }) {
  const m = s.metrics;
  const totalReturn = m.total_return;
  const positive = (totalReturn ?? 0) >= 0;
  return (
    <Link
      href={`/s/${s.slug}` as Route}
      className="block rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-accent/40"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="line-clamp-2 text-sm font-semibold text-foreground">
          {s.title}
        </h3>
        {positive ? (
          <TrendingUp className="h-3.5 w-3.5 flex-shrink-0 text-emerald-600" />
        ) : (
          <TrendingDown className="h-3.5 w-3.5 flex-shrink-0 text-rose-600" />
        )}
      </div>

      <div className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="truncate">
          {s.author.display_name ?? s.author.handle ?? "Anonymous"}
        </span>
        <VerifiedBadge badge={s.author.badge} size="xs" />
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span
          className={`text-xl font-bold ${
            positive ? "text-emerald-600" : "text-rose-600"
          }`}
        >
          {fmtPct(totalReturn, 1)}
        </span>
        <span className="text-[10px] uppercase text-muted-foreground">return</span>
      </div>

      <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>Sharpe {fmtNumber(m.sharpe_ratio, 2)}</span>
        <span>DD {fmtPct(m.max_drawdown, 0)}</span>
        <span>{s.universe.length}t</span>
      </div>

      <div className="mt-3 border-t border-border/60 pt-2 text-[10px] text-muted-foreground">
        {s.strategy_type.replace(/_/g, " ")}
      </div>
    </Link>
  );
}
