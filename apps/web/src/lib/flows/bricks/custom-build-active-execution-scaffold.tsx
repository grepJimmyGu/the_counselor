/**
 * Active Execution toggle for the Custom Build composer.
 *
 * History: shipped in PRD-16b-2 as a disabled "coming soon" scaffold
 * (HANDOFF §6 pitfall B's "leave room" pattern), then activated in
 * PRD-16c-5 when the intraday monitor cron + dashboard endpoints + the
 * <BarResolutionPicker> + <ExitLadderEditor> children all landed.
 * Today: live. The canvas reveals the picker + editor inside an
 * emerald-tinted card when this toggle is on.
 *
 * State is controlled via `value` + `onChange`. `disabled` defaults to
 * `false` post-16c — pass `true` only if a containing flow wants to
 * temporarily mute the toggle (e.g., entitlement-gated tier preview).
 */
"use client";

import { cn } from "@/lib/utils";

interface Props {
  value: boolean;
  onChange: (next: boolean) => void;
  /** Defaults to `false` (live). Set `true` to mute for entitlement-
   *  gated previews where the user can see the option but can't enable
   *  it on their current plan. */
  disabled?: boolean;
  className?: string;
}

export function CustomBuildActiveExecutionScaffold({
  value,
  onChange,
  disabled = false,
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
            Run this strategy live with intraday bar monitoring and a
            multi-tier exit ladder (stop + partial TP + full TP). Toggle
            on to configure bar resolution and the exit tiers below.
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
