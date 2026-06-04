"use client";

/**
 * Market Pulse — `/stocks` route.
 *
 * Phase 1a (2026-05-22): promoted from the hidden `/uiux/market-pulse-v2`
 * preview into production. The composition delegates entirely to
 * `apps/web/src/components/market-pulse/*` — this file is just the
 * top-level shell holding page state, market toggle, refresh, and the
 * live-quote `withLive()` override.
 *
 * Mock data remains in 4 sections (Macro Pulse, History Rhymes, Stock
 * Screener counts, Sector comparison chart) with visible "Preview · mock"
 * badges. Phases 1b–1f progressively replace each.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, RefreshCw } from "lucide-react";
import { useMarketCopy } from "@/lib/market-copy";
import { CnStockSearch } from "@/components/market-pulse/CnStockSearch";

import { getMarketPulse } from "@/lib/api";
import type { MarketPulseResponse, SectorCard } from "@/lib/contracts";
import { buildNarrative } from "@/lib/market-pulse-narrative";

import { MarketBrief } from "@/components/market-pulse/MarketBrief";
import { MacroPulseTable } from "@/components/market-pulse/MacroPulseTable";
import { SectorRotation } from "@/components/market-pulse/SectorRotation";
import { HistoryRhymes } from "@/components/market-pulse/HistoryRhymes";
import { TopMovers, type MoverItem } from "@/components/market-pulse/TopMovers";
import { Screener } from "@/components/market-pulse/Screener";
import { StickySubNav } from "@/components/market-pulse/StickySubNav";
import { DataFreshnessFooter } from "@/components/market-pulse/DataFreshnessFooter";
import {
  BriefSkeleton,
  TopMoversSkeleton,
  SectorHeatmapSkeleton,
} from "@/components/market-pulse/SkeletonStates";

export function MarketPulsePage() {
  const [market, setMarket] = useState<"US" | "CN">("US");
  const [data, setData] = useState<MarketPulseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = (key: string) => useMarketCopy(key, market);

  const load = useCallback(async (m: "US" | "CN", showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const r = await getMarketPulse(m, showRefreshing);
      setData(r);
    } catch {
      setError(t("error_unavailable"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void load(market);
    }, 0);
    return () => window.clearTimeout(id);
  }, [market, load]);

  // ── Top Movers list assembly ────────────────────────────────────────────────
  // Merge top_assets (stocks) + featured_etfs (ETFs). Commodities dropped
  // per 2026-05-21 feedback. De-dup by symbol.
  const moverItems = useMemo<MoverItem[]>(() => {
    if (!data) return [];
    const seen = new Set<string>();
    const out: MoverItem[] = [];

    for (const a of data.top_assets) {
      if (seen.has(a.symbol)) continue;
      seen.add(a.symbol);
      out.push({
        card: a,
        category: "Stock",
        href: `/stocks/${a.symbol}`,
      });
    }
    for (const a of data.featured_etfs) {
      if (seen.has(a.symbol)) continue;
      seen.add(a.symbol);
      out.push({
        card: a,
        category: "ETF",
        href: `/stocks/${a.symbol}`,
      });
    }
    return out;
  }, [data]);

  // ── Narrative (Phase 1a — deterministic Layer A; LLM ships in Phase 1b) ─────
  const narrative = useMemo(
    () => (data ? buildNarrative(data) : null),
    [data],
  );

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-muted/20">
      <StickySubNav />
      <div className="mx-auto max-w-[1280px] space-y-6 px-4 py-6 md:px-6 lg:px-8">
        {/* Header */}
        <header className="flex items-center justify-between gap-3">
          <div>
            <h1 className="font-heading text-2xl font-bold tracking-tight">
              Market Pulse
            </h1>
            <p className="mt-0.5 text-xs text-muted-foreground">
              The narrative read first, then the data depth.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={market === "US" ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setMarket("US")}
            >
              {t("toggle_us")}
            </Badge>
            <Badge
              variant={market === "CN" ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setMarket("CN")}
            >
              {t("toggle_cn")}
            </Badge>
            <Button
              size="sm"
              variant="outline"
              onClick={() => load(market, true)}
              disabled={refreshing}
              className="gap-1.5"
            >
              {refreshing ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              Refresh
            </Button>
          </div>
        </header>

        {error && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            {error}
          </div>
        )}

        {/* Section 1 — Market Brief (narrative + inline 4-cell index ticker) */}
        {loading ? (
          <BriefSkeleton />
        ) : (
          data && <MarketBrief data={data} />
        )}

        {/* Section 2 — Macro Pulse table (4 signals: Growth / Inflation /
            Rates / Stress with 1M / 1Y / 3Y trend toggle + takeaways).
            Phase 1c: real CPI + 10Y Treasury yield via Alpha Vantage;
            Growth (ISM PMI) and Stress (HY OAS) remain mock pending
            a FRED API key. Per-row pill flips between Live + Mock.

            US-only: every signal in this table is a US macro indicator
            (CPI, 10Y Treasury, ISM PMI, HY OAS). Hide on CN to avoid
            misleading users into thinking these apply to A-share /
            HK markets. CN-specific macro signals are a future-phase
            ticket — see PROJECT_BACKLOG.md §4b follow-ups. */}
        {market === "US" && <MacroPulseTable signals={data?.macro_signals} />}

        {/* Section 3 — Sector rotation (heatmap default, table on toggle).
            Sector tile click → inline ETF-vs-SPY comparison chart. */}
        {loading ? (
          <SectorHeatmapSkeleton />
        ) : (
          data && (
            <SectorRotation
              sectors={data.sectors as SectorCard[]}
              market={market}
              rotationHeadline={
                // Phase 1b: prefer LLM-generated rotation interpretation;
                // fall back to the deterministic template when LLM is off.
                data.narrative?.sector_rotation ?? narrative?.sectorRotation
              }
            />
          )
        )}

        {/* Section 4 — History Rhymes (Phase 1e wired backend).
            US-only by design: the backend `macro_similarity_service`
            returns an empty payload with a "US-only in v1" caveat for
            CN, but rather than render the empty state inside the page,
            we hide the section entirely on CN — cleaner visual + less
            cognitive load. */}
        {market === "US" && <HistoryRhymes />}

        {/* Section 5 — Top Movers (2-row × N-col card grid) */}
        {loading ? (
          <TopMoversSkeleton rows={10} />
        ) : (
          <TopMovers items={moverItems} market={market} />
        )}

        {/* Section 6 — Stock Screener (US) · CN Stock Search (CN) */}
        {market === "US" ? (
          <Screener />
        ) : (
          <CnStockSearch market={market} />
        )}

        {/* Footer */}
        <footer className="border-t border-border/60 pt-4 text-[10px] text-muted-foreground space-y-2">
          <div>{t("footer_disclaimer")}</div>
          {/* Phase 1g — per-source freshness report. Replaces the
              previous one-line `Snapshot as of` since the new footer
              already carries that information plus a hover-to-expand
              per-source breakdown. */}
          <DataFreshnessFooter />
        </footer>
      </div>
    </div>
  );
}
