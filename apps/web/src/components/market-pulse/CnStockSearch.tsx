"use client";

/**
 * <CnStockSearch> — CN market stock search + technical indicator viewer.
 *
 * Replaces the hidden Screener section when market === "CN". Two layers:
 *   1. Search bar → terse result cards (ticker, name, exchange)
 *   2. Once a ticker is selected: indicator pills + time range → line chart
 *
 * Alpha Vantage provides the data via /api/cn/stocks/search and
 * /api/cn/indicators. Recharts renders the chart (already in our
 * dependency tree via SectorComparisonChart).
 */

import * as React from "react";
import { Search, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { searchCnStocks, getCnIndicator, type CnSearchResult, type CnIndicatorPoint } from "@/lib/api";
import { useMarketCopy } from "@/lib/market-copy";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

type IndicatorFunc = "SMA" | "RSI" | "MACD" | "BBANDS";
type TimeRange = "1M" | "3M" | "6M" | "1Y" | "ALL";

const INDICATORS: { id: IndicatorFunc; label: string; defaultPeriod: number }[] = [
  { id: "SMA", label: "SMA", defaultPeriod: 20 },
  { id: "RSI", label: "RSI", defaultPeriod: 14 },
  { id: "MACD", label: "MACD", defaultPeriod: 12 },
  { id: "BBANDS", label: "Bollinger", defaultPeriod: 20 },
];

const RANGES: { id: TimeRange; label: string }[] = [
  { id: "1M", label: "1月" },
  { id: "3M", label: "3月" },
  { id: "6M", label: "6月" },
  { id: "1Y", label: "1年" },
  { id: "ALL", label: "全部" },
];

export function CnStockSearch({ market }: { market: "US" | "CN" }) {
  const heading = useMarketCopy("cn_search_heading", market);
  const placeholder = useMarketCopy("cn_search_placeholder", market);

  // ── State ──────────────────────────────────────────────────────────────
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<CnSearchResult[]>([]);
  const [searching, setSearching] = React.useState(false);

  const [selected, setSelected] = React.useState<CnSearchResult | null>(null);
  const [indicator, setIndicator] = React.useState<IndicatorFunc>("RSI");
  const [timePeriod, setTimePeriod] = React.useState(14);
  const [range, setRange] = React.useState<TimeRange>("6M");

  const [points, setPoints] = React.useState<CnIndicatorPoint[]>([]);
  const [latestValue, setLatestValue] = React.useState<number | null>(null);
  const [high, setHigh] = React.useState<number | null>(null);
  const [low, setLow] = React.useState<number | null>(null);
  const [signal, setSignal] = React.useState<string | null>(null);
  const [loadingChart, setLoadingChart] = React.useState(false);
  const [chartError, setChartError] = React.useState<string | null>(null);

  // ── Search ─────────────────────────────────────────────────────────────
  const doSearch = React.useCallback(async (q: string) => {
    if (q.trim().length < 1) return;
    setSearching(true);
    try {
      const r = await searchCnStocks(q.trim());
      setResults(r);
    } catch {
      // leave previous results in place on transient failures
    } finally {
      setSearching(false);
    }
  }, []);

  React.useEffect(() => {
    const t = window.setTimeout(() => doSearch(query), 250);
    return () => window.clearTimeout(t);
  }, [query, doSearch]);

  // ── Indicator fetch ────────────────────────────────────────────────────
  React.useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoadingChart(true);
    setChartError(null);
    const period = indicator === "MACD" ? 12 : timePeriod;
    getCnIndicator(selected.symbol, indicator, period, range)
      .then((r) => {
        if (cancelled) return;
        setPoints(r.points);
        setLatestValue(r.latest_value);
        setHigh(r.high);
        setLow(r.low);
        setSignal(r.signal);
      })
      .catch((e) => {
        if (cancelled) setChartError(e.message ?? "Failed to load indicator");
      })
      .finally(() => {
        if (!cancelled) setLoadingChart(false);
      });
    return () => { cancelled = true; };
  }, [selected, indicator, timePeriod, range]);

  // ── Chart data ─────────────────────────────────────────────────────────
  const chartData = React.useMemo(() =>
    points.map((p) => ({ date: p.date.slice(5), value: p.value })),
    [points],
  );

  const isMACD = indicator === "MACD" || indicator === "BBANDS";
  const yDomain = isMACD ? undefined : indicator === "RSI" ? [0, 100] : undefined;

  return (
    <section data-testid="cn-stock-search" className="space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {heading}
      </h2>

      {/* ── Search bar ─────────────────────────────────────────────────── */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-xl border border-border bg-white py-2.5 pl-10 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {searching && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground">
            搜索中…
          </span>
        )}
      </div>

      {/* ── Results ────────────────────────────────────────────────────── */}
      {results.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((r) => {
            const isSel = selected?.symbol === r.symbol;
            return (
              <button
                key={r.symbol}
                type="button"
                onClick={() => setSelected(r)}
                className={cn(
                  "rounded-xl border p-3 text-left transition-all",
                  isSel
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border hover:border-primary/40 hover:bg-muted/30",
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{r.name_cn}</span>
                  <span className="text-[10px] text-muted-foreground">{r.exchange}</span>
                </div>
                <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {r.symbol}
                </p>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Selected: indicator panel ───────────────────────────────────── */}
      {selected && (
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-semibold">{selected.name_cn}</span>
              <span className="ml-2 font-mono text-xs text-muted-foreground">
                {selected.symbol} · {selected.exchange}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              ✕ 清除
            </button>
          </div>

          {/* Indicator pills */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex flex-wrap gap-1.5">
              {INDICATORS.map((ind) => (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() => { setIndicator(ind.id); setTimePeriod(ind.defaultPeriod); }}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    indicator === ind.id
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border hover:border-primary/40",
                  )}
                >
                  {ind.label}
                </button>
              ))}
            </div>

            {/* Time period (not shown for MACD) */}
            {indicator !== "MACD" && (
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-muted-foreground">周期</span>
                {[5, 10, 14, 20, 50, 200].map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setTimePeriod(p)}
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-mono transition-colors",
                      timePeriod === p
                        ? "bg-primary/20 text-primary font-semibold"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Time range */}
          <div className="flex gap-1.5">
            {RANGES.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setRange(r.id)}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors",
                  range === r.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-primary/30",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Chart */}
          <div className="rounded-lg border border-border bg-white p-3">
            {loadingChart ? (
              <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">
                加载中…
              </div>
            ) : chartError ? (
              <div className="flex h-48 items-center justify-center text-xs text-red-500">
                {chartError}
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                    <YAxis domain={yDomain} tick={{ fontSize: 10 }} width={40} />
                    <Tooltip
                      contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
                    />
                    {indicator === "RSI" && (
                      <>
                        <ReferenceLine y={70} stroke="#f59e0b" strokeDasharray="4 4" />
                        <ReferenceLine y={30} stroke="#f59e0b" strokeDasharray="4 4" />
                      </>
                    )}
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#3b82f6"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>

                {/* Stats bar */}
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/40 pt-2 text-[11px] text-muted-foreground">
                  <span>
                    {indicator === "RSI" ? "最新 RSI" : indicator === "SMA" ? `SMA ${timePeriod}` : indicator === "MACD" ? "最新 MACD" : "布林中轨"}:
                    {" "}
                    <span className="font-mono font-semibold text-foreground">
                      {latestValue != null ? latestValue.toFixed(4) : "—"}
                    </span>
                  </span>
                  {high != null && (
                    <span>
                      最高: <span className="font-mono">{high.toFixed(4)}</span>
                    </span>
                  )}
                  {low != null && (
                    <span>
                      最低: <span className="font-mono">{low.toFixed(4)}</span>
                    </span>
                  )}
                  {signal && (
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-medium",
                        signal.includes("bullish") || signal.includes("超卖")
                          ? "bg-emerald-50 text-emerald-700"
                          : signal.includes("bearish") || signal.includes("超买")
                            ? "bg-red-50 text-red-700"
                            : "bg-muted/30 text-muted-foreground",
                      )}
                    >
                      {signal}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
