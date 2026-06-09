"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import { getSavedStrategy, updateStrategyVisibility, getStrategyLivePerformance } from "@/lib/api";
import { EquityCurveChart, DrawdownChart } from "@/components/workspace/charts";
import type { BacktestResult, LivePerformance, SavedStrategy } from "@/lib/contracts";
import { UpvoteButton } from "@/components/community/upvote-button";
import { CommentsSection } from "@/components/community/comments-section";
import { Globe, Lock, TrendingDown, TrendingUp, Copy, Check, AlertTriangle } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, Tooltip, Area, AreaChart } from "recharts";
import { cn } from "@/lib/utils";

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1.5 text-xl font-semibold tracking-tight">{value}</div>
    </div>
  );
}

function fmt(n: number, isPercent = false) {
  return isPercent ? `${(n * 100).toFixed(2)}%` : n.toFixed(2);
}

export default function SavedStrategyPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: session } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;
  const [data, setData] = useState<SavedStrategy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPublic, setIsPublic] = useState<boolean | null>(null);
  const [togglingVisibility, setTogglingVisibility] = useState(false);
  const [livePerf, setLivePerf] = useState<LivePerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const perfPollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function fetchLivePerf(s: string, attempt = 0) {
    setPerfLoading(true);
    getStrategyLivePerformance(s)
      .then((lp) => {
        setLivePerf(lp);
        setPerfLoading(false);
        // If still computing (no return yet and no terminal error), poll once after 8s
        const isComputing = lp.total_return === null && !lp.error?.includes("Published today");
        if (isComputing && attempt < 3) {
          perfPollRef.current = setTimeout(() => fetchLivePerf(s, attempt + 1), 8000);
        }
      })
      .catch(() => setPerfLoading(false));
  }

  // Clean up poll timer on unmount
  useEffect(() => () => { if (perfPollRef.current) clearTimeout(perfPollRef.current); }, []);

  useEffect(() => {
    getSavedStrategy(slug)
      .then((d) => {
        setData(d);
        setIsPublic(d.is_public);
        // Auto-fetch live performance; poll until computation succeeds
        if (d.is_public) {
          fetchLivePerf(slug);
        }
      })
      .catch(() => setError("This strategy link is invalid or has been removed."));
  }, [slug]);

  if (error) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-4xl px-4 py-16 text-center">
          <p className="text-sm text-muted-foreground">{error}</p>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-4xl px-4 py-16 flex justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </main>
    );
  }

  const s = data.strategy_json;
  const m = data.metrics;
  const savedDate = new Date(data.saved_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const chartResult = {
    equity_curve: data.equity_curve,
    benchmark_curve: data.benchmark_curve,
    buy_and_hold_curve: [],
    drawdown_curve: data.drawdown_curve,
  } as unknown as BacktestResult;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8 space-y-8">

        {/* Header */}
        <div className="space-y-3 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/15 text-primary hover:bg-primary/15">Livermore</Badge>
            <Badge variant="outline">Public Strategy</Badge>
          </div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">{data.name}</h1>
            <div className="flex items-center gap-2 shrink-0 flex-wrap">
              {/* Share / copy link */}
              <button
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/strategies/${slug}`);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
                className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1 text-xs font-medium text-muted-foreground transition-all hover:border-primary/40 hover:text-primary"
                aria-label="Copy share link"
              >
                {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                {copied ? "Copied!" : "Share"}
              </button>
              {/* Visibility toggle — only renders for signed-in users; the
                  backend now requires a Bearer token and an owner match. */}
              <button
                onClick={async () => {
                  if (!backendToken) return;
                  setTogglingVisibility(true);
                  try {
                    const next = !isPublic;
                    await updateStrategyVisibility(backendToken, slug, next);
                    setIsPublic(next);
                  } catch {/* silent */}
                  finally { setTogglingVisibility(false); }
                }}
                disabled={togglingVisibility || !backendToken}
                className={cn(
                  "flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all",
                  isPublic
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    : "border-border bg-muted/30 text-muted-foreground hover:border-primary/40"
                )}
                title={isPublic ? "Click to make private" : "Click to make public"}
              >
                {isPublic ? <><Globe className="h-3 w-3" /> Public</> : <><Lock className="h-3 w-3" /> Private</>}
              </button>
              <UpvoteButton slug={slug} />
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Published {savedDate} · {s.universe.join(", ")} · {s.start_date} to {s.end_date} · vs {s.benchmark}
          </p>
        </div>

        {/* Disclaimer */}
        <div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground leading-5">
          This strategy was created and saved by a user of this tool. It is a historical backtest result,
          not a recommendation or validation. Historical analysis does not predict future returns.
          This tool does not execute trades or provide investment advice.
        </div>

        {/* Strategy Rules */}
        <section className="space-y-3">
          <h2 className="text-sm font-medium">Strategy Rules</h2>
          <div className="rounded-lg border border-border bg-background p-4 space-y-2 text-sm text-muted-foreground">
            <div><span className="text-foreground/60 mr-2">Type</span>{s.strategy_type.replace(/_/g, " ")}</div>
            <div><span className="text-foreground/60 mr-2">Universe</span>{s.universe.join(", ")}</div>
            <div><span className="text-foreground/60 mr-2">Benchmark</span>{s.benchmark}</div>
            <div><span className="text-foreground/60 mr-2">Period</span>{s.start_date} – {s.end_date}</div>
            <div><span className="text-foreground/60 mr-2">Rebalance</span>{s.rebalance_frequency}</div>
            <div><span className="text-foreground/60 mr-2">Transaction costs</span>{s.transaction_cost_bps} bps per trade</div>
            <div><span className="text-foreground/60 mr-2">Slippage</span>{s.slippage_bps} bps</div>
            {s.rules && s.rules.length > 0 && (
              <div>
                <span className="text-foreground/60 mr-2">Rules</span>
                <span className="font-mono text-xs">{JSON.stringify(s.rules)}</span>
              </div>
            )}
          </div>
        </section>

        {/* Credibility warnings */}
        {data.warnings.length > 0 && (
          <div className="space-y-2">
            {data.warnings.map((w, i) => (
              <div key={i} className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                {w}
              </div>
            ))}
          </div>
        )}

        {/* Key metrics */}
        <section className="space-y-3">
          <h2 className="text-sm font-medium">Backtest Results</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Total Return" value={fmt(m.total_return, true)} />
            <MetricCard label="Benchmark Return" value={fmt(m.benchmark_total_return, true)} />
            <MetricCard label="Max Drawdown" value={fmt(m.max_drawdown, true)} />
            <MetricCard label="Sharpe Ratio" value={fmt(m.sharpe_ratio)} />
            <MetricCard label="Win Rate" value={fmt(m.win_rate, true)} />
            <MetricCard label="Trades" value={String(m.number_of_trades)} />
            <MetricCard label="Excess vs Benchmark" value={fmt(m.excess_return_vs_benchmark, true)} />
            <MetricCard label="Time in Market" value={fmt(m.time_in_market, true)} />
          </div>
          <p className="text-xs text-muted-foreground">
            Historical simulation only. Does not account for taxes or real-world execution differences.
          </p>
        </section>

        {/* Live performance since publish */}
        {isPublic && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-medium">Live Performance</h2>
              <span className="text-[10px] text-muted-foreground">since published · updates daily</span>
              {perfLoading && livePerf && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
            </div>

            {!livePerf && perfLoading ? (
              <div className="flex items-center gap-3 rounded-xl border border-border bg-white px-5 py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground shrink-0" />
                <div>
                  <p className="text-sm font-medium">Computing live performance…</p>
                  <p className="text-xs text-muted-foreground">Fetching price data and running the strategy from publish date</p>
                </div>
              </div>
            ) : livePerf ? (
              <div className={cn(
                "rounded-xl border p-5",
                livePerf.total_return_pct != null && livePerf.total_return_pct >= 0
                  ? "border-emerald-200 bg-emerald-50/50"
                  : livePerf.total_return_pct != null
                  ? "border-red-200 bg-red-50/50"
                  : "border-border bg-white"
              )}>
                {livePerf.error?.includes("Published today") ? (
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <div className="h-10 w-10 shrink-0 flex items-center justify-center rounded-full bg-muted/50">
                      <TrendingUp className="h-5 w-5 text-muted-foreground/60" />
                    </div>
                    <div>
                      <p className="font-medium text-foreground">Tracking starts tomorrow</p>
                      <p className="text-xs">Performance data will appear after the first trading day.</p>
                    </div>
                  </div>
                ) : livePerf.error && !livePerf.total_return ? (
                  <p className="text-sm text-muted-foreground">{livePerf.error}</p>
                ) : (
                  <div className="flex flex-wrap items-stretch gap-4 sm:gap-6">
                    {/* Return — giant hero number */}
                    <div className="flex flex-col justify-center">
                      <div className="text-[10px] uppercase tracking-wide font-semibold text-muted-foreground mb-1">Return since published</div>
                      <div className={cn(
                        "flex items-center gap-1.5 font-mono font-bold tabular-nums",
                        livePerf.total_return_pct == null ? "text-muted-foreground text-3xl" :
                        livePerf.total_return_pct >= 0 ? "text-emerald-700 text-4xl" : "text-red-600 text-4xl"
                      )}>
                        {livePerf.total_return_pct == null ? "—" : (
                          <>
                            {livePerf.total_return_pct >= 0
                              ? <TrendingUp className="h-7 w-7" />
                              : <TrendingDown className="h-7 w-7" />}
                            {livePerf.total_return_pct >= 0 ? "+" : ""}
                            {livePerf.total_return_pct.toFixed(2)}%
                          </>
                        )}
                      </div>
                    </div>

                    {/* Sparkline of equity curve since publish */}
                    {livePerf.equity_curve && livePerf.equity_curve.length >= 3 && (
                      <div className="flex-1 min-w-[120px] h-16">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={livePerf.equity_curve as Array<{ date: string; value: number }>} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
                            <defs>
                              <linearGradient id="liveGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={livePerf.total_return_pct != null && livePerf.total_return_pct >= 0 ? "#16a34a" : "#dc2626"} stopOpacity={0.25} />
                                <stop offset="95%" stopColor={livePerf.total_return_pct != null && livePerf.total_return_pct >= 0 ? "#16a34a" : "#dc2626"} stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <Area
                              type="monotone"
                              dataKey="value"
                              stroke={livePerf.total_return_pct != null && livePerf.total_return_pct >= 0 ? "#16a34a" : "#dc2626"}
                              strokeWidth={2}
                              fill="url(#liveGrad)"
                              dot={false}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Secondary stats */}
                    <div className="flex flex-wrap gap-4 items-center">
                      <div>
                        <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Days tracked</div>
                        <div className="font-mono text-xl font-semibold">{livePerf.days_tracked}</div>
                      </div>
                      {livePerf.current_signal && livePerf.current_signal !== "unknown" && (
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Signal</div>
                          <div className={cn(
                            "mt-0.5 inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold capitalize",
                            livePerf.current_signal === "long" ? "bg-emerald-100 text-emerald-700" : "bg-muted text-muted-foreground"
                          )}>
                            {livePerf.current_signal}
                          </div>
                        </div>
                      )}
                      {livePerf.last_price_date && (
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase tracking-wide">Data through</div>
                          <div className="font-mono text-xs">{String(livePerf.last_price_date)}</div>
                        </div>
                      )}
                      {livePerf.computed_at && (
                        <div className="text-[10px] text-muted-foreground">
                          Updated {new Date(livePerf.computed_at).toLocaleString()}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </section>
        )}

        {/* Equity curve */}
        {data.equity_curve.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-medium">Strategy vs Benchmark</h2>
            <div className="rounded-lg border border-border bg-background p-4">
              <EquityCurveChart result={chartResult} />
            </div>
          </section>
        )}

        {/* Drawdown */}
        {data.drawdown_curve.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-medium">Drawdown</h2>
            <div className="rounded-lg border border-border bg-background p-4">
              <DrawdownChart result={chartResult} />
            </div>
          </section>
        )}

        {/* TODO(PRD-16c): wire <ActiveExecutionDashboard> here when
            the backend exposes the SavedStrategy UUID via the slug
            route. Today /api/strategies/{slug} returns a BacktestRecord
            with `slug` only; the dashboard endpoints (PRD-16c-3c) are
            owner-only and key on `saved_strategy_id` (UUID). Either:
              (a) extend the response with `saved_strategy_id: str|None`
                  for slugs that have a matching SavedStrategy, OR
              (b) add a dedicated `/saved-strategies/[id]` page on the
                  frontend that fetches via the auth'd UUID-keyed route.
            (b) is the cleaner long-term shape; (a) is the small
            unblocker. Tracked: PRD-16c §"Wire dashboard surface". */}

        {/* Community — comments */}
        <section className="rounded-xl border border-border bg-white p-5 shadow-sm">
          <CommentsSection slug={slug} />
        </section>

        {/* Footer disclaimer */}
        <div className="border-t border-border pt-6 text-xs text-muted-foreground">
          Historical analysis only. This result depends on the selected period, price data, and strategy
          assumptions. It should not be treated as a prediction or recommendation.
        </div>

      </div>
    </main>
  );
}
