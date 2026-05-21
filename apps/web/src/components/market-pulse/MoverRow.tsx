"use client";

import Link from "next/link";
import type { Route } from "next";
import { ChevronRight, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AssetCard } from "@/lib/contracts";
import { fmtPct, fmtPrice } from "@/lib/market-pulse-format";

/**
 * Single dense 2-line row in the Top Movers list.
 *
 * Layout (same across desktop and mobile):
 *   Line 1: <SYMBOL>  <Name>  [Sector chip]
 *   Line 2: <perf_1d badge>  <CMF chip>  <price>  <volume ratio>  →
 *
 * Per Jimmy's 2026-05-21 feedback: the previous desktop layout had too
 * much empty space across the row. The 2-line shape fits more
 * information vertically and reads consistently on mobile + desktop.
 *
 * `volume_ratio` is rendered as a chip; AssetCard doesn't expose it yet
 * (backend addition in Phase 2). Shown as "—" until then to lock the
 * final layout.
 */

export interface MoverRowProps {
  card: AssetCard;
  category: "Stock" | "ETF";
  href: string;
}

export function MoverRow({ card, category, href }: MoverRowProps) {
  // AssetCard doesn't have volume_ratio today (only SectorCard does).
  // Casting through `unknown` so we don't break the contract — Phase 2
  // backend addition will make this a real field.
  const volumeRatio = (card as unknown as { volume_ratio?: number | null })
    .volume_ratio;
  const sector = card.sector;

  return (
    <Link
      href={href as Route}
      className="block rounded-lg px-3 py-2 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {/* Line 1 — symbol, name, sector chip */}
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xs font-bold">{card.symbol}</span>
        <span className="text-xs text-foreground/80 truncate flex-1 min-w-0">
          {card.name}
        </span>
        {sector && (
          <span className="hidden sm:inline-flex shrink-0 items-center rounded-full border border-border bg-muted/40 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
            {sector}
          </span>
        )}
        <span className="inline-flex shrink-0 items-center rounded-full border border-border/60 bg-muted/30 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground/80">
          {category}
        </span>
      </div>

      {/* Line 2 — perf, CMF, price, volume ratio, chevron */}
      <div className="mt-1 flex items-center gap-3 text-xs">
        <PerfBadge value={card.perf_1d} />
        <CmfMini value={card.cmf_20} />
        <span className="font-mono text-xs font-semibold tabular-nums shrink-0">
          {fmtPrice(card.price)}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground shrink-0">
          {volumeRatio != null ? `${volumeRatio.toFixed(1)}× vol` : "— vol"}
        </span>
        <span className="ml-auto shrink-0">
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
        </span>
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
