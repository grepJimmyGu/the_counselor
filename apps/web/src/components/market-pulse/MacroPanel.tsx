"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MacroCard } from "@/lib/contracts";
import { fmtPct, fmtPrice } from "@/lib/market-pulse-format";

/**
 * Single themed macro panel — renders a title, a 1-sentence theme
 * summary, the 1-2 contributing macro cards, and one interpretation
 * chip computed by the parent (`MacroPanels`).
 *
 * Dumb component: parent decides which macros to show and what the
 * interpretation says. This component just lays it out consistently
 * across the 4 panels (Rates / Vol / FX / Commodities).
 *
 * Per Jimmy's 2026-05-21 feedback ("richer macro pulse number
 * insights" — replacing the old MacroStrip).
 */

export interface MacroPanelProps {
  title: string;
  summary: string;
  cards: MacroCard[];
  interpretation: string;
  interpretationTone: "up" | "down" | "neutral";
}

export function MacroPanel({
  title,
  summary,
  cards,
  interpretation,
  interpretationTone,
}: MacroPanelProps) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{summary}</p>

      <div className="mt-3 space-y-2">
        {cards.length === 0 ? (
          <div className="text-[11px] text-muted-foreground">No data.</div>
        ) : (
          cards.map((c) => <MacroRow key={c.symbol} card={c} />)
        )}
      </div>

      {interpretation && (
        <div className="mt-3">
          <InterpretationChip
            label={interpretation}
            tone={interpretationTone}
          />
        </div>
      )}
    </div>
  );
}

function MacroRow({ card }: { card: MacroCard }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <div className="min-w-0 flex-1">
        <div className="font-medium truncate">{card.label}</div>
        <div className="font-mono text-[10px] text-muted-foreground">
          {card.symbol}
        </div>
      </div>
      <span className="font-mono text-sm font-semibold tabular-nums">
        {fmtPrice(card.price)}
      </span>
      <PerfBadge value={card.perf_1d} />
    </div>
  );
}

function PerfBadge({ value }: { value: number | null | undefined }) {
  if (value == null)
    return (
      <span className="font-mono text-[10px] text-muted-foreground w-14 text-right">
        —
      </span>
    );
  const isUp = value > 0;
  const isDown = value < 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-[11px] font-semibold tabular-nums w-14 justify-end",
        isUp ? "text-emerald-600" : isDown ? "text-red-500" : "text-muted-foreground",
      )}
    >
      {isUp ? (
        <TrendingUp className="h-2.5 w-2.5" />
      ) : isDown ? (
        <TrendingDown className="h-2.5 w-2.5" />
      ) : null}
      {fmtPct(value)}
    </span>
  );
}

function InterpretationChip({
  label,
  tone,
}: {
  label: string;
  tone: "up" | "down" | "neutral";
}) {
  const cls =
    tone === "up"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : tone === "down"
        ? "border-red-200 bg-red-50 text-red-800"
        : "border-border bg-muted/30 text-foreground/80";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
        cls,
      )}
    >
      {label}
    </span>
  );
}
