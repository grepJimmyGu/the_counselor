"use client";

import Link from "next/link";
import type { Route } from "next";
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { IndexCard } from "@/lib/contracts";
import { fmtPct, fmtPrice, fmtDate } from "@/lib/market-pulse-format";

/**
 * Section 2 — Indices Hero Strip.
 *
 * SPY (or whatever the first index is) gets a tall, prominent AreaChart
 * with axis labels; QQQ/IWM/DIA stack as compact rows beside it.
 * Mobile: SPY chart goes full-width, rows stack vertically below.
 *
 * Source data is `data.indices` (existing IndexCard[]). The hero chart
 * uses the same `sparkline_5d` series — short, but enough to convey the
 * 5-day trajectory. Bumping to a longer series is a backend follow-up.
 */

export function IndicesHero({ indices }: { indices: IndexCard[] }) {
  if (!indices?.length) return null;
  const hero = indices[0];
  const rest = indices.slice(1, 4);

  return (
    <section id="indices" aria-labelledby="indices-heading" className="space-y-3">
      <h2
        id="indices-heading"
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Indices
      </h2>
      <div className="grid gap-3 lg:grid-cols-3">
        <HeroCard card={hero} />
        <div className="flex flex-col gap-2">
          {rest.map((c) => (
            <CompactRow key={c.symbol} card={c} />
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Hero (large) ──────────────────────────────────────────────────────────────

function HeroCard({ card }: { card: IndexCard }) {
  const chartData = (card.sparkline_5d ?? []).map((v, i) => ({ i, v }));
  const isUp = card.perf_1d != null ? card.perf_1d >= 0 : true;
  const stroke = isUp ? "#10b981" : "#ef4444";

  return (
    <Link
      href={`/stocks/${card.symbol}` as Route}
      className="block lg:col-span-2 rounded-xl border border-border bg-white p-5 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-xs font-bold text-muted-foreground">
            {card.symbol}
          </div>
          <div className="mt-0.5 text-sm font-medium text-foreground/80">
            {card.name}
          </div>
        </div>
        <PerfBadge value={card.perf_1d} />
      </div>

      <div className="mt-3 flex items-baseline gap-3">
        <span className="font-mono text-3xl font-bold tracking-tight">
          {fmtPrice(card.price)}
        </span>
        {card.perf_5d != null && (
          <span
            className={cn(
              "text-xs font-medium",
              card.perf_5d >= 0 ? "text-emerald-600" : "text-red-500",
            )}
          >
            5D {fmtPct(card.perf_5d)}
          </span>
        )}
      </div>

      <div className="mt-3 h-[180px] sm:h-[200px] w-full">
        {chartData.length >= 2 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 6, right: 6, bottom: 6, left: 6 }}
            >
              <defs>
                <linearGradient
                  id={`hero-spark-${card.symbol}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis hide dataKey="i" />
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{
                  background: "rgba(15,23,42,0.92)",
                  border: 0,
                  borderRadius: 6,
                  color: "white",
                  fontSize: 12,
                }}
                formatter={(v) => fmtPrice(typeof v === "number" ? v : null)}
                labelFormatter={() => ""}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={stroke}
                strokeWidth={2}
                fill={`url(#hero-spark-${card.symbol})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            Chart loading…
          </div>
        )}
      </div>

      {card.latest_date && (
        <div className="mt-2 text-[10px] text-muted-foreground/70">
          As of {fmtDate(card.latest_date)}
          {card.is_stale ? " — stale" : ""}
        </div>
      )}
    </Link>
  );
}

// ── Compact row (small) ───────────────────────────────────────────────────────

function CompactRow({ card }: { card: IndexCard }) {
  const chartData = (card.sparkline_5d ?? []).map((v, i) => ({ i, v }));
  const isUp = card.perf_1d != null ? card.perf_1d >= 0 : true;
  const stroke = isUp ? "#10b981" : "#ef4444";

  return (
    <Link
      href={`/stocks/${card.symbol}` as Route}
      className="flex items-center gap-3 rounded-xl border border-border bg-white px-3.5 py-3 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
    >
      <div className="flex-1 min-w-0">
        <div className="font-mono text-xs font-bold text-muted-foreground">
          {card.symbol}
        </div>
        <div className="text-xs text-foreground/70 truncate">{card.name}</div>
      </div>
      {chartData.length >= 2 && (
        <div className="hidden sm:block shrink-0">
          <ResponsiveContainer width={70} height={32}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient
                  id={`small-spark-${card.symbol}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                dot={false}
                stroke={stroke}
                strokeWidth={1.5}
                fill={`url(#small-spark-${card.symbol})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="text-right shrink-0">
        <div className="font-mono text-sm font-bold">{fmtPrice(card.price)}</div>
        <PerfBadge value={card.perf_1d} compact />
      </div>
    </Link>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function PerfBadge({
  value,
  compact = false,
}: {
  value: number | null | undefined;
  compact?: boolean;
}) {
  if (value == null)
    return <span className="text-xs text-muted-foreground">—</span>;
  const isUp = value >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono font-semibold tabular-nums",
        compact ? "text-[11px]" : "text-sm",
        isUp ? "text-emerald-600" : "text-red-500",
      )}
    >
      {isUp ? (
        <TrendingUp className={compact ? "h-2.5 w-2.5" : "h-3 w-3"} />
      ) : (
        <TrendingDown className={compact ? "h-2.5 w-2.5" : "h-3 w-3"} />
      )}
      {fmtPct(value)}
    </span>
  );
}
