/**
 * PRD-23b — ScreenMatchCount.
 *
 * The live match-count funnel: as the user tunes a reading, a debounced
 * POST /api/screen/count reports "N of <universe> match today". This is the
 * discovery loop's centerpiece for standing universes (sp500 / sector).
 *
 * Reads `backendToken` off useSession (trap #19) and waits for the session to
 * resolve before firing. scan/count are allow_anonymous, so an anonymous user
 * still gets a count; signed-in users pass their token for their tier.
 */
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { screenCount } from "@/lib/api";
import type { ScreenCountResponse } from "@/lib/contracts";
import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import { buildScreenRules } from "@/lib/flows/custom-build-strategy-json";
import { isStandingUniverse } from "./universe-selector";

interface Props {
  universeId: string;
  rules: BuildRule[];
  /** Debounce window; default 250ms. */
  debounceMs?: number;
}

export function ScreenMatchCount({ universeId, rules, debounceMs = 250 }: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  const [result, setResult] = useState<ScreenCountResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only standing universes (sp500/sector) have a meaningful funnel; entered
  // tiers are trivially N/N and skip the round-trip.
  const standing = isStandingUniverse(universeId);

  useEffect(() => {
    if (sessionStatus === "loading") return;
    if (!standing || rules.length === 0) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(() => {
      screenCount(
        { universe_id: universeId, rules: buildScreenRules(rules) },
        { backendToken },
      )
        .then((resp) => {
          if (cancelled) return;
          setResult(resp);
          setError(null);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          setError(e instanceof Error ? e.message : "Couldn't count matches.");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, debounceMs);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // Re-count whenever the reading or universe changes. rules identity changes
    // on every edit (the canvas rebuilds the array), which is the trigger.
  }, [universeId, rules, standing, backendToken, sessionStatus, debounceMs]);

  if (!standing) return null;

  return (
    <div
      data-testid="screen-match-count"
      className="rounded-lg border border-slate-200 bg-white px-4 py-3"
    >
      {rules.length === 0 ? (
        <p className="text-[13px] text-slate-500">
          Add a rule to see how many names match.
        </p>
      ) : error ? (
        <p data-testid="screen-match-count-error" className="text-[13px] text-rose-700">
          {error}
        </p>
      ) : result ? (
        <div className="flex flex-col gap-1">
          <p className="text-[13px] text-slate-700">
            <span data-testid="screen-match-count-value" className="text-lg font-semibold tabular-nums text-slate-900">
              {result.matched_count}
            </span>{" "}
            of {result.universe_size} match
            {result.as_of_date ? (
              <span className="text-slate-400"> · as of {result.as_of_date}</span>
            ) : null}
            {loading ? <span className="text-slate-400"> · updating…</span> : null}
          </p>
          {result.unsupported_primitives.length > 0 && (
            <p className="text-[11px] text-amber-700">
              Not screenable yet: {result.unsupported_primitives.join(", ")}
            </p>
          )}
          {result.default_param_primitives.length > 0 && (
            <p className="text-[11px] text-slate-500">
              Screened at default periods: {result.default_param_primitives.join(", ")}{" "}
              (the backtest uses your exact params)
            </p>
          )}
        </div>
      ) : (
        <p className="text-[13px] text-slate-400">Counting matches…</p>
      )}
    </div>
  );
}
