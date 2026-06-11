/**
 * IntradayChart — live intraday price trend for each OPEN position, with
 * the exit-tier price levels drawn as horizontal lines and the
 * fired-trigger / entry events drawn as point markers.
 *
 * Reads `GET /api/saved-strategies/{id}/intraday-chart` (cache-only on the
 * backend — the monitor cron keeps the intraday_bars cache fresh). A cold
 * cache returns empty `bars`, which we render as a friendly "no bars yet"
 * note rather than an error (ties to the AlphaVantage data dependency).
 *
 * Conventions:
 *   - Trap #19 — fetch only after `useSession()` resolves.
 *   - Polls every 60s (intraday bars don't change faster than the cron
 *     refreshes them).
 *   - A text legend (entry + tier levels + trigger count) renders
 *     alongside the SVG so the data is accessible and testable without
 *     depending on recharts' SVG output.
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getIntradayChart,
  type IntradayChartResponse,
  type IntradayChartSeries,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  strategyId: string;
  /** Override the default 60s poll for tests + storybook. */
  pollIntervalMs?: number;
  /** Bumped by the parent (e.g. on declare) to force an immediate refetch. */
  refreshKey?: number;
  className?: string;
}

// US market data — always render the axis in US Eastern, regardless of the
// viewer's browser timezone. The backend emits ET-aware timestamps, so this
// formats the same instant into ET wall-clock for everyone.
function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function tierColor(triggerPct: number): string {
  return triggerPct >= 0 ? "#059669" /* emerald-600 */ : "#e11d48" /* rose-600 */;
}

export function IntradayChart({
  strategyId,
  pollIntervalMs = 60_000,
  refreshKey = 0,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [data, setData] = useState<IntradayChartResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (sessionStatus === "loading") return;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await getIntradayChart(strategyId, backendToken ?? "");
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message || "Failed to load.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void tick();
    const interval = window.setInterval(tick, pollIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [strategyId, backendToken, sessionStatus, pollIntervalMs, refreshKey]);

  if (loading && !data) {
    return (
      <div
        data-testid="intraday-chart-skeleton"
        className={cn("h-56 animate-pulse rounded-md border border-slate-200 bg-slate-50", className)}
      />
    );
  }

  if (error) {
    return (
      <div
        data-testid="intraday-chart-error"
        className={cn("rounded-md border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-700", className)}
      >
        Couldn&rsquo;t load the price chart. {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div data-testid="intraday-chart" className={cn(className)}>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Price &amp; signals · {data.bar_resolution} · ET
        </p>
        <p className="text-[10px] text-slate-400">
          {new Date(data.generated_at).toLocaleTimeString()}
        </p>
      </div>

      {data.series.length === 0 ? (
        <p
          data-testid="intraday-chart-empty"
          className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-[12px] text-slate-400"
        >
          No open positions to chart. Declare a position to start tracking it
          against your exit ladder.
        </p>
      ) : (
        <div className="space-y-5">
          {data.series.map((s) => (
            <PositionChart key={s.position_id} series={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function PositionChart({ series }: { series: IntradayChartSeries }) {
  const points = useMemo(
    () =>
      series.bars
        .map((b) => ({ t: Date.parse(b.t), close: b.close }))
        .filter((p) => Number.isFinite(p.t)),
    [series.bars],
  );

  // Triggers = every event except the initial entry (entry is shown as its
  // own line). Only those with a usable timestamp + price get a marker.
  const triggers = useMemo(
    () =>
      series.events
        .filter((e) => e.event !== "entry" && e.price != null)
        .map((e) => ({ t: Date.parse(e.t), price: e.price as number, label: e.tier_label ?? e.event }))
        .filter((e) => Number.isFinite(e.t)),
    [series.events],
  );

  return (
    <div
      data-testid={`intraday-chart-series-${series.symbol}`}
      className="rounded-lg border border-slate-200 bg-white p-3"
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-900">{series.symbol}</span>
        {series.entry_price != null && (
          <span className="text-[11px] text-slate-500">
            Entry ${series.entry_price.toFixed(2)}
          </span>
        )}
      </div>

      {/* Text legend — accessible + test-stable, independent of the SVG. */}
      <div
        data-testid={`intraday-chart-legend-${series.symbol}`}
        className="mb-2 flex flex-wrap gap-1.5"
      >
        {series.entry_price != null && (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
            Entry · ${series.entry_price.toFixed(2)}
          </span>
        )}
        {series.tiers.map((tier) => (
          <span
            key={tier.label}
            className="rounded-full px-2 py-0.5 text-[10px] font-medium"
            style={{
              backgroundColor: tier.trigger_pct >= 0 ? "#ecfdf5" : "#fff1f2",
              color: tierColor(tier.trigger_pct),
            }}
          >
            {tier.label} · {(tier.trigger_pct * 100).toFixed(0)}%
            {tier.price_level != null ? ` · $${tier.price_level.toFixed(2)}` : ""}
          </span>
        ))}
        {triggers.length > 0 && (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
            {triggers.length} fired
          </span>
        )}
      </div>

      {points.length === 0 ? (
        <p
          data-testid={`intraday-chart-nobars-${series.symbol}`}
          className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-[12px] text-slate-400"
        >
          No intraday bars cached yet — the monitor fills these during US
          market hours.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={fmtTime}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              minTickGap={40}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              width={48}
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            />
            <Tooltip
              labelFormatter={(ms) => fmtTime(Number(ms))}
              formatter={(v) => [`$${Number(v).toFixed(2)}`, "Close"]}
            />
            <Line
              type="monotone"
              dataKey="close"
              stroke="#0f172a"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />

            {/* Entry level */}
            {series.entry_price != null && (
              <ReferenceLine
                y={series.entry_price}
                stroke="#64748b"
                strokeDasharray="4 4"
                label={{ value: "Entry", position: "insideLeft", fontSize: 10, fill: "#64748b" }}
              />
            )}

            {/* Exit-tier levels */}
            {series.tiers.map((tier) =>
              tier.price_level != null ? (
                <ReferenceLine
                  key={tier.label}
                  y={tier.price_level}
                  stroke={tierColor(tier.trigger_pct)}
                  strokeDasharray="4 4"
                  label={{
                    value: tier.label,
                    position: "insideLeft",
                    fontSize: 10,
                    fill: tierColor(tier.trigger_pct),
                  }}
                />
              ) : null,
            )}

            {/* Fired-trigger markers */}
            {triggers.map((trig, i) => (
              <ReferenceDot
                key={`${trig.t}-${i}`}
                x={trig.t}
                y={trig.price}
                r={4}
                fill="#f59e0b"
                stroke="#ffffff"
                strokeWidth={1.5}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
