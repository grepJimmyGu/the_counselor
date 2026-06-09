/**
 * PRD-16b-2 — Active Execution scaffold (pitfall B).
 *
 * Per PRD-16 HANDOFF §6 pitfall B:
 *   "PRD-16c assumes a 'leave room' pattern in PRD-16b's WHEN OUT
 *    block — leave a visible toggle scaffold (even if disabled and
 *    labeled 'Active execution coming soon') so PRD-16c can wire it
 *    up without modifying PRD-16b's component."
 *
 * This brick is that scaffold: visible, disabled, with a 1-line "coming
 * soon" hint. PRD-16c flips the disabled state + adds the multi-tier
 * exit ladder editor as an `<ExitLadderEditor>` child below this row.
 *
 * State is wired via `value` + `onChange` (controlled). For v1 the
 * canvas always passes `false` + a no-op; PRD-16c hooks real state.
 */
"use client";

import { cn } from "@/lib/utils";

interface Props {
  value: boolean;
  onChange: (next: boolean) => void;
  /** PRD-16b ships `disabled=true` always. PRD-16c flips to false. */
  disabled?: boolean;
  className?: string;
}

export function CustomBuildActiveExecutionScaffold({
  value,
  onChange,
  disabled = true,
  className,
}: Props) {
  return (
    <div
      data-testid="active-execution-scaffold"
      className={cn(
        "rounded-lg border border-slate-200 bg-slate-50/60 p-4",
        disabled && "opacity-75",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Advanced
          </p>
          <h4 className="mt-0.5 text-sm font-semibold text-slate-900">
            Active execution
          </h4>
          <p className="mt-1 text-[12px] leading-snug text-slate-500">
            Run this strategy live with intraday monitoring and a
            multi-tier exit ladder (stop + partial TP + full TP).
            <strong className="font-medium"> Coming soon.</strong>
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={value}
          disabled={disabled}
          onClick={() => onChange(!value)}
          data-testid="active-execution-toggle"
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border transition",
            value
              ? "border-emerald-500 bg-emerald-500"
              : "border-slate-300 bg-slate-200",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 transform rounded-full bg-white shadow transition",
              value ? "translate-x-6" : "translate-x-1",
            )}
          />
        </button>
      </div>
    </div>
  );
}
