"use client";

import Link from "next/link";
import type { Route } from "next";
import { cn } from "@/lib/utils";
import type { IndexCard, MarketPulseResponse } from "@/lib/contracts";
import { buildNarrative, type PillStat } from "@/lib/market-pulse-narrative";
import { fmtPct } from "@/lib/market-pulse-format";

/**
 * Section 1 — the narrative hero card.
 *
 * Renders:
 *   - An inline 4-cell index ticker at the top of the card (Dow / Nasdaq /
 *     S&P 500 / Russell 2000 — via the indices in `MarketPulseResponse`,
 *     which today are ETF proxies SPY/QQQ/DIA/IWM but display the index
 *     names for clarity)
 *   - 2–3 plain-English sentences answering "what's happening in the
 *     market right now?"
 *   - Three inline stat pills (SPY 1D, lead sector, 10Y proxy)
 *
 * The inline ticker absorbed the content of the old `IndicesHero` section
 * per Jimmy's 2026-05-21 feedback ("we can remove the indices hero strip").
 * Keeping it INSIDE the Brief card avoids duplicating the global
 * `LiveTickerBar` that sits at the very top of every page.
 *
 * Phase 0: narrative is the deterministic Layer A `buildNarrative()`.
 * Phase 1: switches to backend LLM narrative when `data.narrative` lands;
 * fallback remains for LLM-unconfigured environments.
 */

// Map our ETF-proxy symbols to the index names retail readers know.
// Phase 1 backend work may switch to real-index quotes (DJI, NDX, SPX, RUT)
// once we verify FMP coverage; the labels here stay the same.
const INDEX_DISPLAY: Record<string, string> = {
  SPY: "S&P 500",
  QQQ: "Nasdaq",
  DIA: "Dow",
  IWM: "Russell 2000",
};

export function MarketBrief({ data }: { data: MarketPulseResponse }) {
  const narrative = buildNarrative(data);

  // Pick up to 4 indices to display; preserve backend order so Dow comes
  // first if the response has DIA. Fall back to whatever's in the array.
  const tickerCells = data.indices.slice(0, 4);

  return (
    <section
      id="brief"
      aria-labelledby="brief-heading"
      className="rounded-2xl border border-border/80 bg-gradient-to-br from-slate-50 to-white p-6 md:p-8 shadow-sm"
    >
      <h2 id="brief-heading" className="sr-only">
        Market Brief
      </h2>

      {/* Inline index ticker — absorbed from the removed IndicesHero section */}
      {tickerCells.length > 0 && (
        <div className="mb-5 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {tickerCells.map((c) => (
            <IndexTickerCell key={c.symbol} card={c} />
          ))}
        </div>
      )}

      <div className="space-y-2">
        {narrative.headline.map((sentence, i) => (
          <p
            key={i}
            className={cn(
              "text-lg md:text-xl leading-snug",
              i === 0 ? "font-semibold text-foreground" : "text-foreground/80",
            )}
          >
            {sentence}
          </p>
        ))}
      </div>

      {narrative.pills.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {narrative.pills.map((p) => (
            <Pill key={p.label} pill={p} />
          ))}
        </div>
      )}
    </section>
  );
}

function IndexTickerCell({ card }: { card: IndexCard }) {
  const isUp = (card.perf_1d ?? 0) >= 0;
  const displayName = INDEX_DISPLAY[card.symbol.toUpperCase()] ?? card.name;
  return (
    <Link
      href={`/stocks/${card.symbol}` as Route}
      className="block rounded-lg border border-border/60 bg-white/60 px-3 py-2 transition-colors hover:bg-white"
    >
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {displayName}
      </div>
      <div className="mt-0.5 flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-semibold tabular-nums">
          {card.price != null ? card.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
        </span>
        <span
          className={cn(
            "font-mono text-[11px] font-semibold tabular-nums",
            isUp ? "text-emerald-600" : "text-red-500",
          )}
        >
          {fmtPct(card.perf_1d)}
        </span>
      </div>
    </Link>
  );
}

function Pill({ pill }: { pill: PillStat }) {
  const tone =
    pill.perf == null
      ? "border-border bg-muted/40 text-foreground"
      : pill.perf >= 0
        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
        : "border-red-200 bg-red-50 text-red-800";

  const content = (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium",
        tone,
      )}
    >
      <span className="font-mono text-xs text-muted-foreground">{pill.label}</span>
      <span className="font-mono tabular-nums">{pill.value}</span>
    </span>
  );

  if (pill.href) {
    return (
      <Link href={pill.href as Route} className="hover:opacity-80 transition-opacity">
        {content}
      </Link>
    );
  }
  return content;
}
