/**
 * /account/strategies/[id] — a single saved strategy's live dashboard.
 *
 * Keyed on the SavedStrategy UUID (the dashboard endpoints are owner-only
 * on this id), so no slug juggling. Renders the strategy title + the
 * ActiveExecutionDashboard. For a daily (non-active-execution) strategy,
 * shows a note instead of the dashboard.
 *
 * Trap #19: reads `backendToken` off `useSession()`.
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { ArrowLeft, Loader2 } from "lucide-react";

import { ActiveExecutionDashboard } from "@/components/active-execution/active-execution-dashboard";
import { listSavedStrategies } from "@/lib/api";
import type { UserSavedStrategy } from "@/lib/contracts";

export default function SavedStrategyDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [rows, setRows] = useState<UserSavedStrategy[] | null>(null);

  useEffect(() => {
    if (status === "loading" || !backendToken) return;
    listSavedStrategies(backendToken)
      .then(setRows)
      .catch(() => setRows([]));
  }, [status, backendToken]);

  const strategy = useMemo(
    () => rows?.find((s) => s.id === id) ?? null,
    [rows, id],
  );

  // GATED ON THE EXIT LADDER, NOT THE BAR RESOLUTION (2026-08-21).
  //
  // This read `bar_resolution !== "daily"` until now — the same condition
  // #331 replaced on the public `/strategies/[slug]` page, left behind here.
  // It matters more on this page than that one: `SavedStrategiesTile` sends
  // EVERY SignalCard click to `/account/strategies/{id}`, so home's own
  // strategy tile routed every user to the one page that hides the
  // dashboard for daily strategies — which, since #327, is the path the
  // product actually runs on.
  //
  // The backend's real requirement is an exit ladder: `declare_position`
  // 400s without one because there is nothing to monitor a position
  // against. The UI now asks the same question the API does.
  const ladder = useMemo(() => {
    const json = (strategy?.strategy_json ?? {}) as {
      risk_management?: { exit_ladder?: unknown[] };
    };
    return json.risk_management?.exit_ladder ?? [];
  }, [strategy]);
  const isActive = ladder.length > 0;

  const barResolution = useMemo(() => {
    const json = (strategy?.strategy_json ?? {}) as { bar_resolution?: string };
    return json.bar_resolution ?? "daily";
  }, [strategy]);

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-10">
      <Link
        href={"/account/strategies" as Route}
        className="mb-4 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> My strategies
      </Link>

      {status === "loading" || rows === null ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : strategy === null ? (
        <p
          data-testid="strategy-not-found"
          className="text-sm text-muted-foreground"
        >
          Strategy not found, or you don&rsquo;t have access to it.
        </p>
      ) : (
        <>
          <header className="mb-6">
            <h1 className="font-heading text-2xl font-bold">{strategy.title}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Live execution dashboard
            </p>
          </header>
          {isActive ? (
            <ActiveExecutionDashboard
              strategyId={strategy.id}
              barResolution={barResolution}
            />
          ) : (
            <p
              data-testid="not-active-execution"
              className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground"
            >
              This strategy has no exit rules, so there&rsquo;s nothing to
              monitor a position against. Add a stop (and any targets) when
              building, and you can track positions here.
            </p>
          )}
        </>
      )}
    </main>
  );
}
