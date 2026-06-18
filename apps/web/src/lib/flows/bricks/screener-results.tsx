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
import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

import { saveScreen, screenRank, screenScan } from "@/lib/api";
import type {
  RankedSymbol,
  ScreenSaveResponse,
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

function deriveScreenTitle(universeId: string): string {
  if (universeId === "sp500") return "S&P 500 screen";
  if (universeId.startsWith("sector_")) {
    return `${universeId.slice("sector_".length)} sector screen`;
  }
  return "My market screen";
}

export function ScreenResults({
  context,
  updateContext,
  back,
}: FlowStepProps<CustomBuildModeContext>) {
  const router = useRouter();
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  const [scan, setScan] = useState<ScreenScanResponse | null>(null);
  const [ranked, setRanked] = useState<Record<string, RankedSymbol> | null>(null);
  const [loadingScan, setLoadingScan] = useState(true);
  const [loadingRank, setLoadingRank] = useState(false);
  // `error` is the SCAN error; `rankError` is the optional rank-enrichment
  // error — kept distinct so a scan failure isn't mislabeled "couldn't rank".
  const [error, setError] = useState<string | null>(null);
  const [rankError, setRankError] = useState<string | null>(null);

  const rules = useMemo(() => buildScreenRules(context.rules), [context.rules]);
  const rankGated = sessionStatus === "unauthenticated" || !backendToken;

  // PRD-23c — save + track this standing screen.
  const screenTitle = useMemo(
    () => deriveScreenTitle(context.universe_id),
    [context.universe_id],
  );
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [savedScreen, setSavedScreen] = useState<ScreenSaveResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(async () => {
    if (!backendToken) return;
    setSaveState("saving");
    setSaveError(null);
    try {
      const resp = await saveScreen(
        { title: screenTitle, universe_id: context.universe_id, rules },
        { backendToken },
      );
      setSavedScreen(resp);
      setSaveState("saved");
    } catch (e: unknown) {
      // A 402 (Scout) already pops the global upgrade modal via fetchApi; show
      // a brief inline note for any failure so the click never feels dead.
      setSaveState("idle");
      setSaveError(e instanceof Error ? e.message : "Couldn't save this screen.");
    }
  }, [backendToken, screenTitle, context.universe_id, rules]);

  // Step 1 — scan (fast, anonymous-OK): the matched basket.
  useEffect(() => {
    if (sessionStatus === "loading") return;
    let cancelled = false;
    setLoadingScan(true);
    setError(null); // clear any stale scan error before a re-scan
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
    setRankError(null); // clear any stale rank error before a re-rank
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
        if (!cancelled) setRankError(e instanceof Error ? e.message : "Ranking failed.");
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
      <header className="flex flex-col gap-1">
        {back && (
          <button
            type="button"
            onClick={back}
            data-testid="screen-results-edit"
            className="-ml-1 mb-0.5 inline-flex w-fit items-center gap-1 text-[12px] font-medium text-slate-500 hover:text-slate-800"
          >
            ← Edit reading
          </button>
        )}
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
        {/* A re-scan failure (stale basket still shown) — distinct from a rank
            failure so the message attributes the right step. */}
        {error && scan && (
          <p
            data-testid="screen-results-scan-error"
            className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[12px] text-amber-700"
          >
            Couldn&apos;t refresh ({error}) — showing the last results.
          </p>
        )}
        {/* Rank is an enrichment overlay — a rank failure (timeout/5xx) must
            not blank the basket. Surface it inline; the matched names below
            still render and still drill in. */}
        {rankError && scan && (
          <p
            data-testid="screen-results-rank-error"
            className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[12px] text-amber-700"
          >
            Couldn&apos;t rank by return ({rankError}). The matched names are shown below.
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
                    ) : rankError ? (
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
        <div className="flex flex-col gap-2">
          {saveState === "saved" && savedScreen ? (
            <div
              data-testid="screen-results-saved"
              className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
            >
              <p className="font-semibold">✓ Tracking “{screenTitle}”.</p>
              <p className="mt-1 text-[13px] text-emerald-800">
                Now watching {savedScreen.basket.length} names. We’ll alert you
                when a new name enters this screen.
              </p>
              <Link
                href={`/screens/${savedScreen.saved_strategy_id}` as Route}
                data-testid="screen-results-view-link"
                className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-emerald-900 underline underline-offset-2 hover:text-emerald-700"
              >
                View screen →
              </Link>
            </div>
          ) : rankGated ? (
            <p
              data-testid="screen-results-save-gate"
              className="rounded-md bg-slate-50 px-4 py-2 text-[12px] text-slate-600"
            >
              Sign in (Strategist+) to save + track this screen for new entrants.
            </p>
          ) : (
            <button
              type="button"
              data-testid="screen-results-save"
              onClick={handleSave}
              disabled={saveState === "saving"}
              className="self-start rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:border-slate-400 disabled:opacity-50"
            >
              {saveState === "saving" ? "Saving…" : "Save + track this screen →"}
            </button>
          )}
          {saveError && (
            <p
              data-testid="screen-results-save-error"
              className="text-[12px] text-rose-600"
            >
              {saveError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
