"use client";

/**
 * <FlowBacktest> — mode-agnostic adapter brick (Sprint 2 / Mode 1 refactor).
 *
 * Used by every mode whose flow includes a "run a backtest on a built
 * StrategyJson" step. Replaces the per-mode `<PortfolioBacktest>` brick
 * from PRD-13b, which is now a thin re-export so the legacy import path
 * keeps working.
 *
 * Contract:
 *   - Reads `context.strategyJson` (any mode must populate this before
 *     mounting the brick).
 *   - Writes `context.backtestResult` and auto-advances on success.
 *   - Labels are pulled via `useFlowCopy(flow.id, key)` — each mode
 *     registers the four keys below. FRAMEWORK_COPY fallbacks keep the
 *     brick usable in test-mode mocks that skip mode-copy registration.
 *
 * The mode id is resolved from `useFlowState().flow.id` so the brick
 * stays pure data-in / data-out — no per-mode wrapper required.
 */

import * as React from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { runBacktest, anonymousBacktestRun, UpgradeRequiredError } from "@/lib/api";
import type { BacktestResult, StrategyJson } from "@/lib/contracts";
import type { FlowContextBase, FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import { useFlowState } from "../runtime";

/**
 * Minimal context shape every consumer must satisfy. Modes can extend
 * `FlowContextBase` with `strategyJson` and `backtestResult` (the rest
 * of the mode context is free-form).
 */
export interface FlowBacktestContext extends FlowContextBase {
  strategyJson?: StrategyJson;
  backtestResult?: BacktestResult;
}

export function FlowBacktest({
  context,
  updateContext,
  advance,
}: FlowStepProps<FlowBacktestContext>) {
  // Resolve which mode is running this brick so we can look up its
  // per-mode copy keys. Falling back to the framework default keeps the
  // brick usable in jsdom tests that don't register any mode copy.
  const { flow } = useFlowState();
  const modeId = flow.id;

  // Auth token for signed-in users — the backtest endpoint requires it.
  // Mirrors the workspace's handleRunBacktestWith pattern.
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as any)?.backendToken as string | undefined;
  const isAnonymous = sessionStatus === "unauthenticated";

  const title = useFlowCopy(modeId, "backtest_title");
  const subtitle = useFlowCopy(modeId, "backtest_subtitle");
  const retryLabel = useFlowCopy(modeId, "backtest_retry");
  const errorMsg = useFlowCopy(modeId, "backtest_error");

  const [loading, setLoading] = React.useState(!context.backtestResult);
  const [error, setError] = React.useState<string | null>(null);

  const strategyJson = context.strategyJson;

  const run = React.useCallback(() => {
    if (!strategyJson) {
      setError("No strategy built yet — go back to the previous step.");
      setLoading(false);
      return;
    }
    // Don't fire while NextAuth is still resolving — a signed-in user
    // would briefly send an anonymous request during the loading window.
    if (sessionStatus === "loading") return;
    setLoading(true);
    setError(null);

    // Branch on auth state: anonymous users hit the anonymous endpoint
    // (with cookie-based session tracking), signed-in users hit the
    // authed endpoint. Mirrors workspace's handleRunBacktestWith.
    const templateId =
      (context as FlowBacktestContext & { template?: { id: string } }).template?.id ??
      "custom";

    const promise = isAnonymous
      ? anonymousBacktestRun({ template_id: templateId, strategy_json: strategyJson })
      : runBacktest(strategyJson, { backendToken, templateId });

    promise
      .then((result) => {
        updateContext({ backtestResult: result } as Partial<FlowBacktestContext>);
        setLoading(false);
        // Auto-advance once the result lands — the user shouldn't have
        // to click through a loading screen.
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
  }, [JSON.stringify(strategyJson), sessionStatus, backendToken, isAnonymous]);

  React.useEffect(() => {
    if (!context.backtestResult) {
      run();
    } else {
      // Already have a result (resumed flow) — push to review immediately.
      advance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  if (loading) {
    return (
      <section className="space-y-4" data-testid="flow-backtest-loading">
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
      <section className="space-y-3" data-testid="flow-backtest-error">
        <p className="text-sm text-red-600">{error}</p>
        <Button onClick={run} data-testid="flow-backtest-retry">
          {retryLabel}
        </Button>
      </section>
    );
  }

  // The auto-advance fired; if we're still here it's a transient render.
  return null;
}
