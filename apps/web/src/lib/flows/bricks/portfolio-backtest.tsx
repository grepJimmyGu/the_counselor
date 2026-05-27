"use client";

/**
 * <PortfolioBacktest> — PRD-13b adapter brick.
 *
 * Calls the existing `runBacktest` API helper with the StrategyJson the
 * OverlayPicker built. Renders a loading skeleton, then auto-advances
 * to the review step once the BacktestResult lands.
 *
 * The real backtest engine work happens on the backend (PRD-13b backend
 * branches). This brick is intentionally minimal — no result rendering
 * lives here (that's PortfolioReview).
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { runBacktest, UpgradeRequiredError } from "@/lib/api";
import type { BacktestResult } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  backtest_title: "Running backtest",
  backtest_subtitle: "Computing the overlay's historical performance on your book.",
  backtest_retry: "Retry",
  backtest_error: "Backtest failed. Try again.",
});

// Extend the per-step context locally — only the backtest brick writes
// `backtestResult`, and only the review brick reads it.
interface PortfolioBacktestContext extends PortfolioModeContext {
  backtestResult?: BacktestResult;
}

export function PortfolioBacktest({
  context,
  updateContext,
  advance,
}: FlowStepProps<PortfolioBacktestContext>) {
  const title = useFlowCopy("portfolio_mode", "backtest_title");
  const subtitle = useFlowCopy("portfolio_mode", "backtest_subtitle");
  const retryLabel = useFlowCopy("portfolio_mode", "backtest_retry");
  const errorMsg = useFlowCopy("portfolio_mode", "backtest_error");

  const [loading, setLoading] = React.useState(!context.backtestResult);
  const [error, setError] = React.useState<string | null>(null);

  const strategyJson = context.strategyJson;

  const run = React.useCallback(() => {
    if (!strategyJson) {
      setError("No strategy built yet — go back to the overlay picker.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    runBacktest(strategyJson)
      .then((result) => {
        updateContext({ backtestResult: result } as Partial<PortfolioBacktestContext>);
        setLoading(false);
        // Auto-advance to the review step once the result lands. The
        // user shouldn't have to click "next" through a loading screen.
        advance();
      })
      .catch((err: unknown) => {
        if (err instanceof UpgradeRequiredError) {
          setError(err.entitlement.detail);
        } else {
          setError(errorMsg);
        }
        setLoading(false);
      });
    // strategyJson is stringified-stable for this purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(strategyJson)]);

  React.useEffect(() => {
    if (!context.backtestResult) {
      run();
    } else {
      // Already have a result (resumed flow) — push to review immediately.
      advance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <section className="space-y-4" data-testid="portfolio-backtest-loading">
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-48" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="space-y-3" data-testid="portfolio-backtest-error">
        <p className="text-sm text-red-600">{error}</p>
        <Button onClick={run} data-testid="portfolio-backtest-retry">
          {retryLabel}
        </Button>
      </section>
    );
  }

  // The auto-advance fired; if we're still here it's a transient render.
  return null;
}
