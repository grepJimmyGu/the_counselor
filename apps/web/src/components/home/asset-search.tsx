"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Search, X, TrendingUp, TrendingDown, ArrowRight, BarChart2, Newspaper } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { getDailyPrices, searchSymbolsApi } from "@/lib/api";
import type { PriceBarResponse, SymbolSearchItem } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

// ── Recommended strategies per asset type ────────────────────────────────────

const COMMODITY_TICKERS = new Set(["GLD", "SLV", "USO", "UNG", "DBA", "DBC", "PDBC", "CPER"]);

function getRecommendedStrategies(symbol: string) {
  const isCommodity = COMMODITY_TICKERS.has(symbol);
  if (isCommodity) {
    return [
      {
        name: "Trend Following",
        prompt: `Buy ${symbol} when price is above its 200-day moving average, hold until it falls below`,
        desc: "Classic commodity trend — ride the trend, exit on regime change",
      },
      {
        name: "Breakout Entry",
        prompt: `Buy ${symbol} when it breaks above the 20-day high, exit on 10-day low or 8% stop`,
        desc: "Breakout momentum strategy — capture extended commodity moves",
      },
      {
        name: "RSI Reversal",
        prompt: `Buy ${symbol} when RSI drops below 30, sell when RSI rises above 65`,
        desc: "Oversold bounce — buy dips in commodity during corrections",
      },
    ];
  }
  return [
    {
      name: "Golden Cross",
      prompt: `Buy ${symbol} when the 50-day MA crosses above the 200-day MA, sell on death cross`,
      desc: "Classic trend signal — catch major uptrends, avoid bear markets",
    },
    {
      name: "RSI Mean Reversion",
      prompt: `Buy ${symbol} when RSI drops below 30, sell when RSI rises above 60`,
      desc: "Counter-trend momentum — buy oversold dips, sell into strength",
    },
    {
      name: "200-Day Filter",
      prompt: `Hold ${symbol} only when the price is above its 200-day moving average`,
      desc: "Simple regime filter — stay in bull market, avoid major drawdowns",
    },
  ];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatPrice(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Component ─────────────────────────────────────────────────────────────────

interface AssetSearchProps {
  preloadSymbol?: string | null;
  sectionRef?: React.RefObject<HTMLElement | null>;
}

export function AssetSearch({ preloadSymbol, sectionRef }: AssetSearchProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<SymbolSearchItem | null>(null);
  const [priceData, setPriceData] = useState<PriceBarResponse[]>([]);
  const [loadingChart, setLoadingChart] = useState(false);
  const [showStrategies, setShowStrategies] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Pre-load symbol when market snapshot card is clicked
  useEffect(() => {
    if (!preloadSymbol) return;
    const syntheticItem: SymbolSearchItem = { symbol: preloadSymbol, name: preloadSymbol };
    selectSymbol(syntheticItem);
    sectionRef?.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preloadSymbol]);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await searchSymbolsApi(query.trim());
        setResults(res.slice(0, 6));
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query]);

  async function selectSymbol(item: SymbolSearchItem) {
    setSelected(item);
    setResults([]);
    setQuery("");
    setShowStrategies(false);
    setLoadingChart(true);
    try {
      const bars = await getDailyPrices(item.symbol);
      setPriceData(bars.slice(-90));
    } catch { setPriceData([]); }
    finally { setLoadingChart(false); }
  }

  const last = priceData[priceData.length - 1];
  const prev = priceData[priceData.length - 2];
  const changePct = last && prev ? ((last.adjusted_close - prev.adjusted_close) / prev.adjusted_close) : null;
  const isPositive = changePct != null && changePct >= 0;
  const recommendedStrategies = selected ? getRecommendedStrategies(selected.symbol) : [];

  return (
    <section ref={sectionRef} className="space-y-4">
      <div>
        <h2 className="font-heading text-xl font-semibold">Asset Explorer</h2>
        <p className="text-sm text-muted-foreground">Search any stock, ETF, or commodity to view price history and build strategies</p>
      </div>

      {/* Search input */}
      <div className="relative">
        <div className="flex items-center gap-3 rounded-xl border border-border bg-white px-4 py-3 shadow-sm focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-all duration-200">
          <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker or company name… e.g. GLD, Apple, crude oil"
            inputMode="search"
            autoCorrect="off"
            spellCheck={false}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {searching && <span className="text-xs text-muted-foreground">Searching…</span>}
          {query && !searching && (
            <button type="button" onClick={() => setQuery("")} className="cursor-pointer text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Dropdown */}
        {results.length > 0 && (
          <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-border bg-white shadow-lg">
            {results.map((item) => (
              <button
                key={item.symbol}
                type="button"
                onClick={() => selectSymbol(item)}
                className="flex w-full cursor-pointer items-center gap-3 px-4 py-2.5 text-left transition-colors duration-150 hover:bg-muted/50"
              >
                <span className="w-14 font-mono text-sm font-bold text-foreground">{item.symbol}</span>
                <span className="flex-1 truncate text-sm text-muted-foreground">{item.name}</span>
                {item.region && <span className="text-xs text-muted-foreground">{item.region}</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected asset panel */}
      {selected && (
        <div className="rounded-xl border border-border bg-white shadow-sm overflow-hidden">
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border px-5 py-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-bold">{selected.symbol}</span>
                {changePct != null && (
                  <span className={cn("flex items-center gap-1 text-sm font-semibold", isPositive ? "text-[var(--profit)]" : "text-[var(--loss)]")}>
                    {isPositive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                    {isPositive ? "+" : ""}{(changePct * 100).toFixed(2)}%
                  </span>
                )}
              </div>
              <div className="text-sm text-muted-foreground">{selected.name !== selected.symbol ? selected.name : ""}</div>
              {last && <div className="mt-1 font-mono text-2xl font-semibold">${formatPrice(last.adjusted_close)}</div>}
              {/* Deep-dive links */}
              <div className="mt-2 flex flex-wrap gap-2">
                <Link
                  href={`/stocks/${selected.symbol}` as Route}
                  className="flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:text-primary"
                >
                  <BarChart2 className="h-3 w-3" />
                  Financial Analysis
                </Link>
                <Link
                  href={`/stocks/${selected.symbol}?tab=sentiment` as Route}
                  className="flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:text-primary"
                >
                  <Newspaper className="h-3 w-3" />
                  News & Sentiment
                </Link>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Chart */}
          <div className="p-4">
            {loadingChart ? (
              <div className="h-48 animate-pulse rounded-lg bg-muted/40" />
            ) : priceData.length > 0 ? (
              <>
                <div className="mb-2 text-xs text-muted-foreground">90-day price history (adjusted close)</div>
                <div className="h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={priceData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke="var(--color-border)" vertical={false} strokeDasharray="3 3" />
                      <XAxis dataKey="trading_date" tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }} minTickGap={30} />
                      <YAxis tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }} width={72} domain={["auto", "auto"]} />
                      <Tooltip
                        contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: "8px", fontSize: 12 }}
                        formatter={(v) => [`$${formatPrice(Number(v))}`, "Price"]}
                      />
                      <Line type="monotone" dataKey="adjusted_close" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                {/* Key stats */}
                <div className="mt-3 grid grid-cols-4 gap-2">
                  {[
                    { label: "90D High", value: `$${formatPrice(Math.max(...priceData.map(b => b.high)))}` },
                    { label: "90D Low", value: `$${formatPrice(Math.min(...priceData.map(b => b.low)))}` },
                    { label: "Avg Vol (20d)", value: (priceData.slice(-20).reduce((s, b) => s + b.volume, 0) / 20 / 1e6).toFixed(1) + "M" },
                    { label: "Data Points", value: `${priceData.length}d` },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded-lg border border-border bg-muted/30 px-2 py-2 text-center">
                      <div className="text-[10px] text-muted-foreground">{label}</div>
                      <div className="font-mono text-xs font-semibold mt-0.5">{value}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="py-6 text-center text-sm text-muted-foreground">No price data available for {selected.symbol}.</p>
            )}
          </div>

          {/* Build Strategy section */}
          <div className="border-t border-border bg-muted/20 px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold">Build a Strategy on {selected.symbol}</div>
                <div className="text-xs text-muted-foreground mt-0.5">Select a strategy below to run a full backtest instantly</div>
              </div>
              <button
                type="button"
                onClick={() => setShowStrategies((v) => !v)}
                className="cursor-pointer rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10"
              >
                {showStrategies ? "Hide strategies" : "Show strategies"}
              </button>
            </div>

            {showStrategies && (
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {recommendedStrategies.map((strat) => (
                  <div
                    key={strat.name}
                    className="flex flex-col justify-between rounded-xl border border-border bg-white p-4 shadow-sm"
                  >
                    <div>
                      <div className="font-heading text-sm font-semibold">{strat.name}</div>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{strat.desc}</p>
                      <p className="mt-2 rounded-md bg-muted/50 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-foreground/70">
                        {strat.prompt}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        router.push(`/workspace?prompt=${encodeURIComponent(strat.prompt)}&autorun=true`)
                      }
                      className="mt-3 flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white transition-colors duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      Run Backtest <ArrowRight className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
