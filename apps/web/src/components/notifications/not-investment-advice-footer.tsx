/**
 * PRD-19 Step 5 — reusable compliance brick.
 *
 * Renders the standardized "not investment advice" disclaimer used by
 * every signal-generating surface (Strategy detail Execute area,
 * Notification settings preview, future onboarding email-preview pages).
 *
 * Server-rendered equivalent lives in:
 *   - apps/api/app/emails/signal_change.py (CAN-SPAM footer)
 *   - apps/api/app/emails/daily_digest.py  (CAN-SPAM footer)
 *
 * The copy is INTENTIONALLY identical to the email versions so users
 * see consistent language across in-app + email surfaces.
 *
 * No props — the component is fully static. If we need conditional
 * variants (e.g. crypto-specific disclaimer), add a `variant` prop
 * rather than forking the file.
 */
"use client";

import { cn } from "@/lib/utils";

interface NotInvestmentAdviceFooterProps {
  /** Optional tailwind class to override the default container. Use
   *  sparingly — the default styling matches the email footers. */
  className?: string;
  /** When true, render a "Compact" 2-line variant suitable for tight
   *  layouts (e.g. inline below a small button). Default false renders
   *  the full 3-line disclaimer. */
  compact?: boolean;
}

export function NotInvestmentAdviceFooter({
  className,
  compact = false,
}: NotInvestmentAdviceFooterProps) {
  if (compact) {
    return (
      <p
        className={cn(
          "text-[11px] leading-[1.5] text-slate-400",
          className,
        )}
        data-testid="not-investment-advice-footer"
      >
        Not investment advice. Livermore does not place trades on your behalf.
      </p>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-slate-50/50 px-4 py-3",
        className,
      )}
      data-testid="not-investment-advice-footer"
    >
      <p className="text-[11px] leading-[1.55] text-slate-500">
        Not investment advice. Past performance does not guarantee future
        results. Livermore does not place trades on your behalf — you decide
        whether to act on any signal.
      </p>
    </div>
  );
}
