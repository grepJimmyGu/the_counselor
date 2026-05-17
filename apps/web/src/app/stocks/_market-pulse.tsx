"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import {
  TrendingUp, TrendingDown, Minus, Search, ArrowRight, RefreshCw, AlertTriangle,
} from "lucide-react";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getMarketPulse, searchSymbols } from "@/lib/api";
import type {
  MarketPulseResponse, IndexCard, MacroCard, SectorCard, AssetCard,
} from "@/lib/contracts";

// ── Design tokens (from ui-ux-pro-max Data-Dense Dashboard) ──────────────────
// Primary: #1E40AF  Secondary: #3B82F6  Accent: #F59E0B
// CMF bar: emerald (positive) ↔ red (negative), divergent from centre

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  const s = (v * 100).toFixed(digits);
  return v >= 0 ? `+${s}%` : `${s}%`;
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function fmtMktCap(v: number | null | undefined): string {
  if (v == null) return "";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  return `$${(v / 1e6).toFixed(0)}M`;
}

function PerfBadge({ v, className }: { v: number | null | undefined; className?: string }) {
  if (v == null) return <span className={cn("font-mono text-xs text-muted-foreground", className)}>—</span>;
  return (
    <span className={cn(
      "inline-flex items-center gap-0.5 font-mono text-xs font-semibold",
      v > 0 ? "text-emerald-600" : v < 0 ? "text-red-500" : "text-muted-foreground",
      className
    )}>
      {v > 0.001 ? <TrendingUp className="h-2.5 w-2.5" /> : v < -0.001 ? <TrendingDown className="h-2.5 w-2.5" /> : <Minus className="h-2.5 w-2.5" />}
      {fmtPct(v)}
    </span>
  );
}

// ── CMF Bar ───────────────────────────────────────────────────────────────────

function CMFBar({ value }: { value: number | null | undefined }) {
  if (value == null) {
    return <div className="text-[10px] text-muted-foreground font-mono">—</div>;
  }
  // Clamp to [-0.5, 0.5] for visual range (typical CMF values)
  const clamped = Math.max(-0.5, Math.min(0.5, value));
  const isPositive = value >= 0;
  // Bar fills from centre (50%) outward
  const barPct = Math.abs(clamped) / 0.5 * 50; // 0–50% of half-width

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span className={cn(
          "font-mono text-[11px] font-semibold tabular-nums",
          isPositive ? "text-emerald-600" : "text-red-500"
        )}>
          {value >= 0 ? "+" : ""}{value.toFixed(3)}
        </span>
        <span className="text-[9px] text-muted-foreground">CMF</span>
      </div>
      {/* Track: −0.5 ←──── 0 ────→ +0.5 */}
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted">
        {/* Negative half (left) */}
        <div className="absolute left-0 top-0 h-full w-1/2 overflow-hidden">
          {!isPositive && (
            <div
              className="absolute right-0 top-0 h-full bg-red-500 transition-all duration-500"
              style={{ width: `${barPct * 2}%` }}
            />
          )}
        </div>
        {/* Positive half (right) */}
        <div className="absolute right-0 top-0 h-full w-1/2 overflow-hidden">
          {isPositive && (
            <div
              className="absolute left-0 top-0 h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${barPct * 2}%` }}
            />
          )}
        </div>
        {/* Centre marker */}
        <div className="absolute left-1/2 top-0 h-full w-px bg-border/60" />
      </div>
    </div>
  );
}

// ── Index Card ────────────────────────────────────────────────────────────────

function StaleBadge() {
  return (
    <span className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-semibold bg-amber-100 text-amber-700 border border-amber-200">
      <AlertTriangle className="h-2.5 w-2.5" />
      Stale
    </span>
  );
}

function IndexCardUI({ card }: { card: IndexCard }) {
  const chartData = card.sparkline_5d.map((v, i) => ({ i, v }));
  const isUp = card.perf_5d != null ? card.perf_5d >= 0 : (card.perf_1d ?? 0) >= 0;
  return (
    <Link href={`/stocks/${card.symbol}` as Route} className="block cursor-pointer touch-manipulation">
      <div className={cn(
        "rounded-xl border bg-white p-3.5 shadow-sm transition-all hover:border-primary/30 hover:shadow-md",
        card.is_stale ? "border-amber-200" : "border-border"
      )}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-mono text-xs font-bold text-muted-foreground">{card.symbol}</div>
            <div className="mt-0.5 text-xs text-foreground/70 leading-tight">{card.name}</div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <PerfBadge v={card.perf_1d} />
            {card.is_stale && <StaleBadge />}
          </div>
        </div>
        <div className="mt-2 flex items-end justify-between gap-1">
          <span className="font-mono text-base sm:text-lg font-bold truncate">{fmtPrice(card.price)}</span>
          {chartData.length >= 2 && (
            <div className="shrink-0">
              <ResponsiveContainer width={80} height={40}>
                <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
                  <defs>
                    <linearGradient id={`spark-${card.symbol}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isUp ? "#10b981" : "#ef4444"} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={isUp ? "#10b981" : "#ef4444"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area
                    type="monotone" dataKey="v" dot={false}
                    stroke={isUp ? "#10b981" : "#ef4444"}
                    strokeWidth={1.5}
                    fill={`url(#spark-${card.symbol})`}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        <div className="mt-1 flex items-center justify-between gap-2">
          {card.perf_5d != null ? (
            <span className="text-[10px] text-muted-foreground">
              5D: <span className={card.perf_5d >= 0 ? "text-emerald-600" : "text-red-500"}>{fmtPct(card.perf_5d)}</span>
            </span>
          ) : <span />}
          {card.latest_date && (
            <span className={cn("text-[9px]", card.is_stale ? "text-amber-600" : "text-muted-foreground/60")}>
              {card.is_stale ? "⚠ " : ""}as of {fmtDate(card.latest_date)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

// ── Macro Chip ────────────────────────────────────────────────────────────────

function MacroChipUI({ card }: { card: MacroCard }) {
  const dir = card.perf_1d == null ? "flat" : card.perf_1d > 0.001 ? "up" : card.perf_1d < -0.001 ? "down" : "flat";
  return (
    <div className={cn(
      "flex items-center justify-between rounded-lg border px-3 py-2.5 min-h-[52px] transition-colors touch-manipulation",
      dir === "up" ? "border-emerald-200 bg-emerald-50/60" :
      dir === "down" ? "border-red-200 bg-red-50/60" :
      "border-border bg-muted/30"
    )}>
      <div className="min-w-0 flex-1">
        <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground truncate">{card.label}</div>
        <div className="font-mono text-sm font-bold">{fmtPrice(card.price)}</div>
      </div>
      <PerfBadge v={card.perf_1d} />
    </div>
  );
}

// ── Sector Flow Row ───────────────────────────────────────────────────────────

function SectorFlowRow({ card, rank }: { card: SectorCard; rank: number }) {
  return (
    <Link href={`/stocks/${card.symbol}` as Route} className="block cursor-pointer touch-manipulation">
      {/* Desktop: 5-column table row */}
      <div className="hidden sm:grid grid-cols-[2rem_1fr_5rem_4rem_7rem] items-center gap-3 rounded-lg px-3 py-2.5 min-h-[44px] transition-colors hover:bg-muted/40">
        <span className="text-[10px] font-mono text-muted-foreground text-right">{rank}</span>
        <div className="min-w-0">
          <div className="text-xs font-semibold truncate">{card.name}</div>
          <div className="font-mono text-[10px] text-muted-foreground">{card.symbol}</div>
        </div>
        <PerfBadge v={card.perf_1d} className="justify-end" />
        <div className="text-right">
          {card.rs_vs_spy_5d != null ? (
            <span className={cn("font-mono text-[10px] font-medium", card.rs_vs_spy_5d > 0 ? "text-emerald-600" : "text-red-500")}>
              {card.rs_vs_spy_5d >= 0 ? "+" : ""}{(card.rs_vs_spy_5d * 100).toFixed(1)}%
            </span>
          ) : <span className="text-[10px] text-muted-foreground">—</span>}
          <div className="text-[9px] text-muted-foreground">vs SPY</div>
        </div>
        <CMFBar value={card.cmf_20} />
      </div>

      {/* Mobile: 2-line card layout */}
      <div className="sm:hidden flex items-center gap-3 px-3 py-3 min-h-[56px] rounded-lg transition-colors hover:bg-muted/40">
        <span className="text-[10px] font-mono text-muted-foreground w-4 shrink-0 text-right">{rank}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold truncate">{card.name}</span>
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">{card.symbol}</span>
          </div>
          <div className="mt-1 w-full">
            <CMFBar value={card.cmf_20} />
          </div>
        </div>
        <div className="shrink-0 text-right">
          <PerfBadge v={card.perf_1d} />
          {card.rs_vs_spy_5d != null && (
            <div className={cn("font-mono text-[10px] mt-0.5", card.rs_vs_spy_5d > 0 ? "text-emerald-600" : "text-red-500")}>
              {card.rs_vs_spy_5d >= 0 ? "+" : ""}{(card.rs_vs_spy_5d * 100).toFixed(1)}%
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

// ── Asset Card (for tabs) ─────────────────────────────────────────────────────

function AssetCardUI({ card, href }: { card: AssetCard; href: string }) {
  return (
    <Link href={href as Route} className="block cursor-pointer touch-manipulation">
      <div className={cn(
        "rounded-lg border bg-white px-3.5 py-3 shadow-sm transition-all hover:border-primary/30 hover:shadow-md min-h-[64px]",
        card.is_stale ? "border-amber-200" : "border-border"
      )}>
        {/* Top row: symbol + price */}
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-mono text-xs font-bold">{card.symbol}</span>
              {card.sector && (
                <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 hidden sm:inline-flex">{card.sector}</Badge>
              )}
              {card.is_stale && <StaleBadge />}
            </div>
            <div className="text-[11px] text-muted-foreground truncate">{card.name}</div>
            {card.sector && (
              <div className="sm:hidden text-[9px] text-muted-foreground truncate mt-0.5">{card.sector}</div>
            )}
          </div>
          <div className="text-right shrink-0 space-y-0.5">
            <div className="font-mono text-sm font-semibold">{fmtPrice(card.price)}</div>
            <PerfBadge v={card.perf_1d} />
          </div>
        </div>
        {/* Bottom row: CMF bar + meta */}
        <div className="mt-2 flex items-center gap-3">
          <div className="flex-1">
            <CMFBar value={card.cmf_20} />
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {card.market_cap && (
              <span className="text-[10px] text-muted-foreground">{fmtMktCap(card.market_cap)}</span>
            )}
            {card.latest_date && (
              <span className={cn("text-[9px]", card.is_stale ? "text-amber-600" : "text-muted-foreground/60")}>
                {fmtDate(card.latest_date)}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}

// ── Mini Screener ─────────────────────────────────────────────────────────────

function MiniScreener() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ symbol: string; name: string; region?: string | null }>>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query.length < 1) { setResults([]); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await searchSymbols(query);
        setResults(r.slice(0, 8));
      } catch { setResults([]); }
      finally { setLoading(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search any symbol or company..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="h-9 pl-8 text-sm"
        />
      </div>
      {(results.length > 0 || loading) && (
        <div className="absolute top-10 left-0 right-0 z-20 rounded-lg border border-border bg-white shadow-lg">
          {loading && (
            <div className="px-3 py-2">
              <Skeleton className="h-4 w-full" />
            </div>
          )}
          {results.map(r => (
            <button
              key={r.symbol}
              onClick={() => { router.push(`/stocks/${r.symbol}` as Route); setQuery(""); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50 transition-colors border-b border-border/30 last:border-0 cursor-pointer"
            >
              <span className="font-mono text-xs font-bold w-12 shrink-0">{r.symbol}</span>
              <span className="text-muted-foreground truncate">{r.name}</span>
              {r.region && <span className="ml-auto text-[10px] text-muted-foreground shrink-0">{r.region}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Loading skeletons ─────────────────────────────────────────────────────────

function IndexCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-white p-3.5 shadow-sm space-y-2 animate-pulse">
      <div className="flex justify-between">
        <div className="space-y-1"><Skeleton className="h-3 w-8" /><Skeleton className="h-3 w-20" /></div>
        <Skeleton className="h-4 w-12" />
      </div>
      <Skeleton className="h-6 w-24" />
    </div>
  );
}

function SectorRowSkeleton() {
  return (
    <div className="grid grid-cols-[2rem_1fr_5rem_4rem_7rem] items-center gap-3 px-3 py-2.5 animate-pulse">
      <Skeleton className="h-3 w-4 ml-auto" />
      <div className="space-y-1"><Skeleton className="h-3 w-24" /><Skeleton className="h-2.5 w-10" /></div>
      <Skeleton className="h-3 w-12 ml-auto" />
      <Skeleton className="h-3 w-10 ml-auto" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function MarketPulsePage() {
  const [market, setMarket] = useState<"US" | "CN">("US");
  const [data, setData] = useState<MarketPulseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (m: "US" | "CN", showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const r = await getMarketPulse(m);
      setData(r);
    } catch (e) {
      setError("Market data unavailable — price history may still be loading.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(market); }, [market, load]);

  const handleMarketToggle = (m: "US" | "CN") => {
    setMarket(m);
    setData(null);
  };

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1280px] space-y-6 px-4 py-6 md:px-6 lg:px-8">

        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-heading text-xl font-bold text-foreground">Market Pulse</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Capital flow · Sector rotation · Index performance
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Market toggle */}
            <div className="flex gap-1 rounded-lg border border-border bg-muted/30 p-1">
              {(["US", "CN"] as const).map(m => (
                <button
                  key={m}
                  onClick={() => handleMarketToggle(m)}
                  className={cn(
                    "rounded-md px-4 py-1.5 text-xs font-semibold transition-all cursor-pointer",
                    market === m ? "bg-white shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {m === "US" ? "🇺🇸 US" : "🇨🇳 CN"}
                </button>
              ))}
            </div>
            {/* Refresh */}
            <button
              onClick={() => load(market, true)}
              className={cn("flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-white text-muted-foreground transition-colors hover:text-foreground cursor-pointer", refreshing && "animate-spin")}
              title="Refresh"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {error} Market ETF price bars load on first deploy — check back shortly.
          </div>
        )}

        {/* A. Indices */}
        <section>
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            {market === "CN" ? "China Indices" : "Major Indices"}
          </div>
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
            {loading
              ? Array(4).fill(0).map((_, i) => <IndexCardSkeleton key={i} />)
              : (data?.indices ?? []).map(c => <IndexCardUI key={c.symbol} card={c} />)
            }
          </div>
        </section>

        {/* B+C. Sector Flow (left) + Macro Signals (right) — side-by-side on desktop */}
        <div className="grid gap-6 lg:grid-cols-[3fr_2fr] lg:items-start">

          {/* C. Sector Capital Flow */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                Sector Capital Flow
                <span className="ml-2 normal-case font-normal text-muted-foreground/60">
                  · Chaikin Money Flow (20d) — positive = accumulation, negative = distribution
                </span>
              </div>
              {data && (
                <div className="text-[10px] text-muted-foreground">
                  Sorted by CMF ↓
                </div>
              )}
            </div>
            <div className="rounded-xl border border-border bg-white shadow-sm overflow-hidden">
              {/* Table header — desktop only */}
              <div className="hidden sm:grid grid-cols-[2rem_1fr_5rem_4rem_7rem] items-center gap-3 border-b border-border/50 px-3 py-2 bg-muted/20">
                <span className="text-[9px] font-semibold uppercase text-muted-foreground text-right">#</span>
                <span className="text-[9px] font-semibold uppercase text-muted-foreground">Sector</span>
                <span className="text-[9px] font-semibold uppercase text-muted-foreground text-right">1D</span>
                <span className="text-[9px] font-semibold uppercase text-muted-foreground text-right">vs SPY 5D</span>
                <span className="text-[9px] font-semibold uppercase text-muted-foreground">CMF (−0.5 → +0.5)</span>
              </div>
              {loading
                ? Array(11).fill(0).map((_, i) => <SectorRowSkeleton key={i} />)
                : (data?.sectors ?? []).map((s, i) => (
                    <div key={s.symbol} className={cn(i < (data?.sectors.length ?? 0) - 1 && "border-b border-border/30")}>
                      <SectorFlowRow card={s} rank={i + 1} />
                    </div>
                  ))
              }
            </div>
          </section>

          {/* B. Macro signals */}
          <section>
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Macro Signals
            </div>
            <div className="grid gap-2 grid-cols-2">
              {loading
                ? Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)
                : (data?.macro ?? []).map(m => <MacroChipUI key={m.symbol} card={m} />)
              }
            </div>
          </section>

        </div>

        {/* D. Asset Tabs */}
        <section>
          <Tabs defaultValue="stocks">
            <div className="flex items-center justify-between mb-3">
              <TabsList className="h-8">
                <TabsTrigger value="stocks" className="text-xs h-7 px-3">Stocks</TabsTrigger>
                <TabsTrigger value="etfs" className="text-xs h-7 px-3">ETFs</TabsTrigger>
                <TabsTrigger value="commodities" className="text-xs h-7 px-3">Commodities</TabsTrigger>
              </TabsList>
              <Link
                href={"/stocks/screener" as Route}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
              >
                Full Screener <ArrowRight className="h-3 w-3" />
              </Link>
            </div>

            {/* Search */}
            <div className="mb-4">
              <MiniScreener />
            </div>

            <TabsContent value="stocks" className="mt-0 space-y-2">
              <div className="text-[10px] text-muted-foreground mb-2">
                {market === "CN"
                  ? "CN market ETF proxies by capital inflow (CMF-20) · Individual A-share data not available"
                  : "Top 10 US stocks by capital inflow (CMF-20) · Updated hourly"}
              </div>
              {loading
                ? Array(5).fill(0).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)
                : (data?.top_assets ?? []).length > 0
                ? (data!.top_assets).map(a => (
                    <AssetCardUI key={a.symbol} card={a} href={`/stocks/${a.symbol}`} />
                  ))
                : (
                  <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
                    {market === "CN"
                      ? "CN ETF price data loading… check back shortly."
                      : "Price history loading for universe… check back in a few minutes."}
                  </div>
                )
              }
            </TabsContent>

            <TabsContent value="etfs" className="mt-0 space-y-2">
              <div className="text-[10px] text-muted-foreground mb-2">
                {market === "CN"
                  ? "CN market ETFs — major index and sector proxies"
                  : "Featured ETFs — major indices, sectors, and macro proxies"}
              </div>
              {loading
                ? Array(5).fill(0).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)
                : (data?.featured_etfs ?? []).map(a => (
                    <AssetCardUI key={a.symbol} card={a} href={`/stocks/${a.symbol}`} />
                  ))
              }
            </TabsContent>

            <TabsContent value="commodities" className="mt-0 space-y-2">
              <div className="text-[10px] text-muted-foreground mb-2">
                Commodity evaluation — physical market + ETF price trend
              </div>
              {[
                { symbol: "GOLD", name: "Gold", unit: "oz", etf: "GLD" },
                { symbol: "WTI",  name: "WTI Crude Oil", unit: "bbl", etf: "USO" },
                { symbol: "COPPER", name: "Copper", unit: "lb", etf: "COPX" },
                { symbol: "WHEAT", name: "Wheat", unit: "bu", etf: "WEAT" },
              ].map(c => (
                <Link key={c.symbol} href={`/commodities/${c.symbol}` as Route} className="block cursor-pointer">
                  <div className="flex items-center justify-between rounded-lg border border-border bg-white px-3.5 py-2.5 shadow-sm transition-all hover:border-primary/30 hover:shadow-md">
                    <div>
                      <div className="text-xs font-bold">{c.name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        ETF proxy: {c.etf} · per {c.unit}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      View analysis <ArrowRight className="h-3 w-3" />
                    </div>
                  </div>
                </Link>
              ))}
            </TabsContent>
          </Tabs>
        </section>

        {/* Footer note */}
        <div className="text-[10px] text-muted-foreground/60 text-center pb-2 space-y-0.5">
          <div>
            Data from Alpha Vantage price history · CMF computed from OHLCV · Not financial advice
          </div>
          {data?.as_of && (
            <div>
              Cache computed: {new Date(data.as_of).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} UTC · Refreshes hourly
            </div>
          )}
        </div>

      </div>
    </main>
  );
}
