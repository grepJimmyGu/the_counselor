"use client";

/**
 * <HomeThemesFiringToday> — PRD-24a §4 (Focus 1 discovery cards).
 *
 * Three curated theme cards. Each shows a live match count + top-3 tickers
 * (with price + day-over-day %, the §3.8 cardinal rule) and routes to its
 * results surface:
 *   1. Positive Catalyst Watchlist  → /sentiment?toolkit=positive_catalyst
 *   2. Best Momentum Pick           → custom_build_mode (best_momentum scan)
 *   3. Mainstream Buyers Focus      → /sentiment?toolkit=news_community_confirmed
 *
 * Sentiment cards call /api/sentiment/analyze over the shared 20-symbol
 * DEFAULT_SENTIMENT_SYMBOLS; the momentum card runs the best_momentum scan
 * preset from the recommended-template registry. v1 fetches live on mount
 * (the endpoints cache server-side); the 6am-ET pre-compute cron is §1.6.
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Loader2, Rocket, Sparkles, Users } from "lucide-react";
import { runSentimentAnalyze, screenScan } from "@/lib/api";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { cn } from "@/lib/utils";
import { DEFAULT_SENTIMENT_SYMBOLS } from "@/lib/sentiment-defaults";
import {
  getRecommendedTemplate,
  type ComposerTemplate,
} from "@/lib/recommended-templates";

type ThemeResult = { count: number; top: string[] };
type ThemeState = ThemeResult | "loading" | "error";

interface ThemeDef {
  id: string;
  label: string;
  reading: string;
  href: Route;
  icon: React.ComponentType<{ className?: string }>;
  load: () => Promise<ThemeResult>;
}

const bestMomentum = getRecommendedTemplate("best_momentum") as ComposerTemplate;

const THEMES: ThemeDef[] = [
  {
    id: "positive_catalyst",
    label: "Positive Catalyst Watchlist",
    reading:
      "Stocks where a meaningful positive event just hit — earnings beat, upgrade, insider buying, news catalyst.",
    href: "/sentiment?toolkit=positive_catalyst&autorun=1" as Route,
    icon: Sparkles,
    load: async () => {
      const r = await runSentimentAnalyze(
        DEFAULT_SENTIMENT_SYMBOLS,
        "positive_catalyst",
      );
      return {
        count: r.candidates.length,
        top: r.candidates.slice(0, 3).map((c) => c.symbol),
      };
    },
  },
  {
    id: "best_momentum",
    label: "Best Momentum Pick",
    reading: bestMomentum.tagline,
    href: "/flow/custom_build_mode?template=best_momentum&universe=sp500" as Route,
    icon: Rocket,
    load: async () => {
      const r = await screenScan({
        universe_id: bestMomentum.universe_id,
        rules: bestMomentum.rules,
      });
      return { count: r.matched_count, top: r.matched.slice(0, 3) };
    },
  },
  {
    id: "news_community_confirmed",
    label: "Mainstream Buyers Focus",
    reading:
      "Both the news flow and the Livermore community are leaning bullish — a convergence signal.",
    href: "/sentiment?toolkit=news_community_confirmed&autorun=1&display=mainstream_buyers" as Route,
    icon: Users,
    load: async () => {
      const r = await runSentimentAnalyze(
        DEFAULT_SENTIMENT_SYMBOLS,
        "news_community_confirmed",
      );
      return {
        count: r.candidates.length,
        top: r.candidates.slice(0, 3).map((c) => c.symbol),
      };
    },
  },
];

/** A top-3 ticker chip with price + day-over-day % (§3.8). */
function TickerChip({
  symbol,
  quote,
}: {
  symbol: string;
  quote?: { price: number; change_percent: number };
}) {
  const positive = quote ? quote.change_percent >= 0 : false;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-muted/40 px-2 py-1 text-xs">
      <span className="font-mono font-semibold">{symbol}</span>
      {quote ? (
        <span
          className={cn(
            "font-mono tabular-nums",
            positive ? "text-emerald-600" : "text-rose-600",
          )}
        >
          {positive ? "+" : ""}
          {quote.change_percent.toFixed(1)}%
        </span>
      ) : null}
    </span>
  );
}

export function HomeThemesFiringToday() {
  const [states, setStates] = React.useState<Record<string, ThemeState>>(() =>
    Object.fromEntries(THEMES.map((t) => [t.id, "loading"])),
  );

  React.useEffect(() => {
    let cancelled = false;
    for (const t of THEMES) {
      t.load()
        .then((r) => {
          if (!cancelled) setStates((s) => ({ ...s, [t.id]: r }));
        })
        .catch(() => {
          if (!cancelled) setStates((s) => ({ ...s, [t.id]: "error" }));
        });
    }
    return () => {
      cancelled = true;
    };
  }, []);

  const allTickers = React.useMemo(() => {
    const set = new Set<string>();
    for (const t of THEMES) {
      const st = states[t.id];
      if (st && st !== "loading" && st !== "error") st.top.forEach((s) => set.add(s));
    }
    return Array.from(set);
  }, [states]);
  const { quotes } = useLiveQuotes(allTickers);

  return (
    <div data-testid="home-themes-firing-today">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-heading text-base font-semibold">Themes firing today</h3>
        <span className="text-xs text-muted-foreground">Find what&rsquo;s worth your attention</span>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {THEMES.map((t) => {
          const st = states[t.id];
          const Icon = t.icon;
          return (
            <Link
              key={t.id}
              href={t.href}
              data-testid={`home-theme-${t.id}`}
              className="group flex flex-col rounded-2xl border border-border/60 bg-white p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg"
            >
              <div className="mb-3 flex items-center justify-between">
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
                  <Icon className="h-5 w-5 text-primary" />
                </span>
                {st === "loading" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : st === "error" ? (
                  <span className="text-xs text-muted-foreground">—</span>
                ) : (
                  <span
                    data-testid={`home-theme-count-${t.id}`}
                    className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700"
                  >
                    {st.count} {st.count === 1 ? "match" : "matches"}
                  </span>
                )}
              </div>

              <h4 className="font-heading text-sm font-semibold">{t.label}</h4>
              <p className="mt-1 flex-1 text-xs leading-relaxed text-muted-foreground">
                {t.reading}
              </p>

              {st !== "loading" && st !== "error" && st.top.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {st.top.map((sym) => (
                    <TickerChip key={sym} symbol={sym} quote={quotes[sym.toUpperCase()]} />
                  ))}
                </div>
              ) : null}

              <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-primary">
                View all
                <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
