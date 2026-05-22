"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import {
  BrainCircuit,
  Coins,
  Eye,
  Gem,
  Loader2,
  Lock,
  MessageSquareText,
  Newspaper,
  Rocket,
  Star,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getScreenerPresets } from "@/lib/api";
import type { ScreenerPresetSummary } from "@/lib/contracts";

/**
 * Section 6 — Stock Screener / Algorithmic Recommendations.
 *
 * 3×3 grid of 9 algorithm-generated stock lists (1 col on mobile,
 * 2 on tablet, 3 on desktop). Modeled on the Seeking Alpha screener
 * tile pattern Jimmy referenced on 2026-05-21.
 *
 * **Phase 1f (2026-05-22):** preset cards now fetch from
 * `GET /api/screener/presets` for real result counts and sample
 * tickers. Click target is `/stocks/screener?preset=<slug>` — the
 * existing screener page reads the `preset` query param and calls
 * the per-preset results endpoint, which enforces tier via 402 for
 * Strategist / Quant presets (existing global SoftPaywall modal
 * intercepts).
 *
 * Falls back to a hardcoded preset list (matching the backend's
 * `screener_presets.py`) if the summary endpoint errors — visual
 * shape stays stable but counts / samples may be off.
 */

type Tier = "scout" | "strategist" | "quant";

const ICON_MAP: Record<string, LucideIcon> = {
  BrainCircuit,
  TrendingUp,
  Rocket,
  Star,
  Coins,
  Gem,
  Newspaper,
  MessageSquareText,
  Eye,
};

// Shape-only fallback. Mirror of `all_presets()` order in
// `apps/api/app/services/screener_presets.py`. Used until the summary
// fetch resolves so the tiles render immediately on first paint.
const FALLBACK_PRESETS: ScreenerPresetSummary[] = [
  { slug: "trending-ai", title: "Trending AI Stocks", description: "AI-themed equities — semiconductors, hyperscalers, infra software, model labs.", icon: "BrainCircuit", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "top-growth", title: "Top Growth Stocks", description: "Mega/large-cap tech, communication & discretionary — revenue compounders.", icon: "TrendingUp", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "top-small-cap", title: "Top Small Cap Stocks", description: "Market cap $300M–$2B. Higher risk / higher growth potential.", icon: "Rocket", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "top-rated", title: "Top Rated Stocks", description: "Mega/large-cap names trading at reasonable P/E — quality + value blend.", icon: "Star", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "top-dividend", title: "Top Dividend Stocks", description: "Dividend yield ≥ 4%, sorted high → low. Income-focused.", icon: "Coins", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "top-value", title: "Top Value Stocks", description: "P/E < 15 and market cap ≥ $2B. Sorted cheapest-first.", icon: "Gem", tier: "scout", result_count: 0, sample_tickers: [] },
  { slug: "positive-catalyst", title: "Positive Catalyst Watchlist", description: "Stocks with recent positive catalysts.", icon: "Newspaper", tier: "strategist", result_count: 0, sample_tickers: [] },
  { slug: "community-confirmed", title: "News Confirmed by Community", description: "Headlines the community is amplifying.", icon: "MessageSquareText", tier: "strategist", result_count: 0, sample_tickers: [] },
  { slug: "rising-attention", title: "Rising Attention Stocks", description: "Sentiment + volume both surging — unusual interest, early signal.", icon: "Eye", tier: "quant", result_count: 0, sample_tickers: [] },
];

export function Screener() {
  const [presets, setPresets] = useState<ScreenerPresetSummary[]>(FALLBACK_PRESETS);
  const [loading, setLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getScreenerPresets()
      .then((r) => {
        if (!cancelled) {
          setPresets(r.presets);
          setIsLive(true);
        }
      })
      .catch(() => {
        /* leave fallback in place */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
        {loading ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading
          </span>
        ) : isLive ? (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
            Live · {presets.reduce((sum, p) => sum + p.result_count, 0)} matches
          </span>
        ) : (
          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
            Counts unavailable
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Pre-built algorithmic screens curated by Livermore. Click any card
        to open the full filtered list in the screener.
      </p>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {presets.map((s) => (
          <ScreenerCard key={s.slug} screen={s} />
        ))}
      </div>
    </section>
  );
}

function ScreenerCard({ screen }: { screen: ScreenerPresetSummary }) {
  const Icon = ICON_MAP[screen.icon] ?? Gem;
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

      {screen.sample_tickers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {screen.sample_tickers.map((t) => (
            <span
              key={t}
              className="rounded-md bg-muted/50 px-1.5 py-0.5 font-mono text-[10px] font-medium text-foreground/70"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
        <span>{screen.result_count > 0 ? `${screen.result_count} stocks` : "—"}</span>
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
