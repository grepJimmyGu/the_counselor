"use client";

/**
 * <HomeHeroSearch> — PRD-24a §3.3 hero lookup with in-place stock preview.
 *
 * Not a search-and-navigate: picking a result expands a preview drawer
 * *in place* (the same pattern PR-#228/#230 shipped on the portfolio
 * diagnose flow) that lazy-fetches getCompanyOverview and renders the
 * SAME stock-profile sections — <EvaluationDashboard> + <BusinessModelSection>
 * (lifted to @/components/stocks in PRD-24a §0.1). The header bar always
 * shows current price + day-over-day % (the §3.8 cardinal rule) from
 * /api/live-quotes. Two CTAs: open the full detail in a new tab, or apply
 * a strategy (launches one_asset_mode with the ticker pre-loaded).
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, ExternalLink, Loader2, Search, X } from "lucide-react";
import { getCompanyOverview, searchSymbols } from "@/lib/api";
import type { CompanyOverviewResponse, SymbolSearchItem } from "@/lib/contracts";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { cn } from "@/lib/utils";
import { EvaluationDashboard } from "@/components/stocks/evaluation-dashboard";
import { BusinessModelSection } from "@/components/stocks/business-model-section";
import { startFlow } from "@/lib/flows/runtime";
// Side-effect import — registers `one_asset_mode` so startFlow can find it.
import "@/lib/flows/one-asset-mode";

/** Price + day-over-day % header (the §3.8 cardinal rule). */
function QuoteHeader({ symbol, name }: { symbol: string; name: string | null }) {
  const { quotes } = useLiveQuotes([symbol]);
  const q = quotes[symbol.toUpperCase()];
  const positive = q ? q.change_percent >= 0 : false;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="font-mono text-lg font-bold">{symbol}</span>
      {q ? (
        <>
          <span className="font-mono text-lg font-semibold tabular-nums">
            ${q.price.toFixed(2)}
          </span>
          <span
            data-testid="home-hero-quote-change"
            className={cn(
              "font-mono text-sm font-semibold tabular-nums",
              positive ? "text-emerald-600" : "text-rose-600",
            )}
          >
            {positive ? "+" : ""}
            {q.change_percent.toFixed(2)}%
          </span>
          <span className="text-[11px] text-muted-foreground">15 min delayed</span>
        </>
      ) : (
        <span className="text-xs text-muted-foreground">Loading quote…</span>
      )}
      {name && name !== symbol ? (
        <span className="w-full text-sm text-muted-foreground">{name}</span>
      ) : null}
    </div>
  );
}

export function HomeHeroSearch() {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = React.useState(false);
  const [selected, setSelected] = React.useState<SymbolSearchItem | null>(null);
  const [overview, setOverview] = React.useState<
    CompanyOverviewResponse | "loading" | "error" | null
  >(null);

  React.useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const t = window.setTimeout(() => {
      searchSymbols(query.trim())
        .then((r) => {
          if (!cancelled) setResults(r.slice(0, 6));
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
      setSearching(false);
    };
  }, [query]);

  const select = (item: SymbolSearchItem) => {
    setSelected(item);
    setResults([]);
    setQuery("");
    setOverview("loading");
    getCompanyOverview(item.symbol)
      .then((o) => setOverview(o))
      .catch(() => setOverview("error"));
  };

  const close = () => {
    setSelected(null);
    setOverview(null);
  };

  return (
    <div className="mx-auto max-w-2xl text-left">
      {/* Search input */}
      <div className="relative">
        <div className="flex items-center gap-3 rounded-xl border border-border bg-white px-4 py-3 shadow-sm transition-all focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
          <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Look up a stock or ETF… e.g. NVDA, Apple"
            inputMode="search"
            autoCorrect="off"
            spellCheck={false}
            data-testid="home-hero-search-input"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {searching ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
          ) : null}
        </div>

        {results.length > 0 ? (
          <ul
            data-testid="home-hero-search-results"
            className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-border bg-white shadow-lg"
          >
            {results.map((item) => (
              <li key={item.symbol}>
                <button
                  type="button"
                  onClick={() => select(item)}
                  data-testid={`home-hero-search-result-${item.symbol}`}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50"
                >
                  <span className="w-14 font-mono text-sm font-bold">{item.symbol}</span>
                  <span className="flex-1 truncate text-sm text-muted-foreground">
                    {item.name}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {/* In-place preview drawer */}
      {selected ? (
        <div
          data-testid="home-hero-preview"
          className="mt-3 overflow-hidden rounded-xl border border-border bg-white shadow-sm"
        >
          <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
            <QuoteHeader symbol={selected.symbol} name={selected.name} />
            <button
              type="button"
              onClick={close}
              aria-label="Close preview"
              className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-5 p-5">
            {overview === "loading" || overview === null ? (
              <div
                className="flex justify-center py-10"
                data-testid="home-hero-preview-loading"
              >
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : overview === "error" ? (
              <p className="text-sm text-muted-foreground">
                Couldn&rsquo;t load {selected.symbol}.{" "}
                <Link
                  href={`/stocks/${selected.symbol}` as Route}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary hover:underline"
                >
                  Open the full profile ↗
                </Link>
              </p>
            ) : (
              <>
                <section>
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Fundamental analysis
                  </h3>
                  <EvaluationDashboard data={overview} />
                </section>
                <section>
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Business model
                  </h3>
                  <BusinessModelSection
                    seg={overview.revenue_segments}
                    bm={overview.business_map}
                  />
                </section>
              </>
            )}

            <div className="flex flex-wrap gap-3 border-t border-border pt-4">
              <Link
                href={`/stocks/${selected.symbol}` as Route}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="home-hero-open-detail"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-muted/30"
              >
                Open full detail <ExternalLink className="h-3.5 w-3.5" />
              </Link>
              <button
                type="button"
                data-testid="home-hero-apply-strategy"
                onClick={() =>
                  startFlow("one_asset_mode", {
                    initialContext: {
                      fromTrigger: "home/hero_preview",
                      ticker: selected.symbol,
                    },
                  })
                }
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Apply a strategy <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
