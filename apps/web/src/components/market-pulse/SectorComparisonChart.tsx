"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, X } from "lucide-react";
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
import type { SectorCard } from "@/lib/contracts";
import { fmtPct } from "@/lib/market-pulse-format";

/**
 * Inline expansion under the sector heatmap. Renders a sector-ETF
 * vs S&P 500 cumulative return chart + returns table, modeled on the
 * Seeking Alpha "Sector vs S&P 500" comparison view Jimmy referenced
 * on 2026-05-21.
 *
 * **Phase 0a status:** chart data is hardcoded MOCK (synthetic 1-yr
 * normalized series). Real backend (`GET /api/sectors/{symbol}/comparison`
 * or extended `/api/company/{symbol}/trend`) ships in Phase 1. Returns
 * table values are derived from the mock series for visual consistency.
 *
 * **Time ranges:** Phase 0a supports 1M / 6M / YTD / 1Y / 3Y. 5Y / 10Y /
 * MAX would require extending backend `price_bars` retention past the
 * current 3-yr warmup window — deferred.
 */

type Range = "1M" | "6M" | "YTD" | "1Y" | "3Y";

const RANGES: { id: Range; label: string; days: number }[] = [
  { id: "1M", label: "1M", days: 22 },
  { id: "6M", label: "6M", days: 130 },
  { id: "YTD", label: "YTD", days: 100 },
  { id: "1Y", label: "1Y", days: 252 },
  { id: "3Y", label: "3Y", days: 756 },
];

export function SectorComparisonChart({
  sector,
  onClose,
}: {
  sector: SectorCard;
  onClose: () => void;
}) {
  const [range, setRange] = useState<Range>("1Y");

  // Mock series — generates a deterministic-ish synthetic walk so the
  // shape looks plausible and is stable across renders.
  const series = useMemo(
    () => buildMockSeries(sector.symbol, range),
    [sector.symbol, range],
  );

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
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
              Preview · mock series
            </span>
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
      </div>

      {/* Returns table */}
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
                {sector.name}
              </td>
              <PerfCell value={sector.perf_1d} />
              <PerfCell value={sector.perf_5d != null ? sector.perf_5d * 5 : null} />
              <PerfCell value={sectorTotal} />
              <PerfCell value={sectorTotal * 1.5} />
            </tr>
            <tr className="border-t border-border/60">
              <td className="px-2 py-1.5 font-sans font-semibold text-foreground">
                S&P 500
              </td>
              <PerfCell value={0.005} />
              <PerfCell value={0.08} />
              <PerfCell value={spyTotal} />
              <PerfCell value={spyTotal * 1.5} />
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

// ── Mock series builder ─────────────────────────────────────────────────────
//
// Deterministic-ish synthetic walk so the chart looks plausible without
// a real backend call. Uses the symbol string as a seed so different
// sectors produce visibly different paths.

function buildMockSeries(
  symbol: string,
  range: Range,
): { label: string; sector: number; spy: number }[] {
  const cfg = RANGES.find((r) => r.id === range)!;
  const days = cfg.days;
  const seed = hashString(symbol);

  // Sector drift varies by symbol; SPY drift is fixed-ish to look like the market.
  const sectorDrift = ((seed % 100) / 100) * 0.0008 - 0.0001; // ~ -0.01%/d to +0.07%/d
  const spyDrift = 0.0004;

  const points: { label: string; sector: number; spy: number }[] = [];
  let sectorCum = 0;
  let spyCum = 0;
  const today = new Date();

  for (let i = 0; i < days; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() - (days - 1 - i));
    const label = `${d.getMonth() + 1}/${d.getDate()}`;

    // Pseudo-random noise via sin combinations seeded by symbol + day.
    const sectorNoise =
      Math.sin((seed + i) * 0.37) * 0.008 +
      Math.sin((seed + i) * 0.13) * 0.004;
    const spyNoise =
      Math.sin((seed + i) * 0.21) * 0.006 +
      Math.sin((seed + i) * 0.09) * 0.003;

    sectorCum = sectorCum + sectorDrift + sectorNoise * 0.05;
    spyCum = spyCum + spyDrift + spyNoise * 0.04;

    points.push({ label, sector: sectorCum, spy: spyCum });
  }

  return points;
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
