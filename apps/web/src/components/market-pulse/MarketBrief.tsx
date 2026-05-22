"use client";

import Link from "next/link";
import type { Route } from "next";
import { cn } from "@/lib/utils";
import type { MarketPulseResponse } from "@/lib/contracts";
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

// Per Jimmy's 2026-05-21 feedback: the inline ticker should show the
// ACTUAL index numbers (Dow Jones, Nasdaq Composite, S&P 500, Russell
// 2000 point values) rather than the ETF proxy share prices that
// `data.indices` returns today (SPY ~$740, QQQ ~$485, etc.).
//
// Phase 0a uses HARDCODED MOCK values matching realistic late-2026
// levels so the ticker visual is reviewable. Phase 1 wires a backend
// indices endpoint that fetches DJI / IXIC / SPX / RUT directly from
// FMP (or AV) and lets us drop this constant.
interface MockIndex {
  label: string;
  value: number;
  perf: number;
  symbol: string; // ETF proxy used for the click-through link
}

const MOCK_INDICES: MockIndex[] = [
  { label: "Dow Jones", value: 38234.16, perf: -0.0042, symbol: "DIA" },
  { label: "Nasdaq Composite", value: 17623.45, perf: 0.0118, symbol: "QQQ" },
  { label: "S&P 500", value: 5310.12, perf: 0.0028, symbol: "SPY" },
  { label: "Russell 2000", value: 2089.12, perf: -0.0031, symbol: "IWM" },
];

export function MarketBrief({ data }: { data: MarketPulseResponse }) {
  const narrative = buildNarrative(data);

  return (
    <section
      id="brief"
      aria-labelledby="brief-heading"
      className="rounded-2xl border border-border/80 bg-gradient-to-br from-slate-50 to-white p-6 md:p-8 shadow-sm"
    >
      <h2 id="brief-heading" className="sr-only">
        Market Brief
      </h2>

      {/* Inline index ticker — actual index point values
          (Phase 0a mock; Phase 1 wires real backend) */}
      <div className="mb-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {MOCK_INDICES.map((idx) => (
            <IndexTickerCell key={idx.symbol} idx={idx} />
          ))}
        </div>
        <div className="mt-1.5">
          <span className="rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[9px] font-medium text-amber-900">
            Preview · mock index values
          </span>
        </div>
      </div>

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

function IndexTickerCell({ idx }: { idx: MockIndex }) {
  const isUp = idx.perf >= 0;
  // Format index point values without decimals (38,234 not 38,234.16) for
  // readability — these are quoted as whole-number indices in the press.
  const valueStr = idx.value.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
  return (
    <Link
      href={`/stocks/${idx.symbol}` as Route}
      className="block rounded-lg border border-border/60 bg-white/60 px-3 py-2 transition-colors hover:bg-white"
    >
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {idx.label}
      </div>
      <div className="mt-0.5 flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-semibold tabular-nums">
          {valueStr}
        </span>
        <span
          className={cn(
            "font-mono text-[11px] font-semibold tabular-nums",
            isUp ? "text-emerald-600" : "text-red-500",
          )}
        >
          {fmtPct(idx.perf)}
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
