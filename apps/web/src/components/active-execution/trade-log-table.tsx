/**
 * PRD-16c-6 — TradeLogTable.
 *
 * Chronological event log flattened across every position for this
 * strategy. Newest first; paginated via `?before=` cursor.
 *
 * No polling — the trade log is append-only and the user clicks
 * "Load more" to fetch the next page. This matches the existing
 * notification-banner pattern (read-time, not live-time).
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { getStrategyTradeLog, type TradeEvent, type TradeLogResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  strategyId: string;
  pageSize?: number;
  className?: string;
}

export function TradeLogTable({
  strategyId,
  pageSize = 50,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [events, setEvents] = useState<TradeEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (before?: string) => {
      try {
        setLoading(true);
        const resp: TradeLogResponse = await getStrategyTradeLog(
          strategyId,
          backendToken ?? "",
          { limit: pageSize, before },
        );
        setEvents((prev) => (before ? [...prev, ...resp.events] : resp.events));
        setTotal(resp.total);
        setNextBefore(resp.next_before);
        setError(null);
      } catch (e) {
        setError((e as Error).message || "Failed to load.");
      } finally {
        setLoading(false);
      }
    },
    [strategyId, backendToken, pageSize],
  );

  useEffect(() => {
    if (sessionStatus === "loading") return;
    void loadPage();
  }, [sessionStatus, loadPage]);

  if (loading && events.length === 0) {
    return (
      <div data-testid="trade-log-skeleton" className={cn("space-y-1", className)}>
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-8 animate-pulse rounded border border-slate-200 bg-slate-50"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="trade-log-error"
        className={cn("rounded-md border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-700", className)}
      >
        Couldn't load trade log. {error}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div
        data-testid="trade-log-empty"
        className={cn("rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-[12px] text-slate-500", className)}
      >
        No trade events yet.
      </div>
    );
  }

  return (
    <div data-testid="trade-log-table" className={cn(className)}>
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Trade log
        </p>
        <p className="text-[10px] text-slate-400">{total} events</p>
      </div>
      <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
        <table className="w-full text-[12px]">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2 text-left">When</th>
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-left">Event</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Shares</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {events.map((e, i) => (
              <tr key={`${e.position_id}-${e.timestamp}-${i}`}>
                <td className="px-3 py-2 text-slate-500">
                  {new Date(e.timestamp).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </td>
                <td className="px-3 py-2 font-semibold">{e.symbol}</td>
                <td className="px-3 py-2">
                  {e.event}
                  {e.tier_label ? (
                    <span className="ml-1 text-slate-400">
                      ({e.tier_label})
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right">
                  {e.price !== null && e.price !== undefined
                    ? `$${e.price.toFixed(2)}`
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {e.shares_sold ?? e.shares ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {nextBefore && (
        <button
          type="button"
          onClick={() => loadPage(nextBefore)}
          disabled={loading}
          data-testid="trade-log-load-more"
          className="mt-2 w-full rounded-md border border-slate-200 bg-white py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Load more"}
        </button>
      )}
    </div>
  );
}
