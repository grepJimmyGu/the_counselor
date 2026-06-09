/**
 * PRD-16a-4 — SignalPrimitiveCard.
 *
 * One uniform card for any catalog primitive. Renders:
 *   - Name + family chip
 *   - Description (1-line, truncated)
 *   - Category badge + evidence-tier badge
 *
 * Optional click handler so the composer (PRD-16b) can drop the
 * primitive's ID into the user's selection.
 */
"use client";

import type {
  SignalCategory,
  SignalPrimitive,
} from "@/lib/contracts";
import { SIGNAL_CATEGORY_LABEL } from "@/lib/contracts";
import { cn } from "@/lib/utils";

interface Props {
  primitive: SignalPrimitive;
  onClick?: (primitive: SignalPrimitive) => void;
  /** Visual selection state — used by the composer to mark already-picked
   *  primitives. The card stays clickable (allows toggle-off). */
  selected?: boolean;
  className?: string;
}

const CATEGORY_TINT: Record<SignalCategory, string> = {
  trend: "bg-sky-50 text-sky-700 border-sky-200",
  mean_reversion: "bg-violet-50 text-violet-700 border-violet-200",
  momentum: "bg-emerald-50 text-emerald-700 border-emerald-200",
  volume: "bg-amber-50 text-amber-700 border-amber-200",
  volatility: "bg-rose-50 text-rose-700 border-rose-200",
  fundamental: "bg-slate-100 text-slate-700 border-slate-300",
  sentiment: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  cross_sectional: "bg-cyan-50 text-cyan-700 border-cyan-200",
};

const TIER_LABEL: Record<"A" | "B" | "C", string> = {
  A: "Well established",
  B: "Supported",
  C: "Experimental",
};

const TIER_TINT: Record<"A" | "B" | "C", string> = {
  A: "bg-emerald-100 text-emerald-700",
  B: "bg-slate-100 text-slate-600",
  C: "bg-amber-100 text-amber-700",
};

export function SignalPrimitiveCard({
  primitive,
  onClick,
  selected = false,
  className,
}: Props) {
  const interactive = !!onClick;

  return (
    <button
      type="button"
      data-testid={`primitive-card-${primitive.id}`}
      onClick={() => onClick?.(primitive)}
      disabled={!interactive}
      className={cn(
        "group flex w-full flex-col gap-2 rounded-lg border bg-white p-4 text-left transition",
        interactive && "cursor-pointer hover:border-slate-400 hover:shadow-sm",
        !interactive && "cursor-default",
        selected ? "border-slate-900 ring-2 ring-slate-900/10" : "border-slate-200",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">
            {primitive.name}
          </p>
          <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {primitive.family}
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            TIER_TINT[primitive.evidence_tier],
          )}
          title={TIER_LABEL[primitive.evidence_tier]}
        >
          Tier {primitive.evidence_tier}
        </span>
      </div>
      <p className="line-clamp-2 text-[13px] leading-snug text-slate-600">
        {primitive.description}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[11px] font-medium",
            CATEGORY_TINT[primitive.category],
          )}
        >
          {SIGNAL_CATEGORY_LABEL[primitive.category]}
        </span>
        {primitive.is_ranking ? (
          <span className="rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            Ranking
          </span>
        ) : null}
        {selected ? (
          <span className="ml-auto text-[11px] font-semibold text-slate-900">
            Selected
          </span>
        ) : null}
      </div>
    </button>
  );
}
