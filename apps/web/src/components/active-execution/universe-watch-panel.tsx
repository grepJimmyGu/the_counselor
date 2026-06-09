/**
 * PRD-16c-6 — UniverseWatchPanel.
 *
 * Renders one card per universe ticker with the latest cached price.
 * Reads from `GET /api/saved-strategies/{id}/universe-state` which
 * pulls from the intraday_bars cache only (no AV roundtrip on the GET
 * path). Symbols with `source='no_data'` show a placeholder.
 *
 * Conventions:
 *   - Trap #19 — fires after `useSession()` resolves, never during the
 *     loading window.
 *   - Polls every 30s (live but not aggressive). PRD-16c §"Live
 *     dashboard polls 30s — no faster (avoid hammering)."
 *   - Skeleton state on initial load (3 placeholder cards).
 */
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import {
  getUniverseState,
  type UniverseStateResponse,
  type UniverseSymbolState,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  strategyId: string;
  /** Override the default 30s poll for tests + storybook. */
  pollIntervalMs?: number;
  className?: string;
}

export function UniverseWatchPanel({
  strategyId,
  pollIntervalMs = 30_000,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [state, setState] = useState<UniverseStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (sessionStatus === "loading") return;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await getUniverseState(strategyId, backendToken ?? "");
        if (!cancelled) {
          setState(next);
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
  }, [strategyId, backendToken, sessionStatus, pollIntervalMs]);

  if (loading && !state) {
    return (
      <div data-testid="universe-watch-skeleton" className={cn("grid grid-cols-2 gap-2 sm:grid-cols-3", className)}>
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-md border border-slate-200 bg-slate-50"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="universe-watch-error"
        className={cn("rounded-md border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-700", className)}
      >
        Couldn't load universe state. {error}
      </div>
    );
  }

  if (!state) return null;

  return (
    <div data-testid="universe-watch-panel" className={cn(className)}>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Universe watch · {state.bar_resolution}
        </p>
        <p className="text-[10px] text-slate-400">
          {new Date(state.generated_at).toLocaleTimeString()}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {state.universe.map((row) => (
          <UniverseCard key={row.symbol} row={row} />
        ))}
      </div>
    </div>
  );
}

function UniverseCard({ row }: { row: UniverseSymbolState }) {
  const hasData = row.source === "intraday" && row.latest_price !== null;
  return (
    <div
      data-testid={`universe-card-${row.symbol}`}
      className={cn(
        "rounded-md border bg-white p-3",
        hasData ? "border-slate-200" : "border-slate-100 bg-slate-50",
      )}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {row.symbol}
      </p>
      {hasData ? (
        <>
          <p className="mt-1 text-base font-bold text-slate-900">
            ${row.latest_price!.toFixed(2)}
          </p>
          <p className="text-[10px] text-slate-400">
            {row.latest_at &&
              new Date(row.latest_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
          </p>
        </>
      ) : (
        <p className="mt-2 text-[12px] text-slate-400">No recent bar</p>
      )}
    </div>
  );
}
