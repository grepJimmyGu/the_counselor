/**
 * PRD-16c-6 — ActiveExecutionDashboard.
 *
 * Composition wrapper for the strategy-detail page's active-execution
 * section: declare a position, watch it against the exit ladder, read the
 * event log.
 *
 * NOW RENDERS FOR DAILY STRATEGIES TOO (2026-08-18). The parent used to
 * gate this whole section on `bar_resolution !== 'daily'`, which left the
 * backend's daily-position support unreachable — #327 lifted the 400 on
 * declaring a daily position, but the form to declare one was never shown
 * to those users. The parent now gates on the exit ladder, matching what
 * the API actually requires.
 *
 * Two bricks stay intraday-only, because their endpoints early-return for
 * daily strategies (`saved_strategies.py` universe-state and
 * intraday-chart both bail on `bar_resolution == "daily"`). Rendering them
 * anyway would give daily users two permanently empty panels and teach
 * them the page is broken.
 */
"use client";

import { useState } from "react";

import { DeclarePositionForm } from "./declare-position-form";
import { IntradayChart } from "./intraday-chart";
import { PositionCardsGrid } from "./position-cards-grid";
import { TradeLogTable } from "./trade-log-table";
import { UniverseWatchPanel } from "./universe-watch-panel";

interface Props {
  strategyId: string;
  /** Drives which bricks make sense. Daily strategies are monitored once
   *  after the close by `daily_position_jobs`, so there is no intraday
   *  series to plot and no live tick to watch. */
  barResolution?: string;
  className?: string;
}

export function ActiveExecutionDashboard({
  strategyId,
  barResolution = "daily",
  className,
}: Props) {
  const isIntraday = barResolution !== "daily";
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
        {isIntraday && <UniverseWatchPanel strategyId={strategyId} />}
        <DeclarePositionForm
          strategyId={strategyId}
          onDeclared={() => setRefreshKey((k) => k + 1)}
        />
        <PositionCardsGrid strategyId={strategyId} refreshKey={refreshKey} />
        {isIntraday && (
          <IntradayChart strategyId={strategyId} refreshKey={refreshKey} />
        )}
        <TradeLogTable strategyId={strategyId} />
      </div>
    </section>
  );
}
