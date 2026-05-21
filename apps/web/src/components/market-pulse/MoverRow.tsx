"use client";

import Link from "next/link";
import type { Route } from "next";
import { ChevronRight, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AssetCard } from "@/lib/contracts";
import { fmtPct, fmtPrice } from "@/lib/market-pulse-format";

/**
 * Single 60px row in the unified Movers list.
 *
 * Layout (desktop): symbol | name + category chip | CMF bar | perf badge | price | chevron
 * Mobile: symbol + perf on top row, name + price on bottom row.
 *
 * `category` is rendered as a small chip beside the name so users can
 * see "ETF" / "Stock" / "Commodity" at a glance without having to switch
 * tabs (per Section 5's "one list + filter chips" decision).
 */

export interface MoverRowProps {
  card: AssetCard;
  category: "Stock" | "ETF" | "Commodity";
  href: string;
}

export function MoverRow({ card, category, href }: MoverRowProps) {
  return (
    <Link
      href={href as Route}
      className="block rounded-lg transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {/* Desktop */}
      <div className="hidden sm:grid grid-cols-[5rem_1fr_8rem_6rem_5.5rem_1.5rem] items-center gap-3 px-3 py-2.5 min-h-[52px]">
        <span className="font-mono text-xs font-bold">{card.symbol}</span>
        <div className="min-w-0">
          <div className="text-xs font-medium truncate">
            {card.name}
            <span className="ml-2 inline-flex items-center rounded-full border border-border bg-muted/40 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
              {category}
            </span>
          </div>
        </div>
        <CmfMini value={card.cmf_20} />
        <PerfBadge value={card.perf_1d} />
        <span className="font-mono text-xs font-semibold tabular-nums text-right">
          {fmtPrice(card.price)}
        </span>
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
      </div>

      {/* Mobile */}
      <div className="sm:hidden flex flex-col gap-1 px-3 py-2.5 min-h-[56px]">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-xs font-bold">{card.symbol}</span>
          <PerfBadge value={card.perf_1d} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-foreground/80 truncate">
            {card.name}
            <span className="ml-1 text-[9px] uppercase tracking-wide text-muted-foreground">
              ({category})
            </span>
          </span>
          <span className="font-mono text-xs font-semibold tabular-nums shrink-0">
            {fmtPrice(card.price)}
          </span>
        </div>
      </div>
    </Link>
  );
}

function PerfBadge({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="font-mono text-xs text-muted-foreground">—</span>;
  const isUp = value >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-xs font-semibold tabular-nums",
        isUp ? "text-emerald-600" : "text-red-500",
      )}
    >
      {isUp ? (
        <TrendingUp className="h-2.5 w-2.5" />
      ) : (
        <TrendingDown className="h-2.5 w-2.5" />
      )}
      {fmtPct(value)}
    </span>
  );
}

function CmfMini({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="font-mono text-[10px] text-muted-foreground">—</span>;
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const isUp = value >= 0;
  const pct = (Math.abs(clamped) / 0.5) * 50;

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="absolute left-1/2 top-0 h-full w-px bg-border/60" />
        <div
          className={cn(
            "absolute top-0 h-full",
            isUp ? "left-1/2 bg-emerald-500" : "right-1/2 bg-red-500",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[10px] tabular-nums w-9 text-right">
        {value.toFixed(2)}
      </span>
    </div>
  );
}
