"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Section 4 — History Rhymes (Phase 0a stub).
 *
 * "Today's macro setup most resembles these historical 5-day windows."
 * Visualizes pattern-match against ~5 years of price_bars via cosine
 * similarity on normalized 5-day macro return vectors.
 *
 * **Phase 0a status:** this component renders **hardcoded mock data**
 * so Jimmy can review the layout. The real backend
 * (`apps/api/app/services/macro_similarity_service.py`) + endpoint
 * (`GET /api/market/history-rhymes`) ship in Phase 1.
 *
 * Per Jimmy's 2026-05-21 feedback ("lastly I thought we talked about
 * history rhyme section" — promoted from the deferred Phase 3 spot into
 * the main page).
 */

interface HistoryMatch {
  label: string;
  context: string;
  similarity: number; // 0..1
  postWindow30dReturn: number; // decimal, e.g. 0.012 = +1.2%
  sampleSparkline: number[]; // 30 daily values, normalized so first = 100
}

const MOCK_MATCHES: HistoryMatch[] = [
  {
    label: "Aug 13–19, 2019",
    context: "Pre-Fed 50bps cut · trade-war jitters",
    similarity: 0.94,
    postWindow30dReturn: 0.012,
    sampleSparkline: [
      100, 100.4, 99.8, 100.2, 100.6, 101.1, 100.7, 101.3, 101.0, 100.8,
      101.4, 101.6, 101.2, 101.5, 101.0, 100.6, 101.1, 101.4, 101.2, 101.5,
      101.3, 101.1, 101.4, 101.0, 100.8, 101.3, 101.5, 101.2, 101.0, 101.2,
    ],
  },
  {
    label: "Mar 2–6, 2022",
    context: "Pre-rate-hike cycle · Ukraine invasion",
    similarity: 0.87,
    postWindow30dReturn: -0.082,
    sampleSparkline: [
      100, 100.2, 99.7, 98.9, 98.4, 97.5, 96.2, 95.4, 95.9, 94.7,
      93.8, 93.1, 92.5, 91.9, 92.6, 92.1, 91.8, 92.4, 91.6, 91.3,
      91.8, 91.2, 90.6, 91.4, 91.9, 92.3, 91.7, 91.4, 91.8, 91.8,
    ],
  },
  {
    label: "Jan 6–10, 2020",
    context: "Pre-COVID · Iran tensions",
    similarity: 0.81,
    postWindow30dReturn: -0.052,
    sampleSparkline: [
      100, 99.8, 99.4, 99.7, 100.1, 99.5, 99.0, 99.4, 99.1, 98.5,
      98.0, 97.7, 96.9, 96.2, 95.8, 95.3, 95.7, 95.1, 94.8, 95.0,
      94.4, 94.0, 94.6, 94.9, 94.3, 94.8, 94.6, 94.2, 95.0, 94.8,
    ],
  },
];

export function HistoryRhymes() {
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
        <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
          Preview · mock data
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Today&apos;s macro setup most resembles these historical 5-day
        windows. Cosine similarity across normalized 5-day return vectors
        for rates, vol, dollar, gold &amp; oil. <em>Not a prediction</em> —
        sample sizes are tiny; markets often don&apos;t rhyme.
      </p>

      <div className="grid gap-3 md:grid-cols-3">
        {MOCK_MATCHES.map((m) => (
          <MatchCard key={m.label} match={m} />
        ))}
      </div>
    </section>
  );
}

function MatchCard({ match }: { match: HistoryMatch }) {
  const isUp = match.postWindow30dReturn >= 0;
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
        <Sparkline data={match.sampleSparkline} positive={isUp} />
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
          {(match.postWindow30dReturn * 100).toFixed(1)}%
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
