/**
 * PRD-16b-2 — RuleComposer.
 *
 * Small AND/OR toggle that renders between two `<CustomBuildRuleCard>`s.
 * Visualized as a labeled connector between vertical cards.
 *
 * The toggle directly updates the `logic_with_prior` on the rule
 * IMMEDIATELY AFTER this connector (rule N joins to rule N-1 via
 * `rules[N].logic_with_prior`). The first rule's connector never
 * renders.
 */
"use client";

import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import { cn } from "@/lib/utils";

interface Props {
  /** Current value — "AND" / "OR". Never null (only the first rule's
   *  connector wouldn't render at all). */
  value: "AND" | "OR";
  onChange: (next: "AND" | "OR") => void;
  className?: string;
}

export function CustomBuildRuleComposer({
  value,
  onChange,
  className,
}: Props) {
  return (
    <div
      data-testid="rule-composer"
      className={cn(
        "flex items-center gap-3 py-1 pl-2",
        className,
      )}
    >
      <div className="h-px flex-1 bg-slate-200" />
      <div className="inline-flex items-center rounded-full border border-slate-200 bg-white p-0.5 shadow-sm">
        {(["AND", "OR"] as const).map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            data-testid={`composer-${opt.toLowerCase()}`}
            className={cn(
              "rounded-full px-3 py-0.5 text-[11px] font-semibold uppercase tracking-wider transition",
              value === opt
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100",
            )}
          >
            {opt}
          </button>
        ))}
      </div>
      <div className="h-px flex-1 bg-slate-200" />
    </div>
  );
}
