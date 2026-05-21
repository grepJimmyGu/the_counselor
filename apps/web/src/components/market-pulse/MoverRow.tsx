"use client";

import Link from "next/link";
import type { Route } from "next";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AssetCard } from "@/lib/contracts";
import { fmtPct, fmtPrice } from "@/lib/market-pulse-format";

/**
 * Single Top Movers card.
 *
 * 2026-05-21 redo: the parent (`TopMovers`) now lays cards out in a
 * 2-row × ~5-column grid (Yahoo-style "Top Gainers/Losers" tile pattern).
 * Each card is compact (~152×128px) and shows symbol + category chip +
 * name on top, price + sector chip in the middle, CMF mini + volume
 * ratio at the bottom.
 *
 * `volume_ratio` is shown as a chip when available (Phase 2 backend
 * addition); rendered as "— vol" placeholder for now to lock the layout.
 */

export interface MoverRowProps {
  card: AssetCard;
  category: "Stock" | "ETF";
  href: string;
}

export function MoverRow({ card, category, href }: MoverRowProps) {
  const volumeRatio = (card as unknown as { volume_ratio?: number | null })
    .volume_ratio;
  const sector = card.sector;

  return (
    <Link
      href={href as Route}
      className="block rounded-xl border border-border bg-white p-3 transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {/* Top — symbol + category chip + perf badge */}
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-sm font-bold">{card.symbol}</span>
            <span className="inline-flex shrink-0 items-center rounded-full border border-border/60 bg-muted/30 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground/80">
              {category}
            </span>
          </div>
          <div
            className="text-[11px] text-muted-foreground truncate"
            title={card.name}
          >
            {card.name}
          </div>
        </div>
        <PerfBadge value={card.perf_1d} />
      </div>

      {/* Middle — price + sector chip */}
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="font-mono text-base font-semibold tabular-nums">
          {fmtPrice(card.price)}
        </span>
        {sector && (
          <span
            className="rounded-full border border-border/60 bg-white px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground truncate max-w-[60%]"
            title={sector}
          >
            {sector}
          </span>
        )}
      </div>

      {/* Bottom — CMF mini + volume ratio */}
      <div className="mt-2 flex items-center gap-2">
        <CmfMini value={card.cmf_20} />
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground shrink-0">
          {volumeRatio != null ? `${volumeRatio.toFixed(1)}× vol` : "— vol"}
        </span>
      </div>
    </Link>
  );
}

function PerfBadge({ value }: { value: number | null | undefined }) {
  if (value == null)
    return (
      <span className="font-mono text-xs text-muted-foreground shrink-0">—</span>
    );
  const isUp = value >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-xs font-semibold tabular-nums shrink-0",
        isUp ? "text-emerald-600" : "text-red-500",
      )}
    >
      {isUp ? (
        <TrendingUp className="h-3 w-3" />
      ) : (
        <TrendingDown className="h-3 w-3" />
      )}
      {fmtPct(value)}
    </span>
  );
}

function CmfMini({ value }: { value: number | null | undefined }) {
  if (value == null)
    return (
      <span className="font-mono text-[10px] text-muted-foreground flex-1">
        —
      </span>
    );
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const isUp = value >= 0;
  const pct = (Math.abs(clamped) / 0.5) * 50;

  return (
    <div className="flex items-center gap-1.5 flex-1 min-w-0">
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
    </div>
  );
}
