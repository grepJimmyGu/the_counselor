/**
 * PRD-16c-6 — PositionCardsGrid.
 *
 * One card per open + recently-closed position. Each card shows:
 *   - Symbol + status badge (open / closed)
 *   - Entry vs current price
 *   - Signed % change (color-coded)
 *   - Shares remaining
 *   - Mini trade-log timeline
 *
 * Reads from `GET /api/saved-strategies/{id}/positions`. Polls every 30s.
 * Trap #19 guards apply — fires after sessionStatus !== 'loading'.
 */
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import {
  getStrategyPositions,
  type PositionView,
  type PositionsResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  strategyId: string;
  pollIntervalMs?: number;
  /** Bump to force an immediate refetch (e.g. after declaring a new
   *  position). Any change to this value re-runs the fetch effect. */
  refreshKey?: number;
  className?: string;
}

export function PositionCardsGrid({
  strategyId,
  pollIntervalMs = 30_000,
  refreshKey = 0,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [state, setState] = useState<PositionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (sessionStatus === "loading") return;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await getStrategyPositions(strategyId, backendToken ?? "");
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
  }, [strategyId, backendToken, sessionStatus, pollIntervalMs, refreshKey]);

  if (loading && !state) {
    return (
      <div data-testid="positions-skeleton" className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", className)}>
        {[0, 1].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-md border border-slate-200 bg-slate-50"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="positions-error"
        className={cn("rounded-md border border-rose-200 bg-rose-50 p-3 text-[12px] text-rose-700", className)}
      >
        Couldn't load positions. {error}
      </div>
    );
  }

  if (!state) return null;

  if (state.positions.length === 0) {
    return (
      <div
        data-testid="positions-empty"
        className={cn("rounded-md border border-slate-200 bg-slate-50 p-6 text-center text-[12px] text-slate-500", className)}
      >
        No open positions yet. The monitor cron will open positions as
        your rules trigger.
      </div>
    );
  }

  return (
    <div data-testid="positions-grid" className={cn(className)}>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Positions · {state.open_count} open · {state.closed_count} closed
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {state.positions.map((pos) => (
          <PositionCard key={pos.id} pos={pos} />
        ))}
      </div>
    </div>
  );
}

function PositionCard({ pos }: { pos: PositionView }) {
  const pct = pos.pct_change_from_entry;
  const pctColor =
    pct === null
      ? "text-slate-400"
      : pct >= 0
        ? "text-emerald-600"
        : "text-rose-600";
  const pctDisplay =
    pct === null ? "—" : `${pct >= 0 ? "+" : ""}${(pct * 100).toFixed(2)}%`;

  return (
    <div
      data-testid={`position-card-${pos.symbol}`}
      className={cn(
        "rounded-md border bg-white p-3",
        pos.is_open ? "border-emerald-200" : "border-slate-200 opacity-75",
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-bold text-slate-900">{pos.symbol}</p>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
            pos.is_open
              ? "bg-emerald-50 text-emerald-700"
              : "bg-slate-100 text-slate-500",
          )}
        >
          {pos.is_open ? "Open" : "Closed"}
        </span>
      </div>
      <table className="w-full text-[12px]">
        <tbody>
          <tr>
            <td className="text-slate-500">Entry</td>
            <td className="text-right font-semibold">
              ${pos.entry_price.toFixed(2)}
            </td>
          </tr>
          <tr>
            <td className="text-slate-500">Current</td>
            <td className={cn("text-right font-semibold", pctColor)}>
              {pos.latest_price !== null
                ? `$${pos.latest_price.toFixed(2)}`
                : "—"}{" "}
              ({pctDisplay})
            </td>
          </tr>
          <tr>
            <td className="text-slate-500">Shares</td>
            <td className="text-right font-semibold">
              {pos.shares_remaining.toFixed(4)} / {pos.shares_initial.toFixed(4)}
            </td>
          </tr>
          {!pos.is_open && pos.final_pnl !== null && (
            <tr>
              <td className="text-slate-500">Final P&L</td>
              <td
                className={cn(
                  "text-right font-semibold",
                  pos.final_pnl >= 0 ? "text-emerald-600" : "text-rose-600",
                )}
              >
                {pos.final_pnl >= 0 ? "+" : ""}${pos.final_pnl.toFixed(2)}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {pos.trade_log.length > 1 && (
        <div className="mt-2 border-t border-slate-100 pt-2">
          <p className="text-[10px] uppercase tracking-wider text-slate-400">
            Events
          </p>
          <ul className="mt-1 space-y-0.5 text-[11px]">
            {pos.trade_log.slice(-3).map((event, i) => (
              <li key={i} className="text-slate-600">
                · {String(event.event ?? "—")}
                {event.tier_label ? ` (${String(event.tier_label)})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
