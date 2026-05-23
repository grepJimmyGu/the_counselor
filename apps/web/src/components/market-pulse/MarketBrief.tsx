"use client";

import Link from "next/link";
import type { Route } from "next";
import { cn } from "@/lib/utils";
import type { MarketPulseResponse } from "@/lib/contracts";
import { buildNarrative, type PillStat } from "@/lib/market-pulse-narrative";
import { fmtPct } from "@/lib/market-pulse-format";
import { useLiveQuotes } from "@/lib/useLiveQuotes";

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

/**
 * Inline ticker shows the actual index point values (Dow Jones, Nasdaq
 * Composite, S&P 500, Russell 2000) rather than ETF proxy share prices.
 * Phase 1b-extra: fetched live from FMP via the existing `useLiveQuotes`
 * hook using the `^` index symbols, which FMP's `/stable/quote` endpoint
 * supports natively. No new backend code required — the live-quote cache
 * already deduplicates + batches these.
 *
 * `MOCK_INDICES` is kept as the SSR-time / loading fallback so the cells
 * never render empty during the first 200ms before `useLiveQuotes`
 * resolves. The `tickerSymbol` (^DJI etc.) keys the live override; the
 * `clickTarget` (DIA etc.) is the ETF-proxy ticker the click-through
 * link points at since we don't have per-index detail pages.
 */
interface IndexConfig {
  label: string;
  fallbackValue: number; // shown briefly until live data resolves
  fallbackPerf: number;
  tickerSymbol: string; // FMP index symbol — `^DJI` etc.
  clickTarget: string; // ETF proxy for the click-through link
}

const INDEX_CONFIGS: IndexConfig[] = [
  { label: "Dow Jones", fallbackValue: 50285, fallbackPerf: 0.0055, tickerSymbol: "^DJI", clickTarget: "DIA" },
  { label: "Nasdaq Composite", fallbackValue: 26293, fallbackPerf: 0.0009, tickerSymbol: "^IXIC", clickTarget: "QQQ" },
  { label: "S&P 500", fallbackValue: 7446, fallbackPerf: 0.0018, tickerSymbol: "^GSPC", clickTarget: "SPY" },
  { label: "Russell 2000", fallbackValue: 2580, fallbackPerf: -0.0010, tickerSymbol: "^RUT", clickTarget: "IWM" },
];

export function MarketBrief({ data }: { data: MarketPulseResponse }) {
  // Phase 1b-extra: live index point values via FMP (`^DJI`, `^IXIC`,
  // `^GSPC`, `^RUT`). Falls back to fallbackValue / fallbackPerf during
  // the first poll before the cache resolves.
  const indexSymbols = INDEX_CONFIGS.map((c) => c.tickerSymbol);
  const { quotes: liveIndexQuotes } = useLiveQuotes(indexSymbols);

  // Phase 1b — prefer the backend's LLM-generated narrative when present.
  // Falls through to the deterministic template (`lib/market-pulse-narrative.ts`)
  // when `data.narrative` is null (LLM_PROVIDER unset, backend failure, etc.).
  const deterministic = buildNarrative(data);
  const llmNarrative = data.narrative ?? null;
  const headlineSentences = llmNarrative
    ? splitIntoSentences(llmNarrative.headline)
    : deterministic.headline;
  const isLlm = llmNarrative != null;

  return (
    <section
      id="brief"
      aria-labelledby="brief-heading"
      className="rounded-2xl border border-border/80 bg-gradient-to-br from-slate-50 to-white p-6 md:p-8 shadow-sm"
    >
      <h2 id="brief-heading" className="sr-only">
        Market Brief
      </h2>

      {/* Inline index ticker — real DJI / IXIC / GSPC / RUT point values
          via FMP's `/stable/quote` (^-prefixed). Falls back to seeded
          values during the first 200-300ms before useLiveQuotes resolves. */}
      <div className="mb-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {INDEX_CONFIGS.map((cfg) => {
            const live = liveIndexQuotes[cfg.tickerSymbol];
            return (
              <IndexTickerCell
                key={cfg.tickerSymbol}
                config={cfg}
                liveValue={live?.price ?? cfg.fallbackValue}
                livePerf={
                  live ? live.change_percent / 100 : cfg.fallbackPerf
                }
              />
            );
          })}
        </div>
      </div>

      {/* Two-column layout — narrative on the left (2/3 width), takeaways
          on the right (1/3). Stacks on mobile so narrative reads first.
          (Phase 1b feedback 2026-05-22: card was too wide with empty
          space on the right; news-sidebar version is queued as a
          future-phase improvement in PROJECT_BACKLOG.md.) */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-2 lg:col-span-2">
          {/* Date byline — newspaper-style anchor for the narrative.
              Surfaces the LLM-generated `as_of` (the calendar day the
              read is summarizing) above the headline so users can't
              miss which session they're reading. Per Jimmy's 2026-05-23
              feedback (the previous 9px footer placement was too quiet
              to be useful). */}
          {isLlm && llmNarrative.as_of && (
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {llmNarrative.as_of}
            </div>
          )}
          {headlineSentences.map((sentence, i) => (
            <p
              key={i}
              className={cn(
                "text-lg md:text-xl leading-snug",
                i === 0
                  ? "font-semibold text-foreground"
                  : "text-foreground/80",
              )}
            >
              {sentence}
            </p>
          ))}
          <div className="pt-2 text-[9px] text-muted-foreground/60">
            {isLlm ? "Narrative generated hourly" : "Deterministic summary"}
          </div>
        </div>

        <aside className="lg:col-span-1 lg:border-l lg:border-border/40 lg:pl-6">
          {isLlm && llmNarrative.watch_items.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                What to watch
              </div>
              <ul className="space-y-2">
                {llmNarrative.watch_items.map((item, i) => (
                  <li
                    key={i}
                    className="text-sm text-foreground/80 leading-snug flex gap-2"
                  >
                    <span className="mt-1.5 h-1 w-1 rounded-full bg-primary shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!isLlm && deterministic.pills.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Key stats
              </div>
              <div className="flex flex-col gap-2">
                {deterministic.pills.map((p) => (
                  <Pill key={p.label} pill={p} />
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

/**
 * Split an LLM-generated `headline` paragraph into rendered sentences.
 * Mirrors the shape of `buildNarrative()`'s deterministic output (string[])
 * so the render loop above is uniform regardless of source.
 *
 * Sentence boundary = end-of-sentence punctuation (`.` `!` `?`) followed
 * by whitespace AND a capital letter. The capital-letter lookahead is
 * what protects decimal numbers from being shredded — "1.92%" doesn't
 * have a capital letter after the `.`, so it stays intact. This was a
 * production bug visible after 1b shipped (Jimmy's 2026-05-22 screenshot
 * showed "the XLE sector up 1." / "92%, while small caps lagged…").
 */
function splitIntoSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Split AT (lookbehind) end-of-sentence punctuation followed by
  // whitespace AND (lookahead) a capital letter starting the next sentence.
  const parts = trimmed.split(/(?<=[.!?])\s+(?=[A-Z"'])/);
  return parts.map((s) => s.trim()).filter(Boolean);
}

function IndexTickerCell({
  config,
  liveValue,
  livePerf,
}: {
  config: IndexConfig;
  liveValue: number;
  livePerf: number;
}) {
  const isUp = livePerf >= 0;
  // Index point values render without decimals (50,285 not 50,285.16) for
  // readability — that's how they're quoted in financial press.
  const valueStr = liveValue.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
  return (
    <Link
      href={`/stocks/${config.clickTarget}` as Route}
      className="block rounded-lg border border-border/60 bg-white/60 px-3 py-2 transition-colors hover:bg-white"
    >
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {config.label}
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
          {fmtPct(livePerf)}
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
