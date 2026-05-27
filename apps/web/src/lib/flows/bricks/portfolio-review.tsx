"use client";

/**
 * <PortfolioReview> — PRD-13b adapter brick.
 *
 * Renders headline metrics from the backtest result + a sparkline-ish
 * equity-curve summary line. The full chart-heavy result viewer lives
 * inside the existing strategy-builder modal (`backtest-loading.tsx`
 * has the rendering helpers); extracting that into a reusable brick is
 * a Sprint 2 cleanup. For Sprint 1 we ship the minimum: the headline
 * numbers + a CTA to save.
 */

import { Button } from "@/components/ui/button";
import type { BacktestResult } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  review_title: "Backtest result",
  review_subtitle:
    "Past performance is not a guarantee of future results — this is a research tool, not investment advice.",
  review_save: "Save strategy →",
});

interface PortfolioReviewContext extends PortfolioModeContext {
  backtestResult?: BacktestResult;
}

function fmtPct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

function fmtNum(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return x.toFixed(digits);
}

export function PortfolioReview({
  context,
  advance,
}: FlowStepProps<PortfolioReviewContext>) {
  const title = useFlowCopy("portfolio_mode", "review_title");
  const subtitle = useFlowCopy("portfolio_mode", "review_subtitle");
  const saveLabel = useFlowCopy("portfolio_mode", "review_save");

  const result = context.backtestResult;
  if (!result) {
    return (
      <section className="space-y-3" data-testid="portfolio-review-empty">
        <p className="text-sm text-red-600">No backtest result available yet.</p>
      </section>
    );
  }

  const m = result.metrics;
  const stats: Array<[string, string]> = [
    ["Total return", fmtPct(m.total_return)],
    ["Annualized", fmtPct(m.annualized_return)],
    ["Sharpe", fmtNum(m.sharpe_ratio)],
    ["Max drawdown", fmtPct(m.max_drawdown)],
    ["Vol (annualized)", fmtPct(m.annualized_volatility)],
    ["Win rate", fmtPct(m.win_rate, 0)],
  ];

  return (
    <section className="space-y-6" data-testid="portfolio-review">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border p-3">
            <dt className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {label}
            </dt>
            <dd className="mt-1 font-mono text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>

      {result.warnings && result.warnings.length > 0 ? (
        <ul className="space-y-1 rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground">
          {result.warnings.map((w) => (
            <li key={w}>• {w}</li>
          ))}
        </ul>
      ) : null}

      <div>
        <Button onClick={advance} data-testid="portfolio-review-save">
          {saveLabel}
        </Button>
      </div>
    </section>
  );
}
