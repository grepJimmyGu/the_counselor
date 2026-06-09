/**
 * PRD-16c-6 — Live dashboard brick tests.
 *
 * Covers the three composing bricks (UniverseWatchPanel,
 * PositionCardsGrid, TradeLogTable) plus the wrapper. Mocks the
 * api.ts helpers so no network is touched.
 */
import { render, screen, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

vi.mock("@/lib/api", () => ({
  getUniverseState: vi.fn(),
  getStrategyPositions: vi.fn(),
  getStrategyTradeLog: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

import {
  getStrategyPositions,
  getStrategyTradeLog,
  getUniverseState,
} from "@/lib/api";

import { ActiveExecutionDashboard } from "../active-execution-dashboard";
import { PositionCardsGrid } from "../position-cards-grid";
import { TradeLogTable } from "../trade-log-table";
import { UniverseWatchPanel } from "../universe-watch-panel";

beforeEach(() => {
  vi.clearAllMocks();
  useSessionMock.mockReturnValue({
    data: { backendToken: "tok_abc" },
    status: "authenticated",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── UniverseWatchPanel ───────────────────────────────────────────────────────


describe("UniverseWatchPanel", () => {
  it("renders skeleton while loading", () => {
    (getUniverseState as unknown as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {}),
    );
    render(<UniverseWatchPanel strategyId="s1" />);
    expect(screen.getByTestId("universe-watch-skeleton")).toBeTruthy();
  });

  it("renders cards for each symbol after load", async () => {
    (getUniverseState as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      {
        strategy_id: "s1",
        bar_resolution: "15min",
        generated_at: new Date().toISOString(),
        universe: [
          {
            symbol: "AAPL",
            latest_price: 180.5,
            latest_at: new Date().toISOString(),
            source: "intraday",
          },
          {
            symbol: "MSFT",
            latest_price: null,
            latest_at: null,
            source: "no_data",
          },
        ],
      },
    );
    render(<UniverseWatchPanel strategyId="s1" pollIntervalMs={9999999} />);
    await waitFor(() => screen.getByTestId("universe-watch-panel"));
    expect(screen.getByTestId("universe-card-AAPL")).toBeTruthy();
    expect(screen.getByTestId("universe-card-MSFT")).toBeTruthy();
    expect(screen.getByText("$180.50")).toBeTruthy();
    expect(screen.getByText("No recent bar")).toBeTruthy();
  });

  it("renders error state on api failure", async () => {
    (getUniverseState as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("503"),
    );
    render(<UniverseWatchPanel strategyId="s1" pollIntervalMs={9999999} />);
    await waitFor(() => screen.getByTestId("universe-watch-error"));
    expect(screen.getByTestId("universe-watch-error").textContent).toContain(
      "503",
    );
  });

  it("waits for sessionStatus !== 'loading' before fetching (trap #19)", () => {
    useSessionMock.mockReturnValue({
      data: { backendToken: "tok_abc" },
      status: "loading" as unknown as "authenticated",
    });
    (getUniverseState as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      {
        strategy_id: "s1",
        bar_resolution: "15min",
        generated_at: new Date().toISOString(),
        universe: [],
      },
    );
    render(<UniverseWatchPanel strategyId="s1" />);
    expect(getUniverseState).not.toHaveBeenCalled();
  });
});

// ── PositionCardsGrid ────────────────────────────────────────────────────────


describe("PositionCardsGrid", () => {
  it("renders empty state when no positions", async () => {
    (
      getStrategyPositions as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      positions: [],
      open_count: 0,
      closed_count: 0,
    });
    render(<PositionCardsGrid strategyId="s1" pollIntervalMs={9999999} />);
    await waitFor(() => screen.getByTestId("positions-empty"));
  });

  it("renders open + closed position cards", async () => {
    (
      getStrategyPositions as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      open_count: 1,
      closed_count: 1,
      positions: [
        {
          id: "p1",
          symbol: "AAPL",
          entered_at: new Date().toISOString(),
          entry_price: 100,
          shares_initial: 10,
          shares_remaining: 10,
          is_open: true,
          closed_at: null,
          final_pnl: null,
          latest_price: 115,
          pct_change_from_entry: 0.15,
          trade_log: [{ event: "entry" }],
        },
        {
          id: "p2",
          symbol: "MSFT",
          entered_at: new Date().toISOString(),
          entry_price: 420,
          shares_initial: 5,
          shares_remaining: 0,
          is_open: false,
          closed_at: new Date().toISOString(),
          final_pnl: 120,
          latest_price: 444,
          pct_change_from_entry: 0.057,
          trade_log: [
            { event: "entry" },
            { event: "tp1_hit", tier_label: "TP1" },
          ],
        },
      ],
    });
    render(<PositionCardsGrid strategyId="s1" pollIntervalMs={9999999} />);
    await waitFor(() => screen.getByTestId("position-card-AAPL"));
    expect(screen.getByTestId("position-card-AAPL")).toBeTruthy();
    expect(screen.getByTestId("position-card-MSFT")).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByText("Closed")).toBeTruthy();
    // pct rendered inside a cell with the price + parens, so match
    // partial: $115.00 (+15.00%)
    expect(screen.getByText(/\+15\.00%/)).toBeTruthy();
  });

  it("renders error state", async () => {
    (
      getStrategyPositions as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValue(new Error("404"));
    render(<PositionCardsGrid strategyId="s1" pollIntervalMs={9999999} />);
    await waitFor(() => screen.getByTestId("positions-error"));
  });
});

// ── TradeLogTable ────────────────────────────────────────────────────────────


describe("TradeLogTable", () => {
  it("renders empty state when no events", async () => {
    (
      getStrategyTradeLog as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      events: [],
      total: 0,
      next_before: null,
    });
    render(<TradeLogTable strategyId="s1" />);
    await waitFor(() => screen.getByTestId("trade-log-empty"));
  });

  it("renders event rows + Load more button when next_before is set", async () => {
    (
      getStrategyTradeLog as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      total: 100,
      next_before: "2026-06-09T13:00:00",
      events: [
        {
          position_id: "p1",
          symbol: "AAPL",
          event: "tp1_hit",
          timestamp: "2026-06-09T14:30:00",
          price: 115.0,
          shares_sold: 3.33,
          tier_label: "TP1",
        },
      ],
    });
    render(<TradeLogTable strategyId="s1" />);
    await waitFor(() => screen.getByTestId("trade-log-table"));
    expect(screen.getByText("AAPL")).toBeTruthy();
    expect(screen.getByText(/tp1_hit/)).toBeTruthy();
    expect(screen.getByTestId("trade-log-load-more")).toBeTruthy();
  });

  it("does NOT render Load more when next_before is null", async () => {
    (
      getStrategyTradeLog as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      total: 1,
      next_before: null,
      events: [
        {
          position_id: "p1",
          symbol: "AAPL",
          event: "entry",
          timestamp: "2026-06-09T14:00:00",
          price: 100,
          shares: 10,
        },
      ],
    });
    render(<TradeLogTable strategyId="s1" />);
    await waitFor(() => screen.getByTestId("trade-log-table"));
    expect(screen.queryByTestId("trade-log-load-more")).toBeNull();
  });
});

// ── ActiveExecutionDashboard composition wrapper ────────────────────────────


describe("ActiveExecutionDashboard", () => {
  it("renders all three composing bricks", async () => {
    (getUniverseState as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      {
        strategy_id: "s1",
        bar_resolution: "15min",
        generated_at: new Date().toISOString(),
        universe: [],
      },
    );
    (
      getStrategyPositions as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      positions: [],
      open_count: 0,
      closed_count: 0,
    });
    (
      getStrategyTradeLog as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      strategy_id: "s1",
      events: [],
      total: 0,
      next_before: null,
    });

    render(<ActiveExecutionDashboard strategyId="s1" />);
    expect(screen.getByTestId("active-execution-dashboard")).toBeTruthy();
    // All three bricks initialize (skeletons or empty states).
    await waitFor(() => {
      screen.getByTestId("positions-empty");
      screen.getByTestId("trade-log-empty");
    });
  });
});
