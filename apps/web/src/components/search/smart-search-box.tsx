"use client";

/**
 * <SmartSearchBox> — PRD-27 unified entry (replaces <HomeHeroSearch>).
 *
 * One box, two behaviours:
 *   - **Autocomplete-select a company** → the in-place preview drawer (the
 *     PRD-24a §3.3 pattern, unchanged): quote header + <EvaluationDashboard>
 *     + <BusinessModelSection>, with "open full detail" / "apply a strategy".
 *   - **Submit free text (Enter / the arrow)** → POST /api/search/parse:
 *       COMPANY   → open that company's preview drawer.
 *       SCREEN    → hydrate the parsed rules into the composer and run
 *                   (launchScreenFromParsedRules → custom_build_mode).
 *       AMBIGUOUS → show the "ask" note; never guess.
 *
 * Descriptive, tool framing throughout — the box routes, it doesn't advise.
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import {
  ArrowRight,
  ExternalLink,
  Globe,
  Loader2,
  Search,
  SlidersHorizontal,
  Star,
  X,
} from "lucide-react";

import {
  getCompanyOverview,
  listSavedScreens,
  parseSearch,
  searchSymbols,
} from "@/lib/api";
import type {
  CompanyOverviewResponse,
  SavedScreenSummary,
  SymbolSearchItem,
} from "@/lib/contracts";
import { ConditionBuilder } from "@/components/search/condition-builder";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { cn } from "@/lib/utils";
import { EvaluationDashboard } from "@/components/stocks/evaluation-dashboard";
import { BusinessModelSection } from "@/components/stocks/business-model-section";
import { startFlow } from "@/lib/flows/runtime";
import { launchScreenFromParsedRules } from "@/lib/flows/launch-screen";
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
            data-testid="smart-search-quote-change"
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

export function SmartSearchBox() {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [note, setNote] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<SymbolSearchItem | null>(null);
  const [overview, setOverview] = React.useState<
    CompanyOverviewResponse | "loading" | "error" | null
  >(null);

  // Which control-row panel is open (only one at a time).
  const [panel, setPanel] = React.useState<"conditions" | "saved" | null>(null);
  const [savedScreens, setSavedScreens] = React.useState<SavedScreenSummary[] | null>(
    null,
  );

  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  // Load saved screens lazily — only when the panel is actually opened, and
  // only once. Waits for NextAuth to resolve, otherwise a signed-in user fires
  // an anonymous request during the loading window (backend trap #19).
  React.useEffect(() => {
    if (panel !== "saved" || sessionStatus === "loading") return;
    if (!backendToken || savedScreens !== null) return;
    let cancelled = false;
    listSavedScreens({ backendToken })
      .then((resp) => {
        if (!cancelled) setSavedScreens(resp.screens);
      })
      .catch(() => {
        if (!cancelled) setSavedScreens([]);
      });
    return () => {
      cancelled = true;
    };
  }, [panel, sessionStatus, backendToken, savedScreens]);

  // Autocomplete (company lookup) — unchanged from the hero.
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

  const openCompany = React.useCallback((item: SymbolSearchItem) => {
    setSelected(item);
    setResults([]);
    setNote(null);
    setQuery("");
    setOverview("loading");
    getCompanyOverview(item.symbol)
      .then((o) => setOverview(o))
      .catch(() => setOverview("error"));
  }, []);

  const close = () => {
    setSelected(null);
    setOverview(null);
  };

  // Submit (Enter / arrow) → dispatch the query.
  const handleSubmit = React.useCallback(async () => {
    const q = query.trim();
    if (!q || submitting) return;
    setSubmitting(true);
    setNote(null);
    setResults([]);
    try {
      const result = await parseSearch(q);
      if (result.intent === "company" && result.symbol) {
        openCompany({ symbol: result.symbol, name: result.company_name ?? result.symbol });
        return;
      }
      if (result.intent === "screen" && result.screen) {
        const launched = await launchScreenFromParsedRules(
          result.screen.rules,
          result.screen.universe_id,
          result.screen.symbols,
          result.note ?? undefined,
        );
        if (!launched) {
          setNote(
            "Couldn't turn that into a screen — try naming an indicator, e.g. “RSI below 30”.",
          );
        }
        return; // launched → navigates away
      }
      // AMBIGUOUS (or company with no symbol) → ask, never guess.
      setNote(
        result.note ??
          "Not sure what you meant — try a ticker (NVDA) or a screen like “oversold above the 200-day”.",
      );
    } catch {
      setNote("Search failed. Try again.");
    } finally {
      setSubmitting(false);
    }
  }, [query, submitting, openCompany]);

  return (
    <div className="mx-auto max-w-2xl text-left">
      <div className="relative">
        {/* One bordered container holding the input AND its controls — the
            box is a single object, not an input with chrome floating near it. */}
        <div className="rounded-xl border border-border bg-white shadow-sm transition-all focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
          <div className="flex items-center gap-3 px-4 py-3">
          <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleSubmit();
              }
            }}
            placeholder="A ticker, a company, or a screen… e.g. NVDA · oversold above the 200-day"
            inputMode="search"
            autoCorrect="off"
            spellCheck={false}
            data-testid="smart-search-input"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {searching || submitting ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
          ) : (
            <button
              type="button"
              onClick={() => void handleSubmit()}
              aria-label="Search"
              data-testid="smart-search-submit"
              className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowRight className="h-4 w-4" />
            </button>
          )}
          </div>

          {/* Control row — inside the box, 問財-style: scope · conditions ·
              saved. The box is the product, so its controls live with it
              rather than as chrome scattered around the page. */}
          <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
            <span
              data-testid="smart-search-scope"
              title="US equities only for now"
              className="inline-flex items-center gap-1.5 rounded-full bg-primary/8 px-2.5 py-1 text-[11px] font-medium text-primary"
            >
              <Globe className="h-3 w-3" />
              US equities
            </span>

            <button
              type="button"
              onClick={() => setPanel((p) => (p === "conditions" ? null : "conditions"))}
              aria-expanded={panel === "conditions"}
              data-testid="smart-search-conditions"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                panel === "conditions"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
              )}
            >
              <SlidersHorizontal className="h-3 w-3" />
              Conditions
            </button>

            <button
              type="button"
              onClick={() => setPanel((p) => (p === "saved" ? null : "saved"))}
              aria-expanded={panel === "saved"}
              data-testid="smart-search-saved"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                panel === "saved"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
              )}
            >
              <Star className="h-3 w-3" />
              Saved
            </button>
          </div>
        </div>

        {/* Conditions — the shipped PRD-16a catalog browser, reused whole.
            Picking a primitive appends its name to the query so the user can
            see and edit what they're asking for, rather than composing an
            invisible rule set. */}
        {panel === "conditions" ? (
          <div
            data-testid="smart-search-conditions-panel"
            className="mt-2 max-h-[460px] overflow-y-auto rounded-xl border border-border bg-white p-4 shadow-lg"
          >
            <ConditionBuilder
              onAppend={(phrase) =>
                setQuery((q) => (q.trim() ? `${q.trim()}; ${phrase}` : phrase))
              }
            />
          </div>
        ) : null}

        {/* Saved — the user's saved screens. Sign-in gated by data, not by a
            teaser: with no token there is nothing to list. */}
        {panel === "saved" ? (
          <div
            data-testid="smart-search-saved-panel"
            className="mt-2 overflow-hidden rounded-xl border border-border bg-white shadow-lg"
          >
            {!backendToken ? (
              <p className="px-4 py-3 text-[13px] text-muted-foreground">
                Sign in to see your saved screens.
              </p>
            ) : savedScreens === null ? (
              <p className="px-4 py-3 text-[13px] text-muted-foreground">Loading…</p>
            ) : savedScreens.length === 0 ? (
              <p className="px-4 py-3 text-[13px] text-muted-foreground">
                No saved screens yet — run one and save it.
              </p>
            ) : (
              <ul>
                {savedScreens.map((s) => (
                  <li key={s.saved_strategy_id}>
                    <Link
                      href={`/screens/${s.saved_strategy_id}` as Route}
                      data-testid={`smart-search-saved-${s.saved_strategy_id}`}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50"
                    >
                      <span className="truncate text-sm text-foreground">{s.title}</span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {s.basket_size} {s.basket_size === 1 ? "name" : "names"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {results.length > 0 ? (
          <ul
            data-testid="smart-search-results"
            className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-border bg-white shadow-lg"
          >
            {results.map((item) => (
              <li key={item.symbol}>
                <button
                  type="button"
                  onClick={() => openCompany(item)}
                  data-testid={`smart-search-result-${item.symbol}`}
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

      {note ? (
        <p
          data-testid="smart-search-note"
          className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800"
        >
          {note}
        </p>
      ) : null}

      {selected ? (
        <div
          data-testid="smart-search-preview"
          className="mt-3 overflow-hidden rounded-xl border border-border bg-white shadow-sm lg:relative lg:left-1/2 lg:w-[min(1080px,calc(100vw-3rem))] lg:max-w-none lg:-translate-x-1/2"
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
                data-testid="smart-search-preview-loading"
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
                data-testid="smart-search-open-detail"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-muted/30"
              >
                Open full detail <ExternalLink className="h-3.5 w-3.5" />
              </Link>
              <button
                type="button"
                data-testid="smart-search-apply-strategy"
                onClick={() =>
                  startFlow("one_asset_mode", {
                    initialContext: {
                      fromTrigger: "home/smart_search_preview",
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
