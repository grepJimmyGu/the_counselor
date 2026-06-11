/**
 * PRD-16c-6 — ActiveExecutionDashboard.
 *
 * Composition wrapper for the strategy-detail page's active-execution
 * section. Renders the three bricks in stacked order:
 *
 *   1. <UniverseWatchPanel /> — live price cards
 *   2. <PositionCardsGrid />  — per-position state + distance metrics
 *   3. <TradeLogTable />      — chronological event log
 *
 * The parent strategy-detail page conditionally renders this dashboard
 * only when `strategy_json.bar_resolution !== 'daily'` (PRD-16c §"renders
 * for active-execution strategies only"). Daily strategies see the
 * existing backtest result viewer instead.
 */
"use client";

import { useState } from "react";

import { DeclarePositionForm } from "./declare-position-form";
import { PositionCardsGrid } from "./position-cards-grid";
import { TradeLogTable } from "./trade-log-table";
import { UniverseWatchPanel } from "./universe-watch-panel";

interface Props {
  strategyId: string;
  className?: string;
}

export function ActiveExecutionDashboard({ strategyId, className }: Props) {
  // Bumped when the user declares a position, to force the grid to
  // refetch immediately rather than waiting for the next 30s poll.
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <section
      data-testid="active-execution-dashboard"
      className={className}
      aria-label="Active execution dashboard"
    >
      <div className="space-y-6">
        <UniverseWatchPanel strategyId={strategyId} />
        <DeclarePositionForm
          strategyId={strategyId}
          onDeclared={() => setRefreshKey((k) => k + 1)}
        />
        <PositionCardsGrid strategyId={strategyId} refreshKey={refreshKey} />
        <TradeLogTable strategyId={strategyId} />
      </div>
    </section>
  );
}
