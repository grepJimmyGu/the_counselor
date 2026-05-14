"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import { getSavedStrategy, updateStrategyVisibility, getStrategyLivePerformance } from "@/lib/api";
import { EquityCurveChart, DrawdownChart } from "@/components/workspace/charts";
import type { BacktestResult, LivePerformance, SavedStrategy } from "@/lib/contracts";
import { UpvoteButton } from "@/components/community/upvote-button";
import { CommentsSection } from "@/components/community/comments-section";
import { Globe, Lock, TrendingDown, TrendingUp } from "lucide-react";

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
  const [data, setData] = useState<SavedStrategy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPublic, setIsPublic] = useState<boolean | null>(null);
  const [togglingVisibility, setTogglingVisibility] = useState(false);
  const [livePerf, setLivePerf] = useState<LivePerformance | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);
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
        <div className="space-y-2 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/15 text-primary hover:bg-primary/15">Livermore</Badge>
            <Badge variant="outline">Saved Strategy</Badge>
          </div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h1 className="text-3xl font-semibold tracking-tight">{data.name}</h1>
            <div className="flex items-center gap-2 shrink-0">
              {/* Public/private toggle */}
              <button
                onClick={async () => {
                  setTogglingVisibility(true);
                  try {
                    const next = !isPublic;
                    await updateStrategyVisibility(slug, next);
                    setIsPublic(next);
                  } catch {/* silent */}
                  finally { setTogglingVisibility(false); }
                }}
                disabled={togglingVisibility}
                className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all ${
                  isPublic
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    : "border-border bg-muted/30 text-muted-foreground hover:border-primary/40"
                }`}
                title={isPublic ? "Click to make private" : "Click to make public"}
              >
                {isPublic
                  ? <><Globe className="h-3 w-3" /> Public</>
                  : <><Lock className="h-3 w-3" /> Private</>}
              </button>
              <UpvoteButton slug={slug} />
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Saved {savedDate} · {s.universe.join(", ")} · {s.start_date} – {s.end_date} · Benchmark: {s.benchmark}
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
              <div key={i} className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-xs text-yellow-300/80">
                ⚠ {w}
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
            <h2 className="text-sm font-medium flex items-center gap-2">
              Live Performance
              <span className="text-[10px] font-normal text-muted-foreground">since published · updates daily</span>
              {perfLoading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
            </h2>

            {!livePerf && perfLoading ? (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-4 py-5 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                Computing performance since publish date…
              </div>
            ) : livePerf ? (
              <div className="rounded-lg border border-border bg-background p-4">
                {livePerf.error?.includes("Published today") ? (
                  <p className="text-sm text-muted-foreground">
                    Published today — performance tracking begins tomorrow after market close.
                  </p>
                ) : livePerf.error && !livePerf.total_return ? (
                  <p className="text-sm text-muted-foreground">{livePerf.error}</p>
                ) : (
                  <div className="flex flex-wrap items-center gap-6">
                    {/* Return — primary metric */}
                    <div>
                      <div className="text-xs text-muted-foreground">Return since published</div>
                      <div className={`mt-0.5 flex items-center gap-1 text-2xl font-bold font-mono ${
                        livePerf.total_return_pct == null
                          ? "text-muted-foreground"
                          : livePerf.total_return_pct >= 0 ? "text-emerald-600" : "text-red-600"
                      }`}>
                        {livePerf.total_return_pct == null ? "—" : (
                          <>
                            {livePerf.total_return_pct >= 0
                              ? <TrendingUp className="h-5 w-5" />
                              : <TrendingDown className="h-5 w-5" />}
                            {livePerf.total_return_pct >= 0 ? "+" : ""}
                            {livePerf.total_return_pct.toFixed(2)}%
                          </>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Trading days tracked</div>
                      <div className="mt-0.5 text-lg font-semibold font-mono">{livePerf.days_tracked}</div>
                    </div>
                    {livePerf.current_signal && livePerf.current_signal !== "unknown" && (
                      <div>
                        <div className="text-xs text-muted-foreground">Current signal</div>
                        <div className="mt-0.5 text-sm font-semibold capitalize">{livePerf.current_signal}</div>
                      </div>
                    )}
                    {livePerf.last_price_date && (
                      <div>
                        <div className="text-xs text-muted-foreground">Data through</div>
                        <div className="mt-0.5 text-sm font-mono">{String(livePerf.last_price_date)}</div>
                      </div>
                    )}
                    {livePerf.computed_at && (
                      <div className="ml-auto text-[10px] text-muted-foreground">
                        Updated {new Date(livePerf.computed_at).toLocaleString()}
                      </div>
                    )}
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
