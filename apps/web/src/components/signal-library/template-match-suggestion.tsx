/**
 * PRD-16a-4 — TemplateMatchSuggestion.
 *
 * Wraps the KB lookup at `POST /api/signal-combos/match-templates`.
 * Given the user's currently-selected primitive IDs, renders the top-N
 * suggested templates with their Jaccard score + per-primitive
 * threshold defaults.
 *
 * Used in the composer's right rail. The "Use these defaults" callback
 * (`onPickTemplate`) is consumed by PRD-16b's composer canvas to
 * pre-fill the user's primitive parameters.
 *
 * Re-fetches on `primitiveIds` change. Debounces with a 250ms delay so
 * rapid clicks in the catalog browser don't spam the endpoint.
 */
"use client";

import { useEffect, useState } from "react";

import { matchSignalCombosToTemplates } from "@/lib/api";
import type {
  MatchTemplatesResponse,
  TemplateMatch,
} from "@/lib/contracts";
import { SIGNAL_CATEGORY_LABEL } from "@/lib/contracts";
import { cn } from "@/lib/utils";

interface Props {
  primitiveIds: string[];
  /** Capped at 3 by the matcher's default; the prop lets future surfaces
   *  request more if needed. */
  topN?: number;
  /** Optional — composer pre-fills user's primitives with the template's
   *  thresholds when invoked. */
  onPickTemplate?: (match: TemplateMatch) => void;
  className?: string;
}

const DEBOUNCE_MS = 250;

export function TemplateMatchSuggestion({
  primitiveIds,
  topN = 3,
  onPickTemplate,
  className,
}: Props) {
  const [data, setData] = useState<MatchTemplatesResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (primitiveIds.length === 0) {
      setData(null);
      return;
    }
    const handle = setTimeout(() => {
      setLoading(true);
      matchSignalCombosToTemplates({ primitive_ids: primitiveIds, top_n: topN })
        .then(setData)
        .catch(() => setData({ matches: [] }))
        .finally(() => setLoading(false));
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // Stable-stringify so a same-shape array doesn't re-fetch.
  }, [JSON.stringify(primitiveIds), topN]);

  // Anonymous / empty state.
  if (primitiveIds.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4",
          className,
        )}
      >
        <p className="text-[12px] text-slate-500">
          Pick primitives on the left and we'll suggest matching templates.
        </p>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div
        data-testid="template-match-skeleton"
        className={cn(
          "h-32 w-full animate-pulse rounded-lg bg-slate-100",
          className,
        )}
      />
    );
  }

  const matches = data?.matches ?? [];
  if (matches.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border border-slate-200 bg-white p-4",
          className,
        )}
      >
        <p className="text-[12px] text-slate-500">
          No template matches for this combination yet — your custom build is
          off the beaten path.
        </p>
      </div>
    );
  }

  return (
    <section
      data-testid="template-match-suggestion"
      className={cn("flex flex-col gap-2", className)}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Closest templates
      </p>
      {matches.map((match) => (
        <article
          key={match.template_id}
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
          data-testid={`template-match-${match.template_id}`}
        >
          <header className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">
              {humanizeTemplateId(match.template_id)}
            </h3>
            <span className="text-[11px] font-medium text-slate-500">
              {(match.similarity * 100).toFixed(0)}% match
            </span>
          </header>
          {match.shared_categories.length > 0 ? (
            <p className="mt-1 text-[12px] text-slate-500">
              Shared: {match.shared_categories.map((c) => SIGNAL_CATEGORY_LABEL[c]).join(" · ")}
            </p>
          ) : null}
          {Object.keys(match.thresholds_for_user_primitives).length > 0 ? (
            <dl className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-600">
              {Object.entries(match.thresholds_for_user_primitives).map(
                ([primitiveId, thresholds]) => (
                  <div
                    key={primitiveId}
                    className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1"
                  >
                    <dt className="font-medium text-slate-900">{primitiveId}</dt>
                    <dd>
                      {Object.entries(thresholds)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ")}
                    </dd>
                  </div>
                ),
              )}
            </dl>
          ) : null}
          {onPickTemplate ? (
            <button
              type="button"
              onClick={() => onPickTemplate(match)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50"
            >
              Use these defaults →
            </button>
          ) : null}
        </article>
      ))}
    </section>
  );
}

function humanizeTemplateId(id: string): string {
  // "bollinger-mean-reversion" → "Bollinger Mean Reversion"
  return id
    .split("-")
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(" ");
}
