"use client";

import { cn } from "@/lib/utils";
import { interpretCmf } from "@/lib/market-pulse-format";

/**
 * Plain-English chip for technical metrics.
 *
 * Rendering rule: numbers alone don't tell a story to a retail user.
 * `CMF=0.32` is meaningless without context; "Strong inflow" is not.
 * Each chip variant maps a value to a band + colored label.
 *
 * Used on sector heatmap tooltips, sector table rows, and Mover row hover.
 */

interface SignalChipProps {
  kind: "cmf" | "perf" | "rs";
  value: number | null | undefined;
  /** "xs" for inline use in dense rows; "sm" for tooltips and standalone use. */
  size?: "xs" | "sm";
  className?: string;
}

export function SignalChip({ kind, value, size = "xs", className }: SignalChipProps) {
  if (kind === "cmf") {
    const i = interpretCmf(value);
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full font-medium",
          size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
          i.colorClass,
          className,
        )}
      >
        {i.label}
      </span>
    );
  }

  if (kind === "perf") {
    const v = value;
    const label = perfBand(v);
    const colorClass =
      v == null
        ? "bg-muted text-muted-foreground"
        : v >= 0.015
          ? "bg-emerald-600 text-white"
          : v >= 0.002
            ? "bg-emerald-100 text-emerald-800"
            : v > -0.002
              ? "bg-muted text-muted-foreground"
              : v > -0.015
                ? "bg-red-100 text-red-800"
                : "bg-red-600 text-white";
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full font-medium",
          size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
          colorClass,
          className,
        )}
      >
        {label}
      </span>
    );
  }

  // kind === "rs" (relative strength vs SPY)
  const v = value;
  const label = rsBand(v);
  const colorClass =
    v == null
      ? "bg-muted text-muted-foreground"
      : v >= 0.02
        ? "bg-emerald-600 text-white"
        : v >= 0.005
          ? "bg-emerald-100 text-emerald-800"
          : v > -0.005
            ? "bg-muted text-muted-foreground"
            : v > -0.02
              ? "bg-red-100 text-red-800"
              : "bg-red-600 text-white";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium",
        size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
        colorClass,
        className,
      )}
    >
      {label}
    </span>
  );
}

function perfBand(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 0.015) return "Strong gain";
  if (v >= 0.002) return "Up";
  if (v > -0.002) return "Flat";
  if (v > -0.015) return "Down";
  return "Strong loss";
}

function rsBand(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 0.02) return "Outperforming";
  if (v >= 0.005) return "Above SPY";
  if (v > -0.005) return "In line";
  if (v > -0.02) return "Below SPY";
  return "Underperforming";
}
