"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { ArrowRight, TrendingUp, Users, BarChart2, AlertTriangle } from "lucide-react";
import type { Route } from "next";
import { getCommunityBoard } from "@/lib/community-api";
import type { SignalScore } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { VoteBar } from "@/components/community/vote-bar";

function SignalBar({ score }: { score: number }) {
  const color = score >= 60 ? "bg-emerald-400" : score >= 50 ? "bg-amber-400" : "bg-muted";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className="w-8 font-mono text-xs font-semibold tabular-nums">{score.toFixed(0)}</span>
    </div>
  );
}

function BoardRow({ item }: { item: SignalScore }) {
  const bullPct = item.total_votes > 0
    ? Math.round((item.bull_votes / item.total_votes) * 100) : 0;

  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-white px-4 py-3 shadow-sm hover:border-primary/30 transition-colors">
      <Link href={`/stocks/${item.symbol}` as Route} className="w-16 shrink-0">
        <span className="font-mono text-sm font-bold hover:text-primary transition-colors">
          {item.symbol}
        </span>
      </Link>

      <div className="flex-1 min-w-0">
        <SignalBar score={item.signal_score} />
        <span className="text-[10px] text-muted-foreground">{item.signal_label}</span>
      </div>

      <div className="hidden sm:flex items-center gap-4 text-xs text-muted-foreground shrink-0">
        <div className="flex items-center gap-1">
          <Users className="h-3 w-3" />
          <span>{item.watchlist_count}</span>
        </div>
        <div className="flex items-center gap-1">
          <TrendingUp className="h-3 w-3 text-emerald-500" />
          <span>{bullPct}% bull</span>
        </div>
        <div className="flex items-center gap-1">
          <BarChart2 className="h-3 w-3" />
          <span>{item.strategy_run_count} runs</span>
        </div>
      </div>

      <Link
        href={`/stocks/${item.symbol}` as Route}
        className="shrink-0 text-muted-foreground hover:text-primary transition-colors"
      >
        <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}

export default function CommunityPage() {
  const { data: session } = useSession();
  const [items, setItems] = useState<SignalScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [spotlightSymbol] = useState("AAPL");

  useEffect(() => {
    getCommunityBoard(20)
      .then((r) => setItems(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-8 px-4 py-8 md:px-6 lg:px-8">

        {/* Header */}
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
            <Link href={"/" as Route} className="hover:text-foreground">Home</Link>
            <span>/</span>
            <span className="text-foreground">Community</span>
          </div>
          <h1 className="font-heading text-2xl font-bold">Community</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Stocks ranked by watchlist adds, votes, and strategy runs — not returns.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-3">

          {/* Board — 2/3 width */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Most Active This Week</h2>
              {items.length > 0 && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  {items.length} stocks
                </Badge>
              )}
            </div>

            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-xl" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-white p-8 text-center text-sm text-muted-foreground">
                No community activity yet.
                <br />
                Add stocks to your watchlist and vote to start building the board.
              </div>
            ) : (
              <div className="space-y-2">
                {items.map((item) => <BoardRow key={item.symbol} item={item} />)}
              </div>
            )}
          </div>

          {/* Sidebar — 1/3 */}
          <div className="space-y-5">
            {/* Quick vote */}
            <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
              <h3 className="mb-4 text-sm font-semibold">Quick Vote</h3>
              <VoteBar symbol={spotlightSymbol} />
              <p className="mt-3 text-[10px] text-muted-foreground text-center">
                Voting on {spotlightSymbol} · Click any ticker on the board to vote
              </p>
            </div>

            {/* How it works */}
            <div className="rounded-xl border border-border bg-white p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-semibold">How the signal works</h3>
              {[
                { icon: Users, label: "Watchlist adds", weight: "×1.5" },
                { icon: TrendingUp, label: "Net bull votes", weight: "×1.0" },
                { icon: BarChart2, label: "Strategy runs", weight: "×2.0" },
              ].map(({ icon: Icon, label, weight }) => (
                <div key={label} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </div>
                  <Badge variant="outline" className="font-mono text-[10px]">{weight}</Badge>
                </div>
              ))}
            </div>

            {/* Disclaimer */}
            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-[10px] text-muted-foreground">
              <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0 text-amber-500/70" />
              Community sentiment reflects user activity on this platform. Not financial advice.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
