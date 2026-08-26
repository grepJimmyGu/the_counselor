/** @vitest-environment jsdom */

/**
 * My Strategies -> a strategy -> the position dashboard.
 *
 * This page gated on `bar_resolution !== "daily"` until 2026-08-21 — the
 * same condition #331 replaced on the public `/strategies/[slug]` page and
 * left behind here. It mattered more here: `SavedStrategiesTile` sends
 * EVERY SignalCard click to this route, so home's own strategy tile routed
 * every user to the one page that hid the dashboard for daily strategies —
 * which, since #327, is the path the product actually runs on.
 *
 * That is the third time a UI gate has outlived the backend rule it was
 * written for. These tests exist so the fourth fails the build.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const listSavedStrategiesMock = vi.fn();
vi.mock("@/lib/api", () => ({
  listSavedStrategies: (...a: unknown[]) => listSavedStrategiesMock(...a),
  // `<ActiveExecutionDashboard>`'s children fetch; keep them inert.
  getSignalCard: async () => ({ state: "pending", display: "\u2014" }),
  getSnapTradeStatus: async () => ({
    configured: false, registered: false, connected_accounts: 0,
    trading_enabled: false, last_synced_at: null,
  }),
  listBrokerPositions: async () => [],
  getStrategyPositions: async () => [],
  getStrategyTradeLog: async () => [],
  getUniverseState: async () => ({ symbols: [] }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "strat_1" }),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

import Page from "../page";

function strategy(json: Record<string, unknown>) {
  return [{
    id: "strat_1",
    title: "Momentum runner",
    created_at: "2026-08-01T00:00:00Z",
    is_public: false,
    strategy_json: json,
  }];
}

const LADDER = {
  risk_management: {
    exit_ladder: [{ trigger_pct: -0.08, action: "sell_all", label: "Stop" }],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("saved strategy dashboard page", () => {
  it("REGRESSION: shows the dashboard for a DAILY strategy with a ladder", async () => {
    /* The whole bug. Daily is the interval the product runs on since #327,
     * and this page hid the dashboard for every one of them. */
    listSavedStrategiesMock.mockResolvedValue(
      strategy({ bar_resolution: "daily", ...LADDER }),
    );
    render(<Page />);
    await waitFor(() => screen.getByTestId("active-execution-dashboard"));
    expect(screen.queryByTestId("not-active-execution")).toBeNull();
  });

  it("shows it for an intraday strategy with a ladder too", async () => {
    listSavedStrategiesMock.mockResolvedValue(
      strategy({ bar_resolution: "15min", ...LADDER }),
    );
    render(<Page />);
    await waitFor(() => screen.getByTestId("active-execution-dashboard"));
  });

  it("hides it when there is no exit ladder — the real backend rule", async () => {
    /* `declare_position` 400s without a ladder because there is nothing to
     * monitor a position against. The UI asks the same question the API
     * does, rather than a proxy for it. */
    listSavedStrategiesMock.mockResolvedValue(
      strategy({ bar_resolution: "daily" }),
    );
    render(<Page />);
    await waitFor(() => screen.getByTestId("not-active-execution"));
    expect(screen.queryByTestId("active-execution-dashboard")).toBeNull();
  });

  it("hides it for an empty ladder, not just a missing one", async () => {
    listSavedStrategiesMock.mockResolvedValue(
      strategy({ bar_resolution: "daily", risk_management: { exit_ladder: [] } }),
    );
    render(<Page />);
    await waitFor(() => screen.getByTestId("not-active-execution"));
  });

  it("explains the missing ladder, not the bar resolution", async () => {
    /* The old copy told a daily user their INTERVAL was the problem and to
     * "enable Active Execution (a non-daily bar resolution)" — advice that
     * is now exactly backwards. */
    listSavedStrategiesMock.mockResolvedValue(
      strategy({ bar_resolution: "daily" }),
    );
    render(<Page />);
    await waitFor(() => screen.getByTestId("not-active-execution"));
    const copy = screen.getByTestId("not-active-execution").textContent ?? "";
    expect(copy).toMatch(/no exit rules/i);
    expect(copy).not.toMatch(/non-daily/i);
  });
});
