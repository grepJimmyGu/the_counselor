/**
 * PRD-16c-5 — BarResolutionPicker.
 *
 * Lets the user select the bar resolution for an active-execution
 * strategy. Five options: daily (default — same path as PRD-16b), or
 * one of 5min / 15min / 30min / 60min. Daily routes to the EOD engine
 * (existing 22 strategy_types unchanged); intraday options route to
 * the IntradayBarService + monitor cron (PRD-16c-1/3b).
 *
 * Renders as a 5-radio pill row. Disabled when the parent toggle is
 * off — render as visible-but-greyed so the user can see what the
 * Active Execution toggle would unlock. Mirrors the
 * `active-execution-scaffold` aesthetic.
 */
"use client";

import type { BarResolution } from "@/lib/flows/custom-build-mode-context";
import { cn } from "@/lib/utils";

interface Props {
  value: BarResolution;
  onChange: (next: BarResolution) => void;
  disabled?: boolean;
  className?: string;
}

const OPTIONS: { value: BarResolution; label: string; sub: string }[] = [
  { value: "daily", label: "Daily", sub: "End of day" },
  { value: "60min", label: "60 min", sub: "Hourly" },
  { value: "30min", label: "30 min", sub: "Half-hourly" },
  { value: "15min", label: "15 min", sub: "Default intraday" },
  { value: "5min", label: "5 min", sub: "High-resolution" },
];

export function BarResolutionPicker({
  value,
  onChange,
  disabled = false,
  className,
}: Props) {
  return (
    <div
      data-testid="bar-resolution-picker"
      className={cn("space-y-2", disabled && "opacity-50", className)}
    >
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Bar resolution
        </p>
        <p className="mt-0.5 text-[12px] leading-snug text-slate-500">
          How often the strategy evaluates new bars. Intraday options use
          the live monitor; daily mirrors the standard backtest path.
        </p>
      </div>
      <div
        role="radiogroup"
        aria-label="Bar resolution"
        className="grid grid-cols-2 gap-2 sm:grid-cols-5"
      >
        {OPTIONS.map((opt) => {
          const isSelected = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onChange(opt.value)}
              data-testid={`bar-resolution-${opt.value}`}
              className={cn(
                "rounded-md border px-3 py-2 text-left transition",
                isSelected
                  ? "border-emerald-500 bg-emerald-50 ring-1 ring-emerald-200"
                  : "border-slate-200 bg-white hover:border-slate-300",
                disabled && "cursor-not-allowed",
              )}
            >
              <p
                className={cn(
                  "text-sm font-semibold",
                  isSelected ? "text-emerald-700" : "text-slate-900",
                )}
              >
                {opt.label}
              </p>
              <p className="text-[11px] text-slate-500">{opt.sub}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
