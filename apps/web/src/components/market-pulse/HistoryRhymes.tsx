"use client";

import { useEffect, useState } from "react";
import { Loader2, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { getHistoryRhymes } from "@/lib/api";
import type {
  HistoryRhymeMatch,
  HistoryRhymesResponse,
} from "@/lib/contracts";

/**
 * Section 4 — History Rhymes.
 *
 * "Today's macro setup most resembles these historical 5-day windows."
 *
 * **Phase 1e (2026-05-22):** the component now fetches from
 * `GET /api/market/history-rhymes` backed by
 * `macro_similarity_service.py`. The service:
 *
 *   1. Builds today's normalized 5-day return vector across 6 macro
 *      ETFs (TLT, VXX, UUP, HYG, GLD, USO)
 *   2. Slides the same 5-day window over the last ~5 years of
 *      `price_bars` and computes cosine similarity vs today's vector
 *   3. Returns the top 3 matches (deduped to be at least 14 trading
 *      days apart) with their post-window 30-day SPY outcome and a
 *      30-bar normalized sparkline
 *
 * Per Jimmy's 2026-05-21 feedback ("lastly I thought we talked about
 * history rhyme section" — promoted from the deferred Phase 3 spot
 * into the main page).
 *
 * The component degrades cleanly: any backend error renders a small
 * notice + the caveat string, never an exception.
 */

export function HistoryRhymes() {
  const [data, setData] = useState<HistoryRhymesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHistoryRhymes("US")
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message || "Could not load history rhymes.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      id="history"
      aria-labelledby="history-heading"
      className="space-y-3"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2
          id="history-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          History rhymes
        </h2>
        {loading ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading
          </span>
        ) : error || !data || data.matches.length === 0 ? (
          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
            No matches
          </span>
        ) : (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-900">
            Live · cosine sim
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Today&apos;s macro setup most resembles these historical 5-day
        windows. Cosine similarity across normalized 5-day return vectors
        for rates, vol, dollar, credit, gold &amp; oil. <em>Not a
          prediction</em> — sample sizes are tiny; markets often
        don&apos;t rhyme.
      </p>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {error}
        </div>
      )}

      {/* Loading skeletons */}
      {loading && (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-[180px] animate-pulse rounded-xl border border-border bg-muted/20"
            />
          ))}
        </div>
      )}

      {!loading && data && data.matches.length === 0 && !error && (
        <div className="rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          {data.caveat || "No historical windows in the lookback range yet."}
        </div>
      )}

      {!loading && data && data.matches.length > 0 && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            {data.matches.map((m) => (
              <MatchCard key={`${m.start_date}-${m.end_date}`} match={m} />
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground/70">
            {data.caveat}
          </div>
        </>
      )}
    </section>
  );
}

function MatchCard({ match }: { match: HistoryRhymeMatch }) {
  const isUp = match.post_window_30d_return >= 0;
  const simPct = Math.round(match.similarity * 100);

  return (
    <div className="rounded-xl border border-border bg-white p-3">
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-semibold text-sm leading-tight">{match.label}</div>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold tabular-nums",
            simPct >= 90
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : simPct >= 80
                ? "border-amber-200 bg-amber-50 text-amber-800"
                : "border-border bg-muted/30 text-foreground/70",
          )}
        >
          {simPct}% match
        </span>
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground leading-snug">
        {match.context}
      </div>

      <div className="mt-3">
        <Sparkline data={match.sample_sparkline} positive={isUp} />
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">
          30d after window
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-0.5 font-mono text-sm font-semibold tabular-nums",
            isUp ? "text-emerald-600" : "text-red-500",
          )}
        >
          {isUp ? (
            <TrendingUp className="h-3 w-3" />
          ) : (
            <TrendingDown className="h-3 w-3" />
          )}
          SPY {isUp ? "+" : ""}
          {(match.post_window_30d_return * 100).toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 220;
  const h = 40;
  const stepX = w / (data.length - 1);
  const points = data
    .map(
      (v, i) =>
        `${(i * stepX).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`,
    )
    .join(" ");
  const color = positive ? "#10b981" : "#ef4444";

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-full h-10"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
    </svg>
  );
}
