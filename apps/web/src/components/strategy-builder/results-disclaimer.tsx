"use client";

import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Results disclaimer — PR-E, 2026-05-24.
 *
 * Renders ABOVE the backtest equity curve on the results screen AND
 * on the strategy-summary card before "Run Backtest" so the message
 * is consistent at both commit points. Per Jimmy's spec:
 *
 *   "Once result completed and loaded, we should clearly indicate
 *    backtest result DO NOT INDICATE future outcome and I will add
 *    legal disclaim for future reference but don't have it now."
 *
 * The plain-English banner ships today. The `legalText` prop is
 * the future-proof hook for the legal copy — when Jimmy adds it,
 * pass it as the prop and it renders as a `<details>` expandable
 * below the plain-English text. Until then, the banner stands alone.
 */

export interface ResultsDisclaimerProps {
  /** Optional legal text (long-form). Renders as a `<details>` block
   *  below the plain-English banner when provided. */
  legalText?: React.ReactNode;
  /** Visual variant: `banner` (default, full-width yellow bordered
   *  card) or `inline` (compact one-liner — for use inside the
   *  summary card where vertical space is tighter). */
  variant?: "banner" | "inline";
  className?: string;
}

export function ResultsDisclaimer({
  legalText,
  variant = "banner",
  className,
}: ResultsDisclaimerProps): React.ReactElement {
  if (variant === "inline") {
    return (
      <p
        className={cn(
          "flex items-start gap-1.5 text-xs leading-snug text-muted-foreground",
          className,
        )}
      >
        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" aria-hidden="true" />
        <span>
          <strong className="text-foreground/85">Past performance is not a predictor of future results.</strong>{" "}
          Real-world execution differs (slippage, fees, market regime shifts).
        </span>
      </p>
    );
  }

  return (
    <div
      role="note"
      className={cn(
        "flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
      <div className="flex-1 text-amber-900 leading-snug">
        <p>
          <strong>Past performance is not a predictor of future results.</strong>{" "}
          This backtest shows how the strategy <em>would have</em> performed against
          historical data. Real-world execution differs (slippage, fees, market regime
          shifts). Treat this as one data point, not a guarantee.
        </p>
        {legalText && (
          <details className="mt-2 text-xs text-amber-900/80">
            <summary className="cursor-pointer font-medium hover:underline">
              Full legal disclaimer
            </summary>
            <div className="mt-1.5 leading-relaxed">{legalText}</div>
          </details>
        )}
      </div>
    </div>
  );
}
