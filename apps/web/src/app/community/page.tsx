"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BarChart2, TrendingUp, Users, AlertTriangle, Flame, Target } from "lucide-react";
import type { Route } from "next";
import { getCommunityBoard } from "@/lib/community-api";
import { getPublicStrategies, getStrategyLivePerformance } from "@/lib/api";
import type { LivePerformance, PublicStrategyItem, SignalScore } from "@/lib/contracts";
import { UpvoteButton } from "@/components/community/upvote-button";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { VoteBar } from "@/components/community/vote-bar";
import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";

// ── Rank badge ─────────────────────────────────────────────────────────────

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return (
    <div className="shrink-0 flex h-7 w-7 items-center justify-center rounded-full bg-amber-100 text-xs font-bold text-amber-700 ring-1 ring-amber-300">1</div>
  );
  if (rank === 2) return (
    <div className="shrink-0 flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-600 ring-1 ring-slate-300">2</div>
  );
  if (rank === 3) return (
    <div className="shrink-0 flex h-7 w-7 items-center justify-center rounded-full bg-orange-100 text-xs font-bold text-orange-700 ring-1 ring-orange-300">3</div>
  );
  return <div className="shrink-0 flex h-7 w-7 items-center justify-center text-xs font-mono text-muted-foreground">{rank}</div>;
}

// ── Stock board row ────────────────────────────────────────────────────────

function BoardRow({ item, rank }: { item: SignalScore; rank: number }) {
  const bullPct = item.total_votes > 0
    ? Math.round((item.bull_votes / item.total_votes) * 100) : 0;
  const isTop3 = rank <= 3;
  const signalColor = item.signal_score >= 60 ? "bg-emerald-400" : item.signal_score >= 45 ? "bg-amber-400" : "bg-muted-foreground/30";

  return (
    <Link
      href={`/stocks/${item.symbol}` as Route}
      className={cn(
        "flex items-center gap-3 rounded-xl border bg-white px-4 py-3 shadow-sm transition-all duration-200 hover:shadow-md hover:border-primary/40 cursor-pointer",
        isTop3 ? "border-border" : "border-border/60"
      )}
    >
      <RankBadge rank={rank} />

      {/* Symbol */}
      <div className="w-14 shrink-0">
        <div className={cn("font-mono text-sm font-bold", isTop3 ? "text-foreground" : "text-foreground/80")}>
          {item.symbol}
        </div>
      </div>

      {/* Signal bar */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-1">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <div className={cn("h-full rounded-full transition-all duration-500", signalColor)} style={{ width: `${item.signal_score}%` }} />
          </div>
          <span className="w-7 font-mono text-[10px] font-semibold tabular-nums text-muted-foreground">{item.signal_score.toFixed(0)}</span>
        </div>
        <span className="text-[10px] text-muted-foreground">{item.signal_label}</span>
      </div>

      {/* Stats — hidden on mobile */}
      <div className="hidden sm:flex items-center gap-4 text-xs text-muted-foreground shrink-0">
        <span className="flex items-center gap-1"><Users className="h-3 w-3" />{item.watchlist_count}</span>
        {item.total_votes > 0 && (
          <span className="flex items-center gap-1 text-emerald-600">
            <TrendingUp className="h-3 w-3" />{bullPct}%
          </span>
        )}
        {item.strategy_run_count > 0 && (
          <span className="flex items-center gap-1"><BarChart2 className="h-3 w-3" />{item.strategy_run_count}</span>
        )}
      </div>

      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
    </Link>
  );
}

// ── Mini sparkline for strategy return ────────────────────────────────────

function ReturnSparkline({ curve }: { curve: Array<{ date: string; value: number }> }) {
  if (!curve || curve.length < 3) return null;
  const isPos = curve[curve.length - 1].value >= curve[0].value;
  return (
    <div className="w-16 h-8 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={curve}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={isPos ? "#16a34a" : "#dc2626"}
            strokeWidth={1.5}
            dot={false}
          />
          <Tooltip
            contentStyle={{ display: "none" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Strategy row ───────────────────────────────────────────────────────────

function StrategyRow({ s, rank, live }: { s: PublicStrategyItem; rank: number; live: LivePerformance | null }) {
  const ret = live?.total_return_pct;
  const hasReturn = ret != null;
  const isPos = hasReturn && ret >= 0;
  const isComputing = !live;
  const isToday = live?.error?.includes("Published today");

  return (
    <div className={cn(
      "flex items-center gap-3 rounded-xl border bg-white px-4 py-3 shadow-sm transition-all duration-200 hover:shadow-md hover:border-primary/40",
      rank <= 3 ? "border-border" : "border-border/60"
    )}>
      <RankBadge rank={rank} />

      {/* Return — hero metric */}
      <div className="shrink-0 w-24 text-right">
        {isComputing ? (
          <div className="space-y-1">
            <Skeleton className="h-4 w-16 ml-auto" />
            <Skeleton className="h-3 w-10 ml-auto" />
          </div>
        ) : isToday ? (
          <div className="text-[10px] text-muted-foreground leading-tight">Tracking<br/>tomorrow</div>
        ) : (
          <>
            <div className={cn("font-mono text-base font-bold tabular-nums",
              hasReturn ? (isPos ? "text-emerald-600" : "text-red-600") : "text-muted-foreground"
            )}>
              {hasReturn ? `${isPos ? "+" : ""}${ret.toFixed(2)}%` : "—"}
            </div>
            <div className="text-[9px] text-muted-foreground">
              {live?.days_tracked ? `${live.days_tracked}d` : "since pub."}
            </div>
          </>
        )}
      </div>

      {/* Sparkline */}
      {live?.equity_curve && live.equity_curve.length >= 3 && (
        <ReturnSparkline curve={live.equity_curve as Array<{ date: string; value: number }>} />
      )}

      {/* Name + meta */}
      <div className="flex-1 min-w-0">
        <Link
          href={`/strategies/${s.slug}` as Route}
          className="text-sm font-semibold hover:text-primary transition-colors truncate block cursor-pointer"
        >
          {s.name}
        </Link>
        <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
          <span>{new Date(s.saved_at).toLocaleDateString()}</span>
          {live?.current_signal && live.current_signal !== "unknown" && (
            <span className={cn("capitalize rounded px-1 py-px text-[9px]",
              live.current_signal === "long" ? "bg-emerald-50 text-emerald-700" : "bg-muted text-muted-foreground"
            )}>
              {live.current_signal}
            </span>
          )}
        </p>
      </div>

      <UpvoteButton slug={s.slug} />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function CommunityPage() {
  const [items, setItems] = useState<SignalScore[]>([]);
  const [strategies, setStrategies] = useState<PublicStrategyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [livePerfs, setLivePerfs] = useState<Record<string, LivePerformance>>({});
  const [activeTab, setActiveTab] = useState<"stocks" | "strategies">("stocks");

  useEffect(() => {
    Promise.all([
      getCommunityBoard(20).then((r) => setItems(r.items)).catch(() => {}),
      getPublicStrategies(20).then((list) => {
        setStrategies(list);
        list.forEach((s) => {
          if (!s.live) {
            getStrategyLivePerformance(s.slug)
              .then((lp) => setLivePerfs((prev) => ({ ...prev, [s.slug]: lp })))
              .catch(() => {});
          }
        });
      }).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  // Compute activity stats
  const totalWatchlists = items.reduce((s, i) => s + i.watchlist_count, 0);
  const totalVotes = items.reduce((s, i) => s + i.total_votes, 0);
  const totalRuns = items.reduce((s, i) => s + i.strategy_run_count, 0);
  const publicStrategiesWithReturn = strategies.filter(s => {
    const live = s.live ?? livePerfs[s.slug];
    return live?.total_return_pct != null;
  }).length;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-6 px-4 py-8 md:px-6 lg:px-8">

        {/* Header */}
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
            <Link href={"/" as Route} className="hover:text-foreground transition-colors">Home</Link>
            <span>/</span>
            <span className="text-foreground">Community</span>
          </div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="font-heading text-2xl font-bold">Community</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Stocks ranked by watchlist adds, votes, and strategy runs — not returns.
              </p>
            </div>
            <Link
              href={"/workspace" as Route}
              className="shrink-0 flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
            >
              Share a strategy
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>

        {/* Activity stats strip */}
        {!loading && (totalVotes > 0 || totalWatchlists > 0 || strategies.length > 0) && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { icon: Users, label: "Watchlist adds", value: totalWatchlists, color: "text-blue-600", bg: "bg-blue-50" },
              { icon: TrendingUp, label: "Total votes", value: totalVotes, color: "text-emerald-600", bg: "bg-emerald-50" },
              { icon: BarChart2, label: "Strategy runs", value: totalRuns, color: "text-purple-600", bg: "bg-purple-50" },
              { icon: Target, label: "Live strategies", value: strategies.length, color: "text-amber-600", bg: "bg-amber-50" },
            ].map(({ icon: Icon, label, value, color, bg }) => (
              <div key={label} className="flex items-center gap-3 rounded-xl border border-border bg-white px-4 py-3 shadow-sm">
                <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", bg)}>
                  <Icon className={cn("h-4 w-4", color)} />
                </div>
                <div>
                  <div className={cn("font-mono text-lg font-bold tabular-nums", color)}>{value}</div>
                  <div className="text-[10px] text-muted-foreground">{label}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Mobile tab switcher */}
        <div className="flex gap-1 rounded-lg border border-border bg-muted/30 p-1 lg:hidden">
          {(["stocks", "strategies"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "flex-1 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-all cursor-pointer",
                activeTab === tab ? "bg-white shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab === "stocks" ? `Stocks ${items.length > 0 ? `(${items.length})` : ""}` : `Strategies ${strategies.length > 0 ? `(${strategies.length})` : ""}`}
            </button>
          ))}
        </div>

        <div className="grid gap-8 lg:grid-cols-3">

          {/* Board + Strategies — 2/3 width */}
          <div className="lg:col-span-2 space-y-8">

            {/* Most active stocks — hidden on mobile if strategies tab active */}
            <div className={cn("space-y-3", activeTab === "strategies" && "hidden lg:block")}>
              <div className="flex items-center gap-2">
                <Flame className="h-4 w-4 text-orange-500" />
                <h2 className="text-base font-semibold">Most Active Stocks</h2>
                {!loading && items.length > 0 && (
                  <Badge variant="outline" className="ml-auto font-mono text-[10px]">{items.length}</Badge>
                )}
              </div>
              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-xl" />)}
                </div>
              ) : items.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-white p-8 text-center space-y-2">
                  <Users className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">No community activity yet.</p>
                  <p className="text-xs text-muted-foreground">
                    <Link href={"/stocks" as Route} className="text-primary hover:underline">Browse stocks</Link> and add them to your watchlist to start.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {items.map((item, i) => <BoardRow key={item.symbol} item={item} rank={i + 1} />)}
                </div>
              )}
            </div>

            {/* Public strategies — hidden on mobile if stocks tab active */}
            <div className={cn("space-y-3", activeTab === "stocks" && "hidden lg:block")}>
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-purple-500" />
                <h2 className="text-base font-semibold">Public Strategies</h2>
                <span className="ml-1 text-[10px] text-muted-foreground">ranked by live return since publish</span>
                {!loading && strategies.length > 0 && (
                  <Badge variant="outline" className="ml-auto font-mono text-[10px]">{strategies.length}</Badge>
                )}
              </div>
              {loading ? (
                <div className="space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
                </div>
              ) : strategies.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border bg-white p-8 text-center space-y-2">
                  <BarChart2 className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">No public strategies yet.</p>
                  <p className="text-xs text-muted-foreground">
                    <Link href={"/workspace" as Route} className="text-primary hover:underline">Build a strategy</Link> and publish it to appear here.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {strategies.map((s, i) => (
                    <StrategyRow
                      key={s.slug}
                      s={s}
                      rank={i + 1}
                      live={s.live ?? livePerfs[s.slug] ?? null}
                    />
                  ))}
                </div>
              )}
            </div>

          </div>

          {/* Sidebar — 1/3 */}
          <div className="space-y-5">
            {/* Quick vote */}
            <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="h-4 w-4 text-emerald-500" />
                <h3 className="text-sm font-semibold">Vote on AAPL</h3>
              </div>
              <VoteBar symbol="AAPL" />
              <p className="mt-3 text-[10px] text-muted-foreground text-center">
                Visit any stock page to vote on it
              </p>
            </div>

            {/* How signal works */}
            <div className="rounded-xl border border-border bg-white p-5 shadow-sm space-y-4">
              <h3 className="text-sm font-semibold">Community Signal Formula</h3>
              <div className="space-y-2">
                {[
                  { icon: Users, label: "Watchlist adds", weight: "×1.5", color: "text-blue-500", bg: "bg-blue-50" },
                  { icon: TrendingUp, label: "Net bull votes", weight: "×1.0", color: "text-emerald-500", bg: "bg-emerald-50" },
                  { icon: BarChart2, label: "Strategy runs", weight: "×2.0", color: "text-purple-500", bg: "bg-purple-50" },
                ].map(({ icon: Icon, label, weight, color, bg }) => (
                  <div key={label} className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <div className={cn("flex h-6 w-6 items-center justify-center rounded-md", bg)}>
                        <Icon className={cn("h-3 w-3", color)} />
                      </div>
                      {label}
                    </div>
                    <span className="font-mono text-xs font-semibold text-foreground">{weight}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-md bg-muted/40 px-3 py-2 text-[10px] text-muted-foreground">
                Score = sigmoid((wl×1.5) + net_bulls + (runs×2.0)) → 0–100
              </div>
            </div>

            {/* Disclaimer */}
            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-[10px] text-muted-foreground">
              <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0 text-amber-500/70" />
              Community sentiment reflects aggregated user activity. Not financial advice.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
