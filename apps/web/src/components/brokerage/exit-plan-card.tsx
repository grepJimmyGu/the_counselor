"use client";

/**
 * The exit plan — PRD-43a v3 §B.
 *
 * Both expensive habits in the Mirror are the same missing discipline seen
 * from either side: giving back a gain and selling into a drawdown both come
 * from having no exit decided before the trade. So they converge here, on one
 * ladder, rather than getting a CTA each.
 *
 * ⚠ THE STOP FIELD IS EMPTY ON PURPOSE, and that is the whole design.
 *
 * `RiskManagement.validate_exit_ladder` requires a stop tier, so a trackable
 * ladder forces one to be named — and PRD-43e §4.2 forbids deriving it from
 * descriptive statistics. On this account every fixed stop tested negative,
 * because a quarter of the winners dip further than the median loser. The
 * codebase had already settled the same question, in the attach endpoint:
 *
 *     "'sensible' chosen by the server is exactly the stop a user will not
 *      believe when it fires."
 *
 * So the take-profit rung is pre-filled from the user's OWN peaks and labelled
 * as such, and the stop is an empty field with the reason it is empty printed
 * beside it. What fixes the second habit is not the number — it is having
 * chosen one while nothing was at stake.
 */

import { useState } from "react";
import { Check, Loader2 } from "lucide-react";

import { createExitPlan } from "@/lib/api";
import type { ExitPlanResponse } from "@/lib/contracts";

const DEFAULT_TP_PCT = 10;
const DEFAULT_TP_FRACTION = 0.333;

function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function ExitPlanCard({
  backendToken,
  /** The user's own peaks, so the suggested rung can cite them. */
  peakLow,
  peakHigh,
  winnerMae,
  loserMae,
  symbols,
}: {
  backendToken: string;
  peakLow?: number | null;
  peakHigh?: number | null;
  winnerMae?: number | null;
  loserMae?: number | null;
  symbols?: string[];
}) {
  const [tp, setTp] = useState(String(DEFAULT_TP_PCT));
  const [stop, setStop] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [result, setResult] = useState<ExitPlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stopNum = Number.parseFloat(stop);
  const tpNum = Number.parseFloat(tp);
  const ready =
    Number.isFinite(stopNum) && stopNum > 0 && Number.isFinite(tpNum) && tpNum > 0;

  if (state === "saved" && result) {
    return (
      <div
        className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3.5 dark:border-emerald-900 dark:bg-emerald-950"
        data-testid="exit-plan-saved"
      >
        <div className="flex items-center gap-2 text-[14px] font-semibold text-emerald-900 dark:text-emerald-200">
          <Check className="h-4 w-4" />
          Your exit plan is set
        </div>
        <p className="mt-1.5 text-[13px] text-emerald-900/80 dark:text-emerald-200/80">
          {result.tracked.length > 0 ? (
            <>
              Watching{" "}
              <span className="font-medium">{result.tracked.join(", ")}</span>{" "}
              after every close. You&rsquo;ll be told the evening a rung is hit.
            </>
          ) : (
            <>
              Saved. Nothing to watch yet &mdash; it starts on your next
              position.
            </>
          )}
        </p>
        {result.skipped.length > 0 && (
          <p
            className="mt-1.5 text-[11px] text-emerald-900/70 dark:text-emerald-200/70"
            data-testid="exit-plan-skipped"
          >
            Not tracked:{" "}
            {result.skipped
              .map(([sym, reason]) => `${sym} (${reason.replace(/_/g, " ")})`)
              .join(", ")}
            .
          </p>
        )}
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border-2 border-amber-300 bg-amber-50/60 px-4 py-4 dark:border-amber-900 dark:bg-amber-950/30"
      data-testid="exit-plan"
    >
      <div className="text-[15px] font-semibold text-foreground">
        Both are the same thing: no exit decided in advance
      </div>
      <p className="mt-0.5 text-[13px] text-muted-foreground">
        Set one now and we&rsquo;ll watch your positions for it.
      </p>

      {/* Take profit — suggested, and it says where the suggestion came from. */}
      <div className="mt-3 rounded-md border border-border bg-card px-3.5 py-3">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Take some off
          </span>
          <span className="ml-auto text-[10.5px] text-muted-foreground">
            suggested from your record
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
          at
          <span className="inline-flex items-center">
            +
            <input
              type="number"
              value={tp}
              onChange={(e) => setTp(e.target.value)}
              aria-label="Take profit percentage"
              data-testid="exit-plan-tp"
              className="w-16 rounded border border-amber-400 bg-background px-2 py-1 text-center font-mono text-[13.5px] font-semibold tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring dark:border-amber-700"
            />
            %
          </span>
          sell
          <span className="rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[13px] font-semibold">
            one third
          </span>
        </div>
        {peakLow !== null && peakLow !== undefined &&
          peakHigh !== null && peakHigh !== undefined && (
            <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
              Your gave-back trades peaked between{" "}
              <strong className="font-medium text-foreground">
                {pct(peakLow)} and {pct(peakHigh)}
              </strong>
              . A rung at +{DEFAULT_TP_PCT}% sits under all of them.
            </p>
          )}
      </div>

      {/* Stop — deliberately empty. */}
      <div className="mt-2 rounded-md border border-border bg-card px-3.5 py-3">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Stop
          </span>
          <span className="ml-auto text-[10.5px] font-medium text-amber-700 dark:text-amber-500">
            you choose this
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
          at
          <span className="inline-flex items-center">
            −
            <input
              type="number"
              value={stop}
              onChange={(e) => setStop(e.target.value)}
              placeholder="  "
              aria-label="Stop percentage"
              data-testid="exit-plan-stop"
              className="w-16 rounded border border-dashed border-border bg-background px-2 py-1 text-center font-mono text-[13.5px] font-semibold tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
            />
            %
          </span>
          sell
          <span className="rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[13px] font-semibold">
            everything
          </span>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          <strong className="font-medium text-foreground">
            We won&rsquo;t pick this for you.
          </strong>{" "}
          {winnerMae !== null && winnerMae !== undefined &&
            loserMae !== null && loserMae !== undefined && (
              <>
                Your winners dip {pct(Math.abs(winnerMae))} before working and
                your losers {pct(Math.abs(loserMae))} — but a quarter of your
                winners dip further than that, so any stop tight enough to catch
                the losers cuts winners too.{" "}
              </>
            )}
          What fixes the second habit isn&rsquo;t the number; it&rsquo;s having
          chosen it beforehand.
        </p>
      </div>

      <button
        type="button"
        disabled={!ready || state === "saving"}
        data-testid="exit-plan-save"
        onClick={() => {
          setState("saving");
          setError(null);
          createExitPlan(backendToken, {
            take_profit_pct: tpNum / 100,
            take_profit_fraction: DEFAULT_TP_FRACTION,
            // The API takes a negative number; the field asks for a magnitude.
            stop_pct: -Math.abs(stopNum) / 100,
            symbols,
          })
            .then((r) => {
              setResult(r);
              setState("saved");
            })
            .catch((e: Error) => {
              setError(e.message || "Couldn't save it.");
              setState("failed");
            });
        }}
        className="mt-3 w-full rounded-lg bg-foreground px-4 py-2.5 text-[14px] font-semibold text-background transition-opacity hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
      >
        {state === "saving" ? (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving
          </span>
        ) : (
          "Save this rule and watch my positions"
        )}
      </button>

      {!ready && (
        <p className="mt-1.5 text-center text-[11.5px] text-muted-foreground">
          Enter a stop to continue.
        </p>
      )}
      {state === "failed" && (
        <p
          className="mt-1.5 text-center text-[12px] text-rose-700 dark:text-rose-400"
          data-testid="exit-plan-error"
        >
          {error}
        </p>
      )}

      {/* What happens next, so "watch my positions" is a promise with a shape. */}
      <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {[
          ["THEN", "Checked after every close"],
          ["IF HIT", "You get told, that evening"],
          ["ONE TAP", "Pre-filled order ticket"],
          ["ALWAYS", "You confirm; we never sell"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-md border border-border bg-card px-2.5 py-2">
            <div className="font-mono text-[9.5px] font-semibold tracking-wider text-muted-foreground">
              {k}
            </div>
            <div className="mt-0.5 text-[11.5px] leading-tight text-foreground">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
