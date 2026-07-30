"use client";

/**
 * <StrategyDraftSheet> — PRD-26 review surface for a promoted screen.
 *
 * Shows exactly what promote decided, and is explicit about what it could NOT
 * decide:
 *   - which KB template seeded the thresholds (and how strong the match was)
 *   - the seeded entry/exit values per primitive
 *   - the calculated stop/target ladder, with the natr reading it came from
 *   - **when the ladder can't be calculated, it says so and asks the user** —
 *     it never shows a fabricated exit
 *   - which primitives the KB has no exit for at all (entry-only)
 *   - which matched name will be backtested (the engine's custom_build branch
 *     is single-symbol; multi-symbol is a documented engine follow-up)
 */

import { useMemo } from "react";
import { AlertTriangle, ArrowRight, X } from "lucide-react";

import type { PromoteDraft } from "@/lib/flows/promote-to-strategy";
import { cn } from "@/lib/utils";

function pct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function humanizeThresholdKey(key: string): string {
  return key.replace(/_/g, " ");
}

export function StrategyDraftSheet({
  draft,
  candidates,
  onSymbolChange,
  onRunBacktest,
  onClose,
  busy = false,
}: {
  draft: PromoteDraft;
  /** Matched names the user can pick from (ranked order). */
  candidates: string[];
  onSymbolChange: (symbol: string) => void;
  onRunBacktest: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  const seededEntries = useMemo(
    () => Object.entries(draft.seededThresholds),
    [draft.seededThresholds],
  );

  return (
    <div
      data-testid="strategy-draft-sheet"
      className="rounded-xl border border-primary/40 bg-white shadow-sm"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h3 className="text-base font-semibold text-foreground">
            Promote to strategy
          </h3>
          <p className="text-xs text-muted-foreground">
            Review what we filled in, then backtest it.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* Seeding provenance */}
        <section>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Seeded from
          </h4>
          {draft.seededFromTemplate ? (
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded border border-border bg-muted/50 px-2 py-0.5 text-xs text-foreground">
                {draft.seededFromTemplate}
              </code>
              {draft.similarity !== null && (
                <span className="text-[11px] text-muted-foreground">
                  {Math.round(draft.similarity * 100)}% category match
                </span>
              )}
            </div>
          ) : (
            <p data-testid="draft-no-template" className="text-xs text-muted-foreground">
              No template matched — your screen&rsquo;s own rules are used as-is.
            </p>
          )}
        </section>

        {/* Seeded thresholds */}
        {seededEntries.length > 0 && (
          <section data-testid="draft-seeded-thresholds">
            <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Entry / exit
            </h4>
            <ul className="space-y-1">
              {seededEntries.map(([primitiveId, thresholds]) => (
                <li key={primitiveId} className="flex flex-wrap items-center gap-x-2 text-xs">
                  <span className="font-medium text-foreground">{primitiveId}</span>
                  <span className="text-muted-foreground">
                    {Object.entries(thresholds)
                      .map(([k, v]) => `${humanizeThresholdKey(k)} ${v}`)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* The exit — calculated, or explicitly absent */}
        <section>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Exit
          </h4>
          {draft.exitLadder ? (
            <div data-testid="draft-exit-ladder">
              <ul className="space-y-1">
                {draft.exitLadder.map((tier, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">{tier.label}</span>
                    <span
                      className={cn(
                        "font-medium tabular-nums",
                        tier.trigger_pct < 0 ? "text-rose-600" : "text-emerald-600",
                      )}
                    >
                      {pct(tier.trigger_pct)}
                      {tier.action === "sell_fraction" && tier.fraction
                        ? ` · sell ${Math.round(tier.fraction * 100)}%`
                        : ""}
                    </span>
                  </li>
                ))}
              </ul>
              {draft.natrPct !== null && (
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Scaled to {draft.symbol}&rsquo;s recent volatility (ATR{" "}
                  {draft.natrPct.toFixed(2)}% of price) — derived, not optimised.
                </p>
              )}
            </div>
          ) : (
            <div
              data-testid="draft-no-exit"
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
              <p className="text-[12px] text-amber-800">
                <span className="font-medium">No calculated exit.</span> We
                couldn&rsquo;t measure {draft.symbol}&rsquo;s volatility, so
                you&rsquo;ll need to set an exit yourself in the composer before
                relying on this.
              </p>
            </div>
          )}
          {draft.entryOnlyPrimitives.length > 0 && (
            <p
              data-testid="draft-entry-only"
              className="mt-1.5 text-[11px] text-muted-foreground"
            >
              {draft.entryOnlyPrimitives.join(", ")}{" "}
              {draft.entryOnlyPrimitives.length === 1 ? "is an entry" : "are entry"}{" "}
              condition{draft.entryOnlyPrimitives.length === 1 ? "" : "s"} only —
              {draft.entryOnlyPrimitives.length === 1 ? " it says" : " they say"}{" "}
              nothing about when to exit.
            </p>
          )}
        </section>

        {/* Symbol — the engine's custom_build branch is single-symbol */}
        <section>
          <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Backtest on
          </h4>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={draft.symbol}
              onChange={(e) => onSymbolChange(e.target.value)}
              data-testid="draft-symbol-select"
              aria-label="Symbol to backtest"
              className="rounded-lg border border-border bg-white px-2.5 py-1.5 text-xs text-foreground"
            >
              {candidates.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              one name at a time
            </span>
          </div>
        </section>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-border px-5 py-4">
        <button
          type="button"
          onClick={onRunBacktest}
          disabled={busy}
          data-testid="draft-run-backtest"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? "Preparing…" : "Run backtest"}
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
