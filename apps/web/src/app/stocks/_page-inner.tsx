"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { ArrowUpDown, ChevronDown, ChevronUp, Search, SlidersHorizontal, X } from "lucide-react";
import { getScreenerFilters, getScreenerResults } from "@/lib/api";
import type { ScreenerFiltersResponse, ScreenerResult } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

// ── Constants ─────────────────────────────────────────────────────────────────

const GICS_SECTORS = [
  "Energy", "Materials", "Industrials", "Consumer Discretionary",
  "Consumer Staples", "Health Care", "Financials", "Information Technology",
  "Communication Services", "Utilities", "Real Estate",
];

const CAP_LABELS: Record<string, string> = {
  mega: "Mega (>$200B)", large: "Large ($10–200B)",
  mid: "Mid ($2–10B)", small: "Small ($300M–2B)", micro: "Micro (<$300M)",
};

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return n.toFixed(decimals);
}

// ── Screener page ─────────────────────────────────────────────────────────────

export function StocksPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [filtersMeta, setFiltersMeta] = useState<ScreenerFiltersResponse | null>(null);
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortBy, setSortBy] = useState(searchParams.get("sort_by") || "market_cap");
  const [sortOrder, setSortOrder] = useState(searchParams.get("sort_order") || "desc");

  // Active filters from URL
  function getParam(key: string) { return searchParams.get(key) || ""; }

  const activeFilters = {
    sector: getParam("sector"),
    industry: getParam("industry"),
    country: getParam("country"),
    market_cap_category: getParam("market_cap_category"),
    min_pe: getParam("min_pe"),
    max_pe: getParam("max_pe"),
  };

  const activeCount = Object.values(activeFilters).filter(Boolean).length;

  function updateFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value); else params.delete(key);
    params.delete("offset");
    router.replace(`/stocks?${params.toString()}`, { scroll: false });
  }

  function clearAll() {
    router.replace("/stocks", { scroll: false });
  }

  function toggleSort(col: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (sortBy === col) {
      const next = sortOrder === "desc" ? "asc" : "desc";
      setSortOrder(next);
      params.set("sort_order", next);
    } else {
      setSortBy(col);
      setSortOrder("desc");
      params.set("sort_by", col);
      params.set("sort_order", "desc");
    }
    router.replace(`/stocks?${params.toString()}`, { scroll: false });
  }

  const fetchResults = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | undefined> = {};
      searchParams.forEach((v, k) => { params[k] = v; });
      if (!params.sort_by) params.sort_by = "market_cap";
      if (!params.sort_order) params.sort_order = "desc";
      params.limit = 50;
      const data = await getScreenerResults(params);
      setResults(data.results);
      setTotal(data.total);
    } catch { setResults([]); setTotal(0); }
    finally { setLoading(false); }
  }, [searchParams]);

  useEffect(() => {
    getScreenerFilters().then(setFiltersMeta).catch(() => {});
  }, []);

  useEffect(() => { fetchResults(); }, [fetchResults]);

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1400px] px-4 py-6 md:px-6 lg:px-8">

        {/* Page header */}
        <div className="mb-6 flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="font-heading text-2xl font-bold">Stock Screener</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {filtersMeta ? `${filtersMeta.total_symbols.toLocaleString()} symbols` : "Loading…"}
              {total > 0 && activeCount > 0 ? ` · ${total.toLocaleString()} matching` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {activeCount > 0 && (
              <Button variant="ghost" size="sm" onClick={clearAll} className="text-muted-foreground">
                <X className="mr-1 h-3.5 w-3.5" /> Clear filters
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFiltersOpen((v) => !v)}
              className={cn(activeCount > 0 && "border-primary text-primary")}
            >
              <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" />
              Filters {activeCount > 0 && <Badge className="ml-1.5 bg-primary/15 text-primary text-[10px] px-1.5">{activeCount}</Badge>}
            </Button>
          </div>
        </div>

        {/* Browse by Sector strip */}
        <div className="mb-5 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => updateFilter("sector", "")}
            className={cn("cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150",
              !activeFilters.sector ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
            )}
          >
            All Sectors
          </button>
          {GICS_SECTORS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => updateFilter("sector", activeFilters.sector === s ? "" : s)}
              className={cn("cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150",
                activeFilters.sector === s
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Expanded filter panel */}
        {filtersOpen && filtersMeta && (
          <div className="mb-5 grid gap-4 rounded-xl border border-border bg-white p-5 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
            {/* Market Cap */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Market Cap</label>
              <select
                value={activeFilters.market_cap_category}
                onChange={(e) => updateFilter("market_cap_category", e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">Any</option>
                {filtersMeta.market_cap_categories.map((c) => (
                  <option key={c} value={c}>{CAP_LABELS[c] ?? c}</option>
                ))}
              </select>
            </div>
            {/* P/E Range */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">P/E Ratio</label>
              <div className="flex items-center gap-2">
                <Input
                  type="number" placeholder="Min" value={activeFilters.min_pe}
                  onChange={(e) => updateFilter("min_pe", e.target.value)}
                  className="h-9 text-sm"
                />
                <span className="text-xs text-muted-foreground">—</span>
                <Input
                  type="number" placeholder="Max" value={activeFilters.max_pe}
                  onChange={(e) => updateFilter("max_pe", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </div>
            {/* Industry */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Industry</label>
              <select
                value={activeFilters.industry}
                onChange={(e) => updateFilter("industry", e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">Any</option>
                {filtersMeta.industries.slice(0, 80).map((i) => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
            </div>
            {/* Country */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Country</label>
              <select
                value={activeFilters.country}
                onChange={(e) => updateFilter("country", e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">Any</option>
                {filtersMeta.countries.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Results table */}
        <div className="overflow-hidden rounded-xl border border-border bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  {[
                    { key: "symbol", label: "Symbol" },
                    { key: "name", label: "Company" },
                    { key: "sector", label: "Sector" },
                    { key: "market_cap", label: "Mkt Cap" },
                    { key: "pe_ratio", label: "P/E" },
                    { key: "dividend_yield", label: "Div Yield" },
                    { key: "beta", label: "Beta" },
                  ].map(({ key, label }) => (
                    <th
                      key={key}
                      className="cursor-pointer px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => toggleSort(key)}
                    >
                      <span className="flex items-center gap-1">
                        {label}
                        {sortBy === key
                          ? sortOrder === "desc" ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />
                          : <ArrowUpDown className="h-3 w-3 opacity-30" />
                        }
                      </span>
                    </th>
                  ))}
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="border-b border-border/50">
                        {Array.from({ length: 8 }).map((__, j) => (
                          <td key={j} className="px-4 py-3">
                            <Skeleton className="h-4 w-full" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : results.length === 0
                  ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-16 text-center text-sm text-muted-foreground">
                        {filtersMeta?.total_symbols === 0
                          ? "No symbols in database. Run the seed script: python -m app.scripts.seed_symbols"
                          : "No results match your filters."}
                      </td>
                    </tr>
                  )
                  : results.map((r) => (
                    <tr key={r.symbol} className="border-b border-border/40 transition-colors hover:bg-muted/20">
                      <td className="px-4 py-3">
                        <Link href={`/stocks/${r.symbol}` as Route} className="font-mono text-sm font-bold text-primary hover:underline">
                          {r.symbol}
                        </Link>
                      </td>
                      <td className="px-4 py-3 max-w-[200px] truncate font-medium">{r.name}</td>
                      <td className="px-4 py-3">
                        {r.sector && (
                          <button
                            type="button"
                            onClick={() => updateFilter("sector", r.sector!)}
                            className="cursor-pointer rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                          >
                            {r.sector}
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-sm">{fmt(r.market_cap)}</td>
                      <td className="px-4 py-3 font-mono text-sm">{r.pe_ratio ? r.pe_ratio.toFixed(1) : "—"}</td>
                      <td className="px-4 py-3 font-mono text-sm">
                        {r.dividend_yield ? `${(r.dividend_yield * 100).toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-sm">{r.beta ? r.beta.toFixed(2) : "—"}</td>
                      <td className="px-4 py-3">
                        <Link href={`/stocks/${r.symbol}` as Route} className="text-xs text-primary hover:underline">
                          View →
                        </Link>
                      </td>
                    </tr>
                  ))
                }
              </tbody>
            </table>
          </div>

          {/* Pagination info */}
          {!loading && total > 0 && (
            <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted-foreground">
              <span>Showing {results.length} of {total.toLocaleString()} results</span>
              <span>Sorted by {sortBy.replace("_", " ")} ({sortOrder})</span>
            </div>
          )}
        </div>

      </div>
    </main>
  );
}
