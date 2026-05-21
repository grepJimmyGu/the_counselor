"use client";

import Link from "next/link";
import type { Route } from "next";
import { cn } from "@/lib/utils";
import type { MarketPulseResponse } from "@/lib/contracts";
import { buildNarrative, type PillStat } from "@/lib/market-pulse-narrative";

/**
 * Section 1 — the narrative hero card.
 *
 * Renders 2–3 plain-English sentences answering "what's happening in the
 * market right now?" plus three inline stat pills (SPY 1D, lead sector,
 * 10Y proxy). Layout choice: pills as a horizontal row beneath the
 * paragraph so retail readers don't have to parse a multi-column grid.
 *
 * Phase 0: narrative is the deterministic Layer A `buildNarrative()`.
 * Phase 1: switches to backend LLM narrative when `data.narrative` lands;
 * fallback remains for LLM-unconfigured environments.
 */

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
