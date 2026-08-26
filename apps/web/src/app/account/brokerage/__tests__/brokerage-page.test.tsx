/** @vitest-environment jsdom */

/**
 * /account/brokerage — the account as the broker sees it.
 *
 * The claims under test are about honesty and independence: a broker's own
 * numbers are labelled as theirs, a trade is dated when it HAPPENED rather
 * than when it settled, and one failing read costs its section rather than
 * the page.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getSnapTradeStatus = vi.fn();
const listBrokerPositions = vi.fn();
const listBrokerActivities = vi.fn();
const getBrokerPerformance = vi.fn();
const getBrokerBalanceHistory = vi.fn();
const listBrokerOrders = vi.fn();

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

vi.mock("@/lib/api", () => ({
  getSnapTradeStatus: (...a: unknown[]) => getSnapTradeStatus(...(a as [])),
  listBrokerPositions: (...a: unknown[]) => listBrokerPositions(...(a as [])),
  listBrokerActivities: (...a: unknown[]) => listBrokerActivities(...(a as [])),
  getBrokerPerformance: (...a: unknown[]) => getBrokerPerformance(...(a as [])),
  getBrokerBalanceHistory: (...a: unknown[]) => getBrokerBalanceHistory(...(a as [])),
  listBrokerOrders: (...a: unknown[]) => listBrokerOrders(...(a as [])),
  // <ConnectBrokerage> renders when not connected and fetches its own state.
  connectBrokerage: async () => ({ redirect_uri: "https://example.test" }),
}));

import BrokeragePage from "../page";

const CONNECTED = {
  configured: true, registered: true, connected_accounts: 1,
  trading_enabled: false, last_synced_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  getSnapTradeStatus.mockResolvedValue(CONNECTED);
  listBrokerPositions.mockResolvedValue([
    { account_id: "a1", symbol: "NVDA", units: 120,
      average_purchase_price: 118.4, last_price: 121.05, open_pnl: 318 },
  ]);
  listBrokerActivities.mockResolvedValue([
    { account_id: "a1", activity_id: "t1", type: "BUY", symbol: "NVDA",
      units: 120, price: 118.4, amount: -14208,
      trade_date: "2026-08-20", settlement_date: "2026-08-22" },
    { account_id: "a1", activity_id: "d1", type: "DIVIDEND", symbol: "KO",
      amount: 42.1, trade_date: "2026-07-15" },
  ]);
  getBrokerPerformance.mockResolvedValue([
    { timeframe: "1Y", rate_of_return: 0.184 },
  ]);
  getBrokerBalanceHistory.mockResolvedValue([
    { date: "2026-08-01", value: 41200 },
  ]);
  listBrokerOrders.mockResolvedValue([]);
});

describe("before connecting", () => {
  it("offers the connection rather than an empty account", async () => {
    getSnapTradeStatus.mockResolvedValue({ ...CONNECTED, registered: false, connected_accounts: 0 });
    render(<BrokeragePage />);
    await waitFor(() =>
      expect(screen.getByTestId("connect-brokerage")).toBeTruthy(),
    );
    expect(screen.queryByTestId("brokerage-holdings")).toBeNull();
  });
});

describe("holdings", () => {
  it("shows what you hold and what it cost", async () => {
    render(<BrokeragePage />);
    const table = await screen.findByTestId("brokerage-holdings");
    expect(table.textContent).toMatch(/NVDA/);
    expect(table.textContent).toMatch(/\$118\.40/);
  });

  it("totals the account at market, not at cost", async () => {
    /* 120 × 121.05 = 14,526 — the last price, not the 118.40 paid. What the
     * account is worth now is the number a person is looking for. */
    render(<BrokeragePage />);
    const total = await screen.findByTestId("brokerage-market-value");
    expect(total.textContent).toBe("$14,526.00");
  });
});

describe("trade history", () => {
  it("lists buys and sells, not dividends", async () => {
    /* A dividend is not something you did. Mixing it into "buys and sells"
     * makes the list of decisions unreadable. */
    render(<BrokeragePage />);
    const rows = await screen.findByTestId("brokerage-trades");
    expect(rows.textContent).toMatch(/NVDA/);
    expect(rows.textContent).not.toMatch(/KO/);
  });

  it("dates a trade when it HAPPENED, not when it settled", async () => {
    /* trade_date 2026-08-20 vs settlement_date 2026-08-22. Only the first is
     * what a person means by "when I bought it." */
    render(<BrokeragePage />);
    const rows = await screen.findByTestId("brokerage-trades");
    expect(rows.textContent).toMatch(/2026-08-20/);
    expect(rows.textContent).not.toMatch(/2026-08-22/);
  });

  it("asks the broker for the window instead of filtering locally", async () => {
    /* Pulling everything and slicing here would page through years to show
     * a month. */
    render(<BrokeragePage />);
    await screen.findByTestId("brokerage-trades");

    fireEvent.click(screen.getByTestId("brokerage-window-1M"));
    await waitFor(() => {
      const last = listBrokerActivities.mock.calls.at(-1);
      expect(last?.[1]).toHaveProperty("startDate");
    });
    const oneYear = listBrokerActivities.mock.calls[0][1] as { startDate: string };
    const oneMonth = listBrokerActivities.mock.calls.at(-1)![1] as { startDate: string };
    expect(oneMonth.startDate > oneYear.startDate).toBe(true);
  });

  it("says the window is empty rather than showing nothing", async () => {
    listBrokerActivities.mockResolvedValue([]);
    render(<BrokeragePage />);
    expect(await screen.findByTestId("brokerage-no-trades")).toBeTruthy();
  });
});

describe("performance", () => {
  it("shows the broker's figure and says whose it is", async () => {
    render(<BrokeragePage />);
    const perf = await screen.findByTestId("brokerage-performance");
    expect(perf.textContent).toMatch(/1Y/);
    expect(perf.textContent).toMatch(/\+18\.4%/);
    expect(
      screen.getByText(/broker.s own figures/i),
    ).toBeTruthy();
  });

  it("does not render a 1840% return when the broker sends a percent", async () => {
    /* Brokers report either a fraction or a percent and don't say which.
     * Multiplying a percent by 100 is the visible failure. */
    getBrokerPerformance.mockResolvedValue([{ timeframe: "1Y", rate_of_return: 18.4 }]);
    render(<BrokeragePage />);
    const perf = await screen.findByTestId("brokerage-performance");
    expect(perf.textContent).toMatch(/\+18\.4%/);
  });
});

describe("independence", () => {
  it("one failing read costs its section, not the page", async () => {
    /* Five independent calls to a third party. A broker having a bad morning
     * must not blank the holdings a user came to see. */
    getBrokerPerformance.mockRejectedValue(new Error("upstream 502"));
    getBrokerBalanceHistory.mockRejectedValue(new Error("upstream 502"));
    render(<BrokeragePage />);

    expect(await screen.findByTestId("brokerage-holdings")).toBeTruthy();
    expect(await screen.findByTestId("brokerage-trades")).toBeTruthy();
    expect(screen.queryByTestId("brokerage-performance")).toBeNull();
  });
});
