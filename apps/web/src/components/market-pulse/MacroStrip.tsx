"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MacroCard } from "@/lib/contracts";
import { fmtPct, fmtPrice } from "@/lib/market-pulse-format";

/**
 * Section 4 — Macro Pulse strip.
 *
 * 6 macro indicators in a single horizontal row. Compact mini-cards
 * (~140px wide each). On mobile, the strip horizontally scrolls so it
 * stays one row instead of becoming a tall stacked block.
 *
 * Each card has a tooltip explaining what the indicator signals in
 * plain English. This is the Karpathy-#2-simplicity version of
 * "interpretation surface" — no separate SignalChip needed since the
 * tooltip already does the job.
 */

const MACRO_TOOLTIPS: Record<string, string> = {
  VXX: "Volatility proxy. Up = fear rising; down = calm returning.",
  TLT: "Long-duration Treasury proxy. Up = rates falling (bond rally); down = rates rising.",
  UUP: "US dollar index proxy. Up = dollar strengthening vs basket.",
  GOLD_SPOT: "Gold spot price. Safe-haven + inflation-hedge proxy.",
  WTI_SPOT: "Crude oil spot. Growth + supply-shock proxy.",
  HYG: "High-yield credit ETF. Up = risk appetite; down = credit stress.",
};

export function MacroStrip({ macro }: { macro: MacroCard[] }) {
  if (!macro?.length) return null;
  return (
    <TooltipProvider delayDuration={200}>
      <section
        id="macro"
        aria-labelledby="macro-heading"
        className="space-y-3"
      >
        <h2
          id="macro-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Macro pulse
        </h2>
        <div className="-mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="flex gap-2 overflow-x-auto pb-2 sm:overflow-visible scrollbar-hide">
            {macro.map((m) => (
              <MacroCardUI key={m.symbol} card={m} />
            ))}
          </div>
        </div>
      </section>
    </TooltipProvider>
  );
}

function MacroCardUI({ card }: { card: MacroCard }) {
  const dir =
    card.perf_1d == null
      ? "flat"
      : card.perf_1d > 0.001
        ? "up"
        : card.perf_1d < -0.001
          ? "down"
          : "flat";
  const tooltip = MACRO_TOOLTIPS[card.symbol] ?? `Macro indicator: ${card.label}`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "shrink-0 min-w-[148px] sm:min-w-0 sm:flex-1 rounded-lg border px-3 py-2.5 cursor-help",
            dir === "up"
              ? "border-emerald-200 bg-emerald-50/60"
              : dir === "down"
                ? "border-red-200 bg-red-50/60"
                : "border-border bg-muted/30",
          )}
        >
          <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground truncate">
            {card.label}
          </div>
          <div className="mt-0.5 flex items-baseline justify-between gap-2">
            <span className="font-mono text-sm font-bold tabular-nums">
              {fmtPrice(card.price)}
            </span>
            <PerfBadge value={card.perf_1d} />
          </div>
          {card.is_stale && (
            <div className="mt-1 text-[9px] text-amber-700">⚠ stale</div>
          )}
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-[220px] text-xs leading-relaxed">
        <div className="font-semibold mb-1">{card.label}</div>
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}

function PerfBadge({ value }: { value: number | null | undefined }) {
  if (value == null)
    return <span className="font-mono text-[10px] text-muted-foreground">—</span>;
  const isUp = value > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-[11px] font-semibold tabular-nums",
        isUp ? "text-emerald-600" : value < 0 ? "text-red-500" : "text-muted-foreground",
      )}
    >
      {isUp ? (
        <TrendingUp className="h-2.5 w-2.5" />
      ) : value < 0 ? (
        <TrendingDown className="h-2.5 w-2.5" />
      ) : null}
      {fmtPct(value)}
    </span>
  );
}
