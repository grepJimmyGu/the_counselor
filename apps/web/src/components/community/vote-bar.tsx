"use client";

import { useEffect, useState } from "react";
import { useSession, signIn } from "next-auth/react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { castVote, removeVote, getVotes } from "@/lib/community-api";
import type { VoteSummary } from "@/lib/contracts";

interface VoteBarProps {
  symbol: string;
  compact?: boolean;
}

export function VoteBar({ symbol, compact = false }: VoteBarProps) {
  const { data: session } = useSession();
  const [summary, setSummary] = useState<VoteSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVotes(symbol, session?.user?.id)
      .then(setSummary)
      .catch(() => {});
  }, [symbol, session?.user?.id]);

  const handleVote = async (vote: "bull" | "bear" | "hold") => {
    if (!session?.user) { signIn("google"); return; }
    setLoading(true);
    setError(null);
    try {
      const isSame = summary?.user_vote === vote;
      const updated = isSame
        ? await removeVote(symbol)
        : await castVote(symbol, vote);
      setSummary(updated as VoteSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save vote.");
    }
    finally { setLoading(false); }
  };

  const total = summary?.total ?? 0;
  const bullPct = total > 0 ? Math.round(((summary?.bull ?? 0) / total) * 100) : 0;
  const bearPct = total > 0 ? Math.round(((summary?.bear ?? 0) / total) * 100) : 0;

  if (compact) {
    return (
      <div className="flex items-center gap-1">
        {(["bull", "bear", "hold"] as const).map((v) => {
          const icons = { bull: TrendingUp, bear: TrendingDown, hold: Minus };
          const colors = {
            bull: "text-emerald-600 hover:bg-emerald-50",
            bear: "text-red-500 hover:bg-red-50",
            hold: "text-amber-500 hover:bg-amber-50",
          };
          const active = {
            bull: "bg-emerald-100 border-emerald-300 text-emerald-700",
            bear: "bg-red-100 border-red-300 text-red-700",
            hold: "bg-amber-100 border-amber-300 text-amber-700",
          };
          const Icon = icons[v];
          const isActive = summary?.user_vote === v;
          return (
            <button
              key={v}
              onClick={() => handleVote(v)}
              disabled={loading}
              className={cn(
                "flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-all cursor-pointer",
                isActive ? active[v] : `border-border bg-white ${colors[v]}`
              )}
            >
              <Icon className="h-2.5 w-2.5" />
              {summary?.[v] ?? 0}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Community Sentiment</span>
        {total > 0 && <span>{total} vote{total !== 1 ? "s" : ""}</span>}
      </div>

      {/* Vote buttons */}
      <div className="grid grid-cols-3 gap-2">
        {(["bull", "bear", "hold"] as const).map((v) => {
          const label = { bull: "Bullish", bear: "Bearish", hold: "Neutral" }[v];
          const Icon = { bull: TrendingUp, bear: TrendingDown, hold: Minus }[v];
          const base = {
            bull: "border-emerald-200 hover:bg-emerald-50 text-emerald-700",
            bear: "border-red-200 hover:bg-red-50 text-red-600",
            hold: "border-amber-200 hover:bg-amber-50 text-amber-600",
          }[v];
          const activeClass = {
            bull: "bg-emerald-100 border-emerald-400 text-emerald-800 font-semibold",
            bear: "bg-red-100 border-red-400 text-red-800 font-semibold",
            hold: "bg-amber-100 border-amber-400 text-amber-800 font-semibold",
          }[v];
          const isActive = summary?.user_vote === v;
          return (
            <button
              key={v}
              onClick={() => handleVote(v)}
              disabled={loading}
              className={cn(
                "flex flex-col items-center gap-1 rounded-lg border py-2.5 text-xs transition-all cursor-pointer",
                isActive ? activeClass : `bg-white ${base}`
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
              <span className="font-mono font-bold">{summary?.[v] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {error && (
        <p className="text-center text-[10px] text-red-600" role="status">
          {error}
        </p>
      )}

      {/* Bar */}
      {total > 0 && (
        <div className="flex h-1.5 overflow-hidden rounded-full">
          <div className="bg-emerald-400 transition-all" style={{ width: `${bullPct}%` }} />
          <div className="bg-amber-300 transition-all" style={{ width: `${100 - bullPct - bearPct}%` }} />
          <div className="bg-red-400 transition-all" style={{ width: `${bearPct}%` }} />
        </div>
      )}

      {!session?.user && (
        <p className="text-center text-[10px] text-muted-foreground">
          <button onClick={() => signIn("google")} className="text-primary cursor-pointer hover:underline">
            Sign in
          </button>{" "}
          to vote
        </p>
      )}
    </div>
  );
}
