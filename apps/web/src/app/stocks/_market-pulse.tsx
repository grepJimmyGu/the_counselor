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

import { getMarketPulse } from "@/lib/api";
import type {
  AssetCard,
  IndexCard,
  MacroCard,
  MarketPulseResponse,
  SectorCard,
} from "@/lib/contracts";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { buildNarrative } from "@/lib/market-pulse-narrative";

import { MarketBrief } from "@/components/market-pulse/MarketBrief";
import { MacroPulseTable } from "@/components/market-pulse/MacroPulseTable";
import { SectorRotation } from "@/components/market-pulse/SectorRotation";
import { HistoryRhymes } from "@/components/market-pulse/HistoryRhymes";
import { TopMovers, type MoverItem } from "@/components/market-pulse/TopMovers";
import { Screener } from "@/components/market-pulse/Screener";
import { StickySubNav } from "@/components/market-pulse/StickySubNav";
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

  const load = useCallback(async (m: "US" | "CN", showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const r = await getMarketPulse(m, showRefreshing);
      setData(r);
    } catch {
      setError(
        "Market data unavailable — price history may still be loading.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load(market);
  }, [market, load]);

  // ── Live-quote overrides ─────────────────────────────────────────────────────
  // Collect every symbol the page displays, fetch via useLiveQuotes once,
  // and let withLive() override price + perf_1d when the cache has fresh
  // data. Pattern carried over from the original Market Pulse.
  const liveSymbols = useMemo(() => {
    if (!data) return [];
    return Array.from(
      new Set([
        ...data.indices.map((c) => c.symbol),
        ...data.macro.map((c) => c.symbol),
        ...data.top_assets.map((c) => c.symbol),
        ...data.featured_etfs.map((c) => c.symbol),
      ]),
    );
  }, [data]);
  const { quotes: liveQuotes } = useLiveQuotes(liveSymbols);

  function withLive<
    T extends { symbol: string; price: number | null; perf_1d: number | null },
  >(c: T): T {
    const lq = liveQuotes[c.symbol.toUpperCase()];
    if (!lq) return c;
    return { ...c, price: lq.price, perf_1d: lq.change_percent / 100 };
  }

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
        card: withLive(a),
        category: "Stock",
        href: `/stocks/${a.symbol}`,
      });
    }
    for (const a of data.featured_etfs) {
      if (seen.has(a.symbol)) continue;
      seen.add(a.symbol);
      out.push({
        card: withLive(a),
        category: "ETF",
        href: `/stocks/${a.symbol}`,
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, liveQuotes]);

  // ── Narrative (Phase 1a — deterministic Layer A; LLM ships in Phase 1b) ─────
  const narrative = useMemo(
    () => (data ? buildNarrative(applyLiveToData(data, withLive)) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, liveQuotes],
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
              US
            </Badge>
            <Badge
              variant={market === "CN" ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setMarket("CN")}
            >
              CN
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
          data && <MarketBrief data={applyLiveToData(data, withLive)} />
        )}

        {/* Section 2 — Macro Pulse table (4 signals: Growth / Inflation /
            Rates / Stress with 1M / 1Y / 3Y trend toggle + takeaways).
            Phase 1c: real CPI + 10Y Treasury yield via Alpha Vantage;
            Growth (ISM PMI) and Stress (HY OAS) remain mock pending
            a FRED API key. Per-row pill flips between Live + Mock. */}
        <MacroPulseTable signals={data?.macro_signals} />

        {/* Section 3 — Sector rotation (heatmap default, table on toggle).
            Sector tile click → inline ETF-vs-SPY comparison chart. */}
        {loading ? (
          <SectorHeatmapSkeleton />
        ) : (
          data && (
            <SectorRotation
              sectors={data.sectors as SectorCard[]}
              rotationHeadline={
                // Phase 1b: prefer LLM-generated rotation interpretation;
                // fall back to the deterministic template when LLM is off.
                data.narrative?.sector_rotation ?? narrative?.sectorRotation
              }
            />
          )
        )}

        {/* Section 4 — History Rhymes (Phase 1a stub with mock data;
            real macro_similarity_service backend ships in Phase 1e) */}
        <HistoryRhymes />

        {/* Section 5 — Top Movers (2-row × N-col card grid) */}
        {loading ? (
          <TopMoversSkeleton rows={10} />
        ) : (
          <TopMovers items={moverItems} />
        )}

        {/* Section 6 — Stock Screener (9 algorithm cards w/ tier badges;
            preset filter logic wires in Phase 1f) */}
        <Screener />

        {/* Footer */}
        <footer className="border-t border-border/60 pt-4 text-[10px] text-muted-foreground">
          <div>
            Data via Alpha Vantage price history · CMF computed from OHLCV ·
            Live prices via FMP (30s cache) · Not financial advice.
          </div>
          {data?.as_of && (
            <div className="mt-1">
              Snapshot as of {new Date(data.as_of).toLocaleString()}.
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Apply withLive() across every card-shaped field in the response so the
 * narrative + sector rotation read off live prices, not just card surfaces.
 * Sector + market_cap + sparkline-only fields stay as-is.
 */
function applyLiveToData(
  data: MarketPulseResponse,
  withLive: <
    T extends { symbol: string; price: number | null; perf_1d: number | null },
  >(
    c: T,
  ) => T,
): MarketPulseResponse {
  return {
    ...data,
    indices: data.indices.map(withLive) as IndexCard[],
    macro: data.macro.map(withLive) as MacroCard[],
    sectors: data.sectors as SectorCard[],
    top_assets: data.top_assets.map(withLive) as AssetCard[],
    featured_etfs: data.featured_etfs.map(withLive) as AssetCard[],
  };
}
