"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Loader2, X } from "lucide-react";
import {
  AreaChart,
  Area,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cn } from "@/lib/utils";
import type {
  SectorCard,
  SectorComparisonResponse,
} from "@/lib/contracts";
import { fmtPct } from "@/lib/market-pulse-format";
import { getSectorComparison } from "@/lib/api";

/**
 * Inline expansion under the sector heatmap. Renders a sector-ETF
 * vs S&P 500 cumulative return chart + returns table, modeled on the
 * Seeking Alpha "Sector vs S&P 500" comparison view Jimmy referenced
 * on 2026-05-21.
 *
 * **Phase 1d (2026-05-22):** chart data now fetched live from
 * `GET /api/market/sector-comparison/{symbol}?range=...`. Backend
 * computes normalized cumulative returns from `price_bars`, with a 5
 * min server-side cache so sector tile re-clicks are cheap. Returns
 * table reads the pre-computed Day / YTD / 1Y / 3Y totals from the
 * same response (no client-side derivation).
 *
 * **Time ranges:** 1M / 6M / YTD / 1Y / 3Y. 5Y / 10Y / MAX would
 * require extending backend `price_bars` retention past the current
 * 3-yr warmup window — deferred.
 */

type Range = "1M" | "6M" | "YTD" | "1Y" | "3Y";

const RANGES: { id: Range; label: string }[] = [
  { id: "1M", label: "1M" },
  { id: "6M", label: "6M" },
  { id: "YTD", label: "YTD" },
  { id: "1Y", label: "1Y" },
  { id: "3Y", label: "3Y" },
];

export function SectorComparisonChart({
  sector,
  onClose,
}: {
  sector: SectorCard;
  onClose: () => void;
}) {
  const [range, setRange] = useState<Range>("1Y");
  const [data, setData] = useState<SectorComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSectorComparison(sector.symbol, range)
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e: Error) => {
        if (!cancelled)
          setError(e.message || "Comparison data unavailable.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sector.symbol, range]);

  // Series for the chart. Map ISO date → display label (M/D).
  const series = (data?.series ?? []).map((p) => ({
    label: formatDateLabel(p.date),
    sector: p.sector,
    spy: p.spy,
  }));
  const sectorTotal = series[series.length - 1]?.sector ?? 0;
  const spyTotal = series[series.length - 1]?.spy ?? 0;

  return (
    <div className="mt-3 rounded-xl border border-border bg-white p-4 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {sector.name.toUpperCase()} VS. S&P 500
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <ReturnBadge color="#f59e0b" label={sector.symbol} value={sectorTotal} />
            <ReturnBadge color="#3b82f6" label="SPY" value={spyTotal} />
            {loading && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading
              </span>
            )}
            {!loading && !error && data && (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
                Live · {data.series.length} bars
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setRange(r.id)}
              className={cn(
                "rounded-md border px-2 py-1 font-mono text-[10px] font-medium transition-colors",
                range === r.id
                  ? "border-foreground bg-foreground text-white"
                  : "border-border bg-white text-muted-foreground hover:bg-muted/40",
              )}
            >
              {r.label}
            </button>
          ))}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close chart"
            className="ml-2 rounded-md p-1.5 text-muted-foreground hover:bg-muted/40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Chart */}
      <div className="mt-4 h-[280px]">
        {error && (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
              {error}
            </div>
          </div>
        )}
        {!error && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 5, right: 20, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`grad-sector-${sector.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
                </linearGradient>
                <linearGradient id={`grad-spy-${sector.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
                minTickGap={40}
              />
              <YAxis
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                tickLine={false}
                axisLine={false}
                width={48}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 11,
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                }}
                formatter={(value, name) => [
                  `${(Number(value) * 100).toFixed(2)}%`,
                  name,
                ]}
              />
              <Area
                type="monotone"
                dataKey="sector"
                stroke="#f59e0b"
                strokeWidth={1.5}
                fill={`url(#grad-sector-${sector.symbol})`}
                name={sector.symbol}
                dot={false}
              />
              <Area
                type="monotone"
                dataKey="spy"
                stroke="#3b82f6"
                strokeWidth={1.5}
                fill={`url(#grad-spy-${sector.symbol})`}
                name="SPY"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Returns table — values come from the API, NOT derived from the
          chart series. Backend pulls Day / YTD / 1Y / 3Y from the full
          available bar history so these stay accurate regardless of
          which window the chart is zoomed into. */}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="text-left font-medium px-2 py-1.5"></th>
              <th className="text-right font-medium px-2 py-1.5">Day</th>
              <th className="text-right font-medium px-2 py-1.5">YTD</th>
              <th className="text-right font-medium px-2 py-1.5">1Y</th>
              <th className="text-right font-medium px-2 py-1.5">3Y</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            <tr className="border-t border-border/60">
              <td className="px-2 py-1.5 font-sans font-semibold text-foreground">
                {data?.sector_name ?? sector.name}
              </td>
              <PerfCell value={data?.sector_day ?? sector.perf_1d} />
              <PerfCell value={data?.sector_ytd} />
              <PerfCell value={data?.sector_1y} />
              <PerfCell value={data?.sector_3y} />
            </tr>
            <tr className="border-t border-border/60">
              <td className="px-2 py-1.5 font-sans font-semibold text-foreground">
                S&P 500
              </td>
              <PerfCell value={data?.spy_day} />
              <PerfCell value={data?.spy_ytd} />
              <PerfCell value={data?.spy_1y} />
              <PerfCell value={data?.spy_3y} />
            </tr>
          </tbody>
        </table>
      </div>

      {/* Footer link */}
      <div className="mt-3 flex items-center justify-end">
        <Link
          href={`/stocks/${sector.symbol}` as Route}
          className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          View {sector.symbol} sector detail
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

function ReturnBadge({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="text-xs font-medium">{label}</span>
      <span
        className={cn(
          "font-mono text-sm font-semibold tabular-nums",
          value >= 0 ? "text-emerald-600" : "text-red-500",
        )}
      >
        {(value * 100).toFixed(2)}%
      </span>
      <span className="text-[10px] text-muted-foreground">Total Return</span>
    </div>
  );
}

function PerfCell({ value }: { value: number | null | undefined }) {
  return (
    <td
      className={cn(
        "px-2 py-1.5 text-right",
        value == null
          ? "text-muted-foreground"
          : value >= 0
            ? "text-emerald-600"
            : "text-red-500",
      )}
    >
      {value != null ? fmtPct(value, 2) : "—"}
    </td>
  );
}

/**
 * Format an ISO date ("2025-08-14") as a short label ("8/14") for the
 * x-axis. Manual parse to avoid timezone drift — `new Date("2025-08-14")`
 * is parsed as UTC midnight and can render as "8/13" in Pacific.
 */
function formatDateLabel(iso: string): string {
  const [_y, m, d] = iso.split("-");
  if (!m || !d) return iso;
  return `${parseInt(m, 10)}/${parseInt(d, 10)}`;
}
