"use client";

/**
 * <PromoteToStrategyButton> — PRD-26 entry point on any screen-results surface.
 *
 * Owns the promote lifecycle: build the draft (KB match + calculated ladder),
 * show <StrategyDraftSheet> for review, and on confirm hand the strategy to the
 * flow so the existing backtest → review → save chain takes over.
 *
 * A brick: it takes the screen's context + matched names and reports the
 * finished draft upward. It does not know about the flow runtime.
 */

import { useCallback, useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";

import { buildPromoteDraft, type PromoteDraft } from "@/lib/flows/promote-to-strategy";
import type { CustomBuildModeContext } from "@/lib/flows/custom-build-mode-context";

import { StrategyDraftSheet } from "./strategy-draft-sheet";

const MAX_CANDIDATES = 25;

export function PromoteToStrategyButton({
  context,
  matched,
  onConfirm,
  label = "Promote to strategy",
}: {
  context: CustomBuildModeContext;
  /** Matched names in ranked order — the first is the default pick. */
  matched: string[];
  /** Called with the reviewed draft; the caller advances the flow. */
  onConfirm: (draft: PromoteDraft) => void;
  label?: string;
}) {
  const [draft, setDraft] = useState<PromoteDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const candidates = matched.slice(0, MAX_CANDIDATES);

  const build = useCallback(
    async (symbol: string) => {
      setLoading(true);
      setError(null);
      try {
        setDraft(await buildPromoteDraft(context, symbol));
      } catch (e: unknown) {
        // buildPromoteDraft swallows network failures itself, so reaching here
        // means the strategy couldn't be assembled at all (e.g. a rule is
        // incomplete) — show why rather than a dead button.
        setError(e instanceof Error ? e.message : "Couldn't prepare a strategy.");
      } finally {
        setLoading(false);
      }
    },
    [context],
  );

  if (candidates.length === 0) return null;

  if (draft) {
    return (
      <StrategyDraftSheet
        draft={draft}
        candidates={candidates}
        busy={loading}
        onSymbolChange={(s) => void build(s)}
        onRunBacktest={() => onConfirm(draft)}
        onClose={() => {
          setDraft(null);
          setError(null);
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => void build(candidates[0])}
        disabled={loading}
        data-testid="promote-to-strategy"
        className="inline-flex w-fit items-center gap-1.5 rounded-lg border border-primary bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {loading ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Preparing…
          </>
        ) : (
          <>
            {label}
            <ArrowRight className="h-3.5 w-3.5" />
          </>
        )}
      </button>
      {error && (
        <p data-testid="promote-error" className="text-[12px] text-rose-600">
          {error}
        </p>
      )}
    </div>
  );
}
