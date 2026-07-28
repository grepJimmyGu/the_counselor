/**
 * PRD-25 — shared state → visual map for the unified signal card brick.
 *
 * Colours come from the globals.css design tokens (theme-aware in light + dark):
 *   --profit / --profit-muted, --warning-amber / --warning-amber-muted.
 * `pending` has no semantic colour → neutral (muted) Tailwind classes.
 *
 * Labels are deliberately DESCRIPTIVE, never prescriptive ("In signal", not
 * "Buy") — the research/tool compliance stance.
 */
import type { SignalCardState } from "@/lib/contracts";

export interface StateVisual {
  /** One-word glance label. */
  label: string;
  /** CSS-var colour for coloured states (dot + border + text). */
  color?: string;
  /** CSS-var translucent background. */
  mutedBg?: string;
  /** `pending` renders with neutral muted classes instead of a token colour. */
  neutral?: boolean;
}

export const STATE_VISUALS: Record<SignalCardState, StateVisual> = {
  in_signal: { label: "In signal", color: "var(--profit)", mutedBg: "var(--profit-muted)" },
  basket: { label: "In basket", color: "var(--profit)", mutedBg: "var(--profit-muted)" },
  flat: { label: "Flat", color: "var(--warning-amber)", mutedBg: "var(--warning-amber-muted)" },
  pending: { label: "Pending", neutral: true },
};
