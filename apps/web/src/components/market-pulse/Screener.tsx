"use client";

import Link from "next/link";
import type { Route } from "next";
import {
  BrainCircuit,
  Coins,
  Eye,
  Gem,
  Lock,
  MessageSquareText,
  Newspaper,
  Rocket,
  Star,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Section 6 — Stock Screener / Algorithmic Recommendations.
 *
 * 3×2 grid of 6 algorithm-generated stock lists (1 col on mobile,
 * 2 on tablet, 3 on desktop). Modeled on the Seeking Alpha screener
 * tile pattern Jimmy referenced on 2026-05-21.
 *
 * **Phase 0a status:** each card is a visual stub with hardcoded sample
 * tickers + a mock result count. Click target is
 * `/stocks/screener?preset=<slug>` — the existing screener page exists,
 * Phase 1 wires the preset filter on the backend.
 *
 * **Tier gating:** 3 of the 6 cards are flagged with a tier badge
 * ("Strategist" / "Quant"). Phase 0a renders the badge visually; the
 * existing entitlements layer (`require_entitlement` + the `SoftPaywall`
 * 402 interceptor) handles real enforcement when the user clicks
 * through. Visual today, enforced in Phase 1.
 */

type Tier = "scout" | "strategist" | "quant";

interface ScreenCard {
  slug: string;
  title: string;
  description: string;
  icon: LucideIcon;
  resultCount: number;
  sampleTickers: string[];
  tier: Tier;
}

const SCREENS: ScreenCard[] = [
  {
    slug: "trending-ai",
    title: "Trending AI Stocks",
    description:
      "AI-themed equities ranked by recent momentum + capital inflow.",
    icon: BrainCircuit,
    resultCount: 24,
    sampleTickers: ["NVDA", "AMD", "GOOGL", "MSFT", "AVGO"],
    tier: "scout",
  },
  {
    slug: "top-growth",
    title: "Top Growth Stocks",
    description:
      "Revenue + earnings compounders, ranked by 3-yr growth + ROIC.",
    icon: TrendingUp,
    resultCount: 38,
    sampleTickers: ["NVDA", "META", "AMZN", "NFLX", "TSLA"],
    tier: "scout",
  },
  {
    slug: "top-small-cap",
    title: "Top Small Cap Stocks",
    description:
      "Market cap < $2B with positive momentum + improving fundamentals.",
    icon: Rocket,
    resultCount: 17,
    sampleTickers: ["SOFI", "RIVN", "FUBO", "IONQ", "BBAI"],
    tier: "scout",
  },
  {
    slug: "top-rated",
    title: "Top Rated Stocks",
    description:
      "Analyst consensus Strong Buy + Livermore quant rating in top decile.",
    icon: Star,
    resultCount: 22,
    sampleTickers: ["NVDA", "MSFT", "AAPL", "GOOGL", "META"],
    tier: "scout",
  },
  {
    slug: "top-dividend",
    title: "Top Dividend Stocks",
    description:
      "High dividend yield with growth + safety guardrails (>4% sustainable).",
    icon: Coins,
    resultCount: 31,
    sampleTickers: ["JNJ", "XOM", "KO", "PFE", "VZ"],
    tier: "scout",
  },
  {
    slug: "top-value",
    title: "Top Value Stocks",
    description:
      "Low P/E + high free-cash-flow yield, screened for trap avoidance.",
    icon: Gem,
    resultCount: 19,
    sampleTickers: ["JPM", "BAC", "C", "WFC", "GS"],
    tier: "scout",
  },
  {
    slug: "positive-catalyst",
    title: "Positive Catalyst Watchlist",
    description:
      "Stocks with recent positive catalysts identified by news sentiment.",
    icon: Newspaper,
    resultCount: 12,
    sampleTickers: ["TSLA", "COIN", "PLTR", "RIVN"],
    tier: "strategist",
  },
  {
    slug: "community-confirmed",
    title: "News Confirmed by Community",
    description:
      "Headlines that community votes + watchlists are amplifying right now.",
    icon: MessageSquareText,
    resultCount: 9,
    sampleTickers: ["NVDA", "AAPL", "AMZN", "TSLA"],
    tier: "strategist",
  },
  {
    slug: "rising-attention",
    title: "Rising Attention Stocks",
    description:
      "Sentiment + volume both surging — unusual interest, early signal.",
    icon: Eye,
    resultCount: 6,
    sampleTickers: ["PLTR", "SOFI", "COIN", "RBLX"],
    tier: "quant",
  },
];

export function Screener() {
  return (
    <section
      id="screener"
      aria-labelledby="screener-heading"
      className="space-y-3"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2
          id="screener-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Stock Screener
        </h2>
        <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
          Preview · mock data
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Pre-built algorithmic screens curated by Livermore. Click any card
        to open the full filtered list in the screener.
      </p>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {SCREENS.map((s) => (
          <ScreenerCard key={s.slug} screen={s} />
        ))}
      </div>
    </section>
  );
}

function ScreenerCard({ screen }: { screen: ScreenCard }) {
  const Icon = screen.icon;
  const isGated = screen.tier !== "scout";
  return (
    <Link
      href={`/stocks/screener?preset=${screen.slug}` as Route}
      className="block rounded-xl border border-border bg-white p-4 transition-all hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "rounded-lg p-2 shrink-0",
            screen.tier === "scout"
              ? "bg-primary/10 text-primary"
              : screen.tier === "strategist"
                ? "bg-amber-100 text-amber-700"
                : "bg-violet-100 text-violet-700",
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold leading-tight">
              {screen.title}
            </h3>
            {isGated && (
              <TierBadge tier={screen.tier as "strategist" | "quant"} />
            )}
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground leading-snug">
            {screen.description}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {screen.sampleTickers.map((t) => (
          <span
            key={t}
            className="rounded-md bg-muted/50 px-1.5 py-0.5 font-mono text-[10px] font-medium text-foreground/70"
          >
            {t}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
        <span>{screen.resultCount} stocks</span>
        <span className="font-medium text-primary">View all →</span>
      </div>
    </Link>
  );
}

function TierBadge({ tier }: { tier: "strategist" | "quant" }) {
  const cls =
    tier === "strategist"
      ? "border-amber-300 bg-amber-50 text-amber-900"
      : "border-violet-300 bg-violet-50 text-violet-900";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide shrink-0",
        cls,
      )}
    >
      <Lock className="h-2.5 w-2.5" />
      {tier}
    </span>
  );
}
