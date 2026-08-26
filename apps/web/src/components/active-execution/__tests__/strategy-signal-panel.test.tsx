/** @vitest-environment jsdom */

/**
 * The entry side of the loop.
 *
 * The exit half has worked for weeks — a tier fires, an email arrives, the
 * ticket shows a sell. "Your strategy wants in" had no surface at all, so
 * the only way to act on an entry was to spot it yourself.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getSignalCard = vi.fn();
// Flipped per test. False is the production default today.
const tradingEnabled = { value: true };

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

vi.mock("@/lib/api", () => ({
  getSignalCard: (...a: unknown[]) => getSignalCard(...(a as [])),
  // <PlaceOrder> mounts inside and fetches its own state. Trading reported
  // ON with one connected account, so the buy path is exercised rather than
  // silently hidden.
  getSnapTradeStatus: async () => ({
    configured: true, registered: true, connected_accounts: 1,
    trading_enabled: tradingEnabled.value, last_synced_at: null,
  }),
  listBrokerPositions: async () => [],
  listBrokerAccounts: async () => [
    { id: "acct-1", institution_name: "Schwab", name: "Roth", number: "…8821" },
  ],
  previewOrder: async () => ({
    trade_id: "t1", symbol: "NVDA", action: "BUY", units: 0,
    estimated_commission: 0, remaining_cash: 6412,
  }),
  placeOrder: async () => ({ status: "ACCEPTED" }),
}));

import { StrategySignalPanel, entrySymbol, entryTicketText } from "../strategy-signal-panel";
import type { SignalCard } from "@/lib/contracts";

const LONG: SignalCard = {
  saved_strategy_id: "s1",
  strategy_title: "Trend Leader",
  strategy_type: "moving_average_filter",
  symbol: "NVDA",
  state: "in_signal",
  display: "LONG NVDA",
  reason: "NVDA is above its 200-day average.",
  fired_primitives: [],
  backtest_id: "bt1",
  as_of: "2026-08-22",
} as SignalCard;

beforeEach(() => {
  vi.clearAllMocks();
  getSignalCard.mockResolvedValue(LONG);
  tradingEnabled.value = true;
});

describe("entrySymbol", () => {
  it("names a ticker only when the strategy is actually in a single-name long", () => {
    expect(entrySymbol(LONG)).toBe("NVDA");
    expect(entrySymbol({ ...LONG, state: "flat" } as SignalCard)).toBeNull();
    expect(entrySymbol({ ...LONG, state: "basket", symbol: null } as SignalCard)).toBeNull();
    expect(entrySymbol(null)).toBeNull();
  });
});

describe("what the strategy says", () => {
  it("shows the reading and the session it came from", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    expect((await screen.findByTestId("signal-panel-display")).textContent).toBe(
      "LONG NVDA",
    );
    expect(screen.getByText(/as of 2026-08-22/)).toBeTruthy();
  });

  it("distinguishes 'not computed yet' from 'no signal'", async () => {
    /* An empty panel would read as "your strategy says nothing", which is a
     * different claim from "we haven't looked yet." */
    getSignalCard.mockResolvedValue({ ...LONG, state: "pending" });
    render(<StrategySignalPanel strategyId="s1" />);
    const p = await screen.findByTestId("signal-panel-pending");
    expect(p.textContent).toMatch(/haven.t computed/i);
  });

  it("offers no buy when the strategy is flat", async () => {
    getSignalCard.mockResolvedValue({ ...LONG, state: "flat", display: "CASH", symbol: null });
    render(<StrategySignalPanel strategyId="s1" />);
    await screen.findByTestId("signal-panel");
    expect(screen.queryByTestId("signal-panel-amount")).toBeNull();
  });
});

describe("with order placement OFF — the production state today", () => {
  /* SNAPTRADE_TRADING_ENABLED defaults false, so `<PlaceOrder>` renders
   * nothing. The first version of this panel showed a dollar field anyway:
   * you typed $2,000 and nothing happened — an input promising an action the
   * product could not perform. <ExitTicket> had this right from the start
   * (Copy always works); the entry side has to match. */
  beforeEach(() => {
    tradingEnabled.value = false;
  });

  it("REGRESSION: offers a ticket you can carry, never a dead input", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    expect(await screen.findByTestId("signal-panel-ticket")).toBeTruthy();
    expect(screen.getByTestId("signal-panel-copy")).toBeTruthy();
    // The thing that did nothing.
    expect(screen.queryByTestId("signal-panel-amount")).toBeNull();
  });
});

describe("the ticket text", () => {
  it("is three lines: the order, where it came from, what it is not", () => {
    const lines = entryTicketText(LONG, "NVDA", 2000).split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("BUY $2,000 of NVDA");
    expect(lines[1]).toContain("Trend Leader");
    expect(lines[2]).toMatch(/not a live quote/i);
  });

  it("omits a size when none was chosen", () => {
    expect(entryTicketText(LONG, "NVDA", null).split("\n")[0]).toBe("BUY NVDA");
  });
});

describe("the buy", () => {
  it("asks for dollars, not shares", async () => {
    /* You sell what you hold, so a share count is exact. A buy answers "how
     * much of my money" — and the broker converts at the fill, so rounding
     * it here would print a number the fill won't match. */
    render(<StrategySignalPanel strategyId="s1" />);
    const field = await screen.findByTestId("signal-panel-amount");
    expect(field).toBeTruthy();
    expect(screen.getByText(/don.t round it for you/i)).toBeTruthy();
  });

  it("offers nothing until an amount is entered", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    await screen.findByTestId("signal-panel-amount");
    expect(screen.queryByTestId("place-order-NVDA")).toBeNull();
  });

  it("sends the dollar amount, never a share count", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    fireEvent.change(await screen.findByTestId("signal-panel-amount"), {
      target: { value: "2000" },
    });
    await waitFor(() =>
      expect(screen.getByTestId("place-order-NVDA")).toBeTruthy(),
    );
    expect(screen.getByText(/\$2000\.00 at Schwab/)).toBeTruthy();
  });

  it("ignores a nonsense amount rather than pricing it", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    fireEvent.change(await screen.findByTestId("signal-panel-amount"), {
      target: { value: "-50" },
    });
    expect(screen.queryByTestId("place-order-NVDA")).toBeNull();
  });
});

describe("the standing promise", () => {
  it("never implies the strategy is advice, or that we act alone", async () => {
    render(<StrategySignalPanel strategyId="s1" />);
    const panel = await screen.findByTestId("signal-panel");
    expect(panel.textContent).toMatch(/never places an order you/i);
    expect(panel.textContent).toMatch(/not advice/i);
  });
});
