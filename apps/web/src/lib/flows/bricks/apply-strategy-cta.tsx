"use client";

/**
 * <ApplyStrategyCTA> — PRD-14 reusable brick.
 *
 * The Mode 1 secondary-trigger button: "Apply a strategy on this ticker."
 * Lives in `lib/flows/bricks/` so future surfaces (commodity page,
 * screener rows, per-holding rows in PRD-13b's portfolio diagnosis) can
 * pick it off the shelf instead of re-implementing the affordance.
 *
 * Sprint 1 scope: the brick fires an optional `onClick` so each consumer
 * that already mounts a `<StrategyBuilderModal>` in-page (the established
 * pattern on the stock detail page) can open it locally. The PRD-14
 * spec called for a `<Link>` to `/strategies/new?ticker=…`, but that
 * route does not exist in the current codebase — the strategy builder is
 * an in-page modal everywhere it's used. Sprint 2's Mode 1 refactor
 * replaces the onClick path with `startFlow('one_asset_mode', …)`; the
 * brick's prop surface is preserved across that swap.
 *
 * Analytics: PostHog wiring lives at the use-site so each surface can
 * fire its own event (`stock_page_apply_strategy_clicked`,
 * `commodity_page_apply_strategy_clicked`, …). The brick stays
 * surface-agnostic.
 */

import { Button } from "@/components/ui/button";
import { registerModeCopy, useFlowCopy } from "../copy";

registerModeCopy("apply_cta", {
  label_default: "⚡ Apply a strategy",
  label_compact: "Apply strategy",
});

export interface ApplyStrategyCTAProps {
  /** The ticker the user is currently looking at. */
  ticker: string;
  /**
   * Surface identifier for analytics + future flow `fromTrigger`.
   * Format: `"stock_page"`, `"commodity_page"`, `"screener_row"`, …
   */
  from: string;
  /** Primary = filled, Secondary = outline. Default: primary. */
  variant?: "primary" | "secondary";
  /** Use compact label + small button. Useful in dense layouts. */
  compact?: boolean;
  /**
   * Triggered on click. Required in Sprint 1 because each consumer owns
   * its own `<StrategyBuilderModal>` instance. Sprint 2's Mode 1
   * refactor will replace this with `startFlow('one_asset_mode', { … })`
   * and `onClick` will become optional.
   */
  onClick: () => void;
  /** Optional aria-label override. */
  ariaLabel?: string;
}

export function ApplyStrategyCTA({
  ticker,
  from,
  variant = "primary",
  compact = false,
  onClick,
  ariaLabel,
}: ApplyStrategyCTAProps) {
  const labelDefault = useFlowCopy("apply_cta", "label_default");
  const labelCompact = useFlowCopy("apply_cta", "label_compact");
  const label = compact ? labelCompact : labelDefault;
  return (
    <Button
      type="button"
      variant={variant === "primary" ? "default" : "outline"}
      size={compact ? "sm" : "default"}
      onClick={onClick}
      aria-label={ariaLabel ?? `${label} on ${ticker} (from ${from})`}
      data-testid="apply-strategy-cta"
      data-ticker={ticker}
      data-from={from}
    >
      {label}
    </Button>
  );
}
