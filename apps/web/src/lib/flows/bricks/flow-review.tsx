"use client";

/**
 * <FlowReview> — mode-agnostic adapter brick (Sprint 2 / Mode 1 refactor).
 *
 * Renders headline metrics from `context.backtestResult` plus a
 * "continue to save" CTA. Replaces PRD-13b's `<PortfolioReview>` — the
 * full chart-heavy result viewer still lives inside the legacy
 * strategy-builder modal (`backtest-loading.tsx`); extracting that is a
 * Sprint 3 cleanup once the modal can be deleted.
 *
 * Sprint 1's PortfolioReview only rendered the metrics grid plus a Save
 * CTA. This brick is functionally identical, but resolves its labels
 * dynamically per mode via `useFlowState().flow.id`.
 */

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { BacktestResult, StrategyJson } from "@/lib/contracts";
import type { FlowContextBase, FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import { useFlowState } from "../runtime";

export interface FlowReviewContext extends FlowContextBase {
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

export function FlowReview({
  context,
  advance,
}: FlowStepProps<FlowReviewContext>) {
  const { flow } = useFlowState();
  const modeId = flow.id;
  const router = useRouter();

  const title = useFlowCopy(modeId, "review_title");
  const subtitle = useFlowCopy(modeId, "review_subtitle");
  const saveLabel = useFlowCopy(modeId, "review_save");

  const result = context.backtestResult;
  if (!result) {
    return (
      <section className="space-y-3" data-testid="flow-review-empty">
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
    <section className="space-y-6" data-testid="flow-review">
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

      <div className="flex flex-wrap gap-3">
        <Button onClick={advance} data-testid="flow-review-save">
          {saveLabel}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            // Persist the strategy so /workspace?autorun=true can pick it
            // up and render the full chart + explanation + sandbox review.
            // Mirrors strategy-builder-modal.tsx's runBacktest() handoff.
            const strategyJson =
              (context as FlowReviewContext & { strategyJson?: StrategyJson }).strategyJson;
            if (strategyJson) {
              sessionStorage.setItem(
                "pendingStrategy",
                JSON.stringify(strategyJson),
              );
            }
            router.push("/workspace?fromBuilder=true&autorun=true");
          }}
          data-testid="flow-review-workspace"
        >
          View full results in Workspace →
        </Button>
      </div>
    </section>
  );
}
