"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Badge } from "@/components/ui/badge";
import type { MarketPositionSection, CompetitorSegment } from "@/lib/contracts";
// CompetitorSegment is used by RankingTable and CompetitorTabs below
import { cn } from "@/lib/utils";
import {
  LineChart, Line, Tooltip, ResponsiveContainer,
} from "recharts";

// ── Supply chain flow ─────────────────────────────────────────────────────────

function SupplyChain({ mp, symbol }: { mp: MarketPositionSection; symbol: string }) {
  const hasSuppliers = mp.upstream_suppliers.length > 0;
  const hasCustomers = mp.downstream_customers.length > 0;
  if (!hasSuppliers && !hasCustomers) return null;

  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Value Chain
      </div>
      <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/20 p-4">
        {/* Suppliers */}
        <div className="flex-1 min-w-0">
          {hasSuppliers && (
            <>
              <div className="mb-1.5 text-[10px] font-medium text-muted-foreground">Suppliers</div>
              <div className="flex flex-wrap gap-1.5">
                {mp.upstream_suppliers.map((s) =>
                  s.symbol ? (
                    <Link key={s.name} href={`/stocks/${s.symbol}` as Route}>
                      <Badge
                        variant="outline"
                        className="cursor-pointer font-mono text-[10px] hover:border-primary/50 transition-colors"
                      >
                        {s.symbol}
                      </Badge>
                    </Link>
                  ) : (
                    <Badge key={s.name} variant="outline" className="text-[10px] text-muted-foreground">
                      {s.name}
                    </Badge>
                  )
                )}
              </div>
            </>
          )}
        </div>

        {/* Arrow + symbol */}
        <div className="shrink-0 flex flex-col items-center gap-0.5 px-2">
          <div className="text-[10px] text-muted-foreground/50">←</div>
          <div className="rounded-lg border border-primary/30 bg-primary/5 px-2.5 py-1 font-mono text-xs font-bold text-primary">
            {symbol}
          </div>
          <div className="text-[10px] text-muted-foreground/50">→</div>
        </div>

        {/* Customers */}
        <div className="flex-1 min-w-0">
          {hasCustomers && (
            <>
              <div className="mb-1.5 text-[10px] font-medium text-muted-foreground text-right">Customers</div>
              <div className="flex flex-wrap justify-end gap-1.5">
                {mp.downstream_customers.map((c) =>
                  c.symbol ? (
                    <Link key={c.name} href={`/stocks/${c.symbol}` as Route}>
                      <Badge
                        variant="outline"
                        className="cursor-pointer font-mono text-[10px] hover:border-primary/50 transition-colors"
                      >
                        {c.symbol}
                      </Badge>
                    </Link>
                  ) : (
                    <Badge key={c.name} variant="outline" className="text-[10px] text-muted-foreground">
                      {c.name}
                    </Badge>
                  )
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Position dot ──────────────────────────────────────────────────────────────

function PositionDot({ position }: { position: string }) {
  if (position === "Dominant") return <span className="text-emerald-600 font-bold">●</span>;
  if (position === "Market Leader") return <span className="text-blue-500 font-bold">◉</span>;
  if (position === "Major Participant") return <span className="text-amber-500">○</span>;
  return <span className="text-muted-foreground">·</span>;
}

// ── 5-year sparkline ──────────────────────────────────────────────────────────

function ShareSparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return <span className="text-muted-foreground text-[10px]">—</span>;
  const chartData = data.map((v, i) => ({ i, v: Math.round(v * 100) }));
  return (
    <ResponsiveContainer width={60} height={24}>
      <LineChart data={chartData}>
        <Line type="monotone" dataKey="v" dot={false} stroke="#6366f1" strokeWidth={1.5} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Competitor ranking table ──────────────────────────────────────────────────

function RankingTable({
  rankings,
  disclaimer,
}: {
  rankings: CompetitorSegment["rankings"];
  disclaimer: string;
}) {
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] text-muted-foreground">
              <th className="pb-1.5 text-left font-medium">#</th>
              <th className="pb-1.5 text-left font-medium">Company</th>
              <th className="pb-1.5 text-right font-medium">Revenue</th>
              <th className="pb-1.5 text-right font-medium">Share</th>
              <th className="pb-1.5 text-center font-medium">Position</th>
              <th className="pb-1.5 text-right font-medium">5yr</th>
            </tr>
          </thead>
          <tbody>
            {rankings.map((r, i) => (
              <tr key={r.symbol} className="border-b border-border/30 last:border-0">
                <td className="py-2 font-mono text-muted-foreground">{i + 1}</td>
                <td className="py-2">
                  <Link
                    href={`/stocks/${r.symbol}` as Route}
                    className="font-medium hover:text-primary hover:underline transition-colors"
                  >
                    {r.name || r.symbol}
                  </Link>
                  <div className="font-mono text-[10px] text-muted-foreground">{r.symbol}</div>
                </td>
                <td className="py-2 text-right font-mono">{r.revenue}</td>
                <td className="py-2 text-right font-mono font-semibold">
                  {(r.share * 100).toFixed(0)}%
                </td>
                <td className="py-2 text-center">
                  <PositionDot position={r.position} />
                </td>
                <td className="py-2 flex justify-end">
                  <ShareSparkline data={r.trend_5yr} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-muted-foreground/70 leading-relaxed">{disclaimer}</p>
    </div>
  );
}

// ── Per-segment tabs ──────────────────────────────────────────────────────────

function CompetitorTabs({ segments }: { segments: CompetitorSegment[] }) {
  const [activeTab, setActiveTab] = useState(segments[0]?.segment ?? "");
  const active = segments.find((s) => s.segment === activeTab) ?? segments[0];

  if (!active) return null;

  return (
    <div className="space-y-3">
      {/* Tab bar */}
      <div className="flex gap-1 overflow-x-auto rounded-lg border border-border bg-muted/30 p-1">
        {segments.map((seg) => (
          <button
            key={seg.segment}
            onClick={() => setActiveTab(seg.segment)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all",
              activeTab === seg.segment
                ? "bg-white shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {seg.segment}
          </button>
        ))}
      </div>

      {/* Active segment rankings */}
      <div className="rounded-lg border border-border bg-muted/10 p-4">
        <div className="mb-3 text-xs font-semibold text-foreground">
          {active.segment} — Competitive Position
        </div>
        {active.rankings.length > 0 ? (
          <RankingTable rankings={active.rankings} disclaimer={active.disclaimer} />
        ) : (
          <p className="text-xs text-muted-foreground">
            Ranking data is being computed — check back shortly.
          </p>
        )}
      </div>
    </div>
  );
}

// ── Composed market position section ─────────────────────────────────────────

interface Props {
  mp: MarketPositionSection;
  symbol: string;
  competitorSegments: CompetitorSegment[];
}

export function MarketPositionSectionUI({ mp, symbol, competitorSegments }: Props) {
  return (
    <div className="space-y-5">

      {/* Growth drivers + risks */}
      {(mp.key_growth_drivers.length > 0 || mp.key_risks.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {mp.key_growth_drivers.length > 0 && (
            <div>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Growth Drivers
              </div>
              <ul className="space-y-1 text-xs text-foreground/75">
                {mp.key_growth_drivers.map((d) => (
                  <li key={d} className="flex gap-1.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {mp.key_risks.length > 0 && (
            <div>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Key Risks
              </div>
              <ul className="space-y-1 text-xs text-foreground/75">
                {mp.key_risks.map((r) => (
                  <li key={r} className="flex gap-1.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Peers */}
      {mp.key_competitors.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Peers
          </div>
          <div className="flex flex-wrap gap-1.5">
            {mp.key_competitors.map((c) => (
              <Link key={c} href={`/stocks/${c}` as Route}>
                <Badge
                  variant="outline"
                  className="cursor-pointer font-mono text-xs hover:border-primary/40 transition-colors"
                >
                  {c}
                </Badge>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Supply chain flow */}
      <SupplyChain mp={mp} symbol={symbol} />

      {/* Per-segment competitor tabs */}
      {competitorSegments.length > 0 && (
        <div>
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Competitive Position by Segment
          </div>
          <CompetitorTabs segments={competitorSegments} />
        </div>
      )}

      {/* Market metadata chips */}
      {(mp.market_growth_label || mp.competitive_position_label ||
        (mp.market_size_estimate && mp.market_size_estimate !== "estimate unavailable" && mp.market_size_estimate !== "Not disclosed")) && (
        <div className="flex flex-wrap gap-2">
          {mp.market_size_estimate && mp.market_size_estimate !== "estimate unavailable" && mp.market_size_estimate !== "Not disclosed" && (
            <div className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs">
              <span className="font-semibold text-muted-foreground">Market size:</span>{" "}
              <span>{mp.market_size_estimate}</span>
            </div>
          )}
          {mp.market_growth_label && (
            <div className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs">
              <span className="font-semibold text-muted-foreground">Growth:</span>{" "}
              <span className="capitalize">{mp.market_growth_label}</span>
            </div>
          )}
          {mp.competitive_position_label && (
            <div className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs">
              <span className="font-semibold text-muted-foreground">Position:</span>{" "}
              <span className="capitalize">{mp.competitive_position_label}</span>
            </div>
          )}
        </div>
      )}

      {mp.confidence === "partial" && (
        <div className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
          Market intelligence sourced from 10-K filing when available · Supply chain and competitor data auto-extracted
        </div>
      )}
    </div>
  );
}
