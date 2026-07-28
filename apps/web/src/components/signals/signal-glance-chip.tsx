"use client";

/**
 * <SignalGlanceChip> — PRD-25 L0 "glance" form of the unified signal card.
 *
 * A dot + one descriptive word, rendered identically on every ticker surface
 * (saved-strategies tile, screener results). Display-only (no interaction), so
 * it's safe to nest inside a Link or button. Themed on globals.css tokens.
 */
import type { SignalCardState } from "@/lib/contracts";
import { cn } from "@/lib/utils";

import { STATE_VISUALS } from "./signal-card-visuals";

export function SignalGlanceChip({
  state,
  label,
  asOf,
  className,
}: {
  state: SignalCardState;
  /** Override the default word (e.g. the backend display string). */
  label?: string;
  asOf?: string | null;
  className?: string;
}) {
  const visual = STATE_VISUALS[state];
  return (
    <span
      data-testid="signal-glance-chip"
      data-state={state}
      title={asOf ? `As of ${asOf}` : undefined}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        visual.neutral && "border-border bg-muted/60 text-muted-foreground",
        className,
      )}
      style={
        visual.neutral
          ? undefined
          : { color: visual.color, borderColor: visual.color, backgroundColor: visual.mutedBg }
      }
    >
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: visual.neutral ? "currentColor" : visual.color }}
      />
      {label ?? visual.label}
    </span>
  );
}
