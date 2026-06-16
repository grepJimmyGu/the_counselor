/**
 * PRD-23b — ScreenResults.
 *
 * The progressive ranked basket for a standing-universe screen. Never a blank
 * page (Principle 4):
 *   1. POST /api/screen/scan (allow_anonymous) → render the matched basket
 *      immediately: ticker + satisfied-reading chips + skeleton metric.
 *   2. POST /api/screen/rank (sign-in-gated) → fill total-return/Sharpe and
 *      re-sort. Anonymous users see the basket + a "sign in to rank" CTA.
 * "as of <date>" byline (date-visibility invariant). Row click drills into the
 * existing single-asset backtest in the Workspace (reused — no new surface).
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { screenRank, screenScan } from "@/lib/api";
import type {
  RankedSymbol,
  ScreenScanResponse,
  StrategyJson,
} from "@/lib/contracts";
import type { CustomBuildModeContext } from "@/lib/flows/custom-build-mode-context";
import {
  buildCustomBuildStrategyJson,
  buildScreenRules,
} from "@/lib/flows/custom-build-strategy-json";
import type { FlowStepProps } from "@/lib/flows/types";
import { cn } from "@/lib/utils";

function pct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

export function ScreenResults({
  context,
  updateContext,
}: FlowStepProps<CustomBuildModeContext>) {
  const router = useRouter();
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  const [scan, setScan] = useState<ScreenScanResponse | null>(null);
  const [ranked, setRanked] = useState<Record<string, RankedSymbol> | null>(null);
  const [loadingScan, setLoadingScan] = useState(true);
  const [loadingRank, setLoadingRank] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rules = useMemo(() => buildScreenRules(context.rules), [context.rules]);
  const rankGated = sessionStatus === "unauthenticated" || !backendToken;

  // Step 1 — scan (fast, anonymous-OK): the matched basket.
  useEffect(() => {
    if (sessionStatus === "loading") return;
    let cancelled = false;
    setLoadingScan(true);
    screenScan({ universe_id: context.universe_id, rules }, { backendToken })
      .then((resp) => {
        if (!cancelled) {
          setScan(resp);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Scan failed.");
      })
      .finally(() => {
        if (!cancelled) setLoadingScan(false);
      });
    return () => {
      cancelled = true;
    };
  }, [context.universe_id, rules, backendToken, sessionStatus]);

  // Step 2 — rank (slower, sign-in-gated): fill the return metrics + re-sort.
  useEffect(() => {
    if (sessionStatus === "loading" || rankGated || !scan || scan.matched.length === 0) {
      return;
    }
    let cancelled = false;
    setLoadingRank(true);
    const strategy = buildCustomBuildStrategyJson(context, {
      // The rank backtests each survivor with universe swapped per-symbol, so
      // this placeholder symbol is overridden server-side.
      symbol: scan.matched[0] ?? "SPY",
    }) as StrategyJson;
    screenRank(
      { universe_id: context.universe_id, rules, strategy, top_k: 50 },
      { backendToken: backendToken as string },
    )
      .then((resp) => {
        if (cancelled) return;
        const byId: Record<string, RankedSymbol> = {};
        for (const r of resp.ranked) byId[r.symbol] = r;
        setRanked(byId);
        updateContext({ screenRankResult: resp });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Ranking failed.");
      })
      .finally(() => {
        if (!cancelled) setLoadingRank(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan, rankGated, sessionStatus]);

  // Basket order: by total return once ranked, else scan order.
  const ordered = useMemo(() => {
    const matched = scan?.matched ?? [];
    if (!ranked) return matched;
    return [...matched].sort(
      (a, b) => (ranked[b]?.total_return ?? -Infinity) - (ranked[a]?.total_return ?? -Infinity),
    );
  }, [scan, ranked]);

  const drillIn = useCallback(
    (symbol: string) => {
      try {
        const strategyJson = buildCustomBuildStrategyJson(context, { symbol });
        sessionStorage.setItem("pendingStrategy", JSON.stringify(strategyJson));
        router.push("/workspace?fromBuilder=true&autorun=true");
      } catch {
        // Non-fatal — the row just won't navigate.
      }
    },
    [context, router],
  );

  if (loadingScan) {
    return (
      <div data-testid="screen-results-loading" className="flex h-48 items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-slate-700" />
      </div>
    );
  }

  if (error && !scan) {
    return (
      <div data-testid="screen-results-error" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        {error}
      </div>
    );
  }

  const matchedCount = scan?.matched_count ?? 0;

  return (
    <section data-testid="screen-results" className="flex flex-col gap-4">
      <header className="flex flex-col gap-0.5">
        {scan?.as_of_date && (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            as of {scan.as_of_date}
          </p>
        )}
        <h2 className="text-lg font-semibold text-slate-900">
          {matchedCount} {matchedCount === 1 ? "name" : "names"} match
          <span className="text-slate-400"> of {scan?.universe_size ?? 0}</span>
        </h2>
        {loadingRank && (
          <p className="text-[12px] text-slate-500">Backtesting the matched basket…</p>
        )}
        {/* Rank is an enrichment overlay — a rank failure (timeout/5xx) must
            not blank the basket. Surface it inline; the matched names below
            still render and still drill in. */}
        {error && scan && (
          <p
            data-testid="screen-results-rank-error"
            className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[12px] text-amber-700"
          >
            Couldn&apos;t rank by return ({error}). The matched names are shown below.
          </p>
        )}
      </header>

      {matchedCount === 0 ? (
        <p data-testid="screen-results-empty" className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-[13px] text-slate-500">
          Nothing matches this reading today. Loosen a rule and try again.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {ordered.map((symbol) => {
            const r = ranked?.[symbol];
            return (
              <li key={symbol}>
                <button
                  type="button"
                  data-testid={`screen-result-row-${symbol}`}
                  onClick={() => drillIn(symbol)}
                  className="flex w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="font-semibold text-slate-900">{symbol}</span>
                    <div className="flex flex-wrap gap-1">
                      {(scan?.readings[symbol] ?? []).map((reading, i) => (
                        <span
                          key={i}
                          className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600"
                        >
                          {reading}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    {r ? (
                      <>
                        <div
                          className={cn(
                            "text-sm font-semibold tabular-nums",
                            r.total_return >= 0 ? "text-emerald-600" : "text-rose-600",
                          )}
                        >
                          {pct(r.total_return)}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          Sharpe {r.sharpe_ratio == null ? "—" : r.sharpe_ratio.toFixed(2)}
                        </div>
                      </>
                    ) : rankGated ? (
                      <span className="text-[11px] text-slate-400">sign in to rank</span>
                    ) : error ? (
                      // Rank failed — stop the perpetual skeleton; the banner
                      // above explains why.
                      <span className="text-[11px] text-slate-300">—</span>
                    ) : (
                      <div className="h-4 w-12 animate-pulse rounded bg-slate-100" />
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {rankGated && matchedCount > 0 && (
        <p data-testid="screen-results-rank-gate" className="rounded-md bg-slate-50 px-4 py-2 text-[12px] text-slate-600">
          Sign in to rank these {matchedCount} names by backtested return.
        </p>
      )}

      {matchedCount > 0 && (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            data-testid="screen-results-save"
            disabled
            title="Coming soon (PRD-23c)"
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-400"
          >
            Save + track this screen →
          </button>
        </div>
      )}
    </section>
  );
}
