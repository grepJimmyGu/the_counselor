/** @vitest-environment jsdom */

/**
 * The order ticket — the artifact a user carries to their broker.
 *
 * The rules under test are the ones that keep it honest: it prints a
 * quantity only when the quantity is derivable one way, it never rounds a
 * share count UP, and it tells the staleness story that matches how the
 * position is actually monitored.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

// `<PlaceOrder>` renders inside `<ExitTicket>` and fetches its own state.
// Without this the component calls the real API during render and the whole
// file fails for a reason unrelated to the ticket. Trading is reported OFF
// here so the ticket renders exactly as it does for a user with no broker
// connected — which is what the assertions below are about.
// Same reason: `<PlaceOrder>` reads the session, which `<ExitTicket>`
// never did before it was nested inside.
vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

vi.mock("@/lib/api", () => ({
  getSnapTradeStatus: async () => ({
    configured: false, registered: false, connected_accounts: 0,
    trading_enabled: false, last_synced_at: null,
  }),
  listBrokerPositions: async () => [],
  previewOrder: async () => ({}),
  placeOrder: async () => ({}),
}));

import { ExitTicket, quantityFor, ticketText } from "../exit-ticket";
import type { UnresolvedExit } from "@/lib/contracts";

const base: UnresolvedExit = {
  strategy_id: "strat_1",
  strategy_title: "Momentum runner",
  position_id: "pos_1",
  symbol: "NVDA",
  trigger_type: "tier0_hit",
  tier_label: "Stop",
  signaled_at: "2026-08-18T21:10:00Z",
  bar_date: "2026-08-18",
  price: 108.93,
  pct_change: -0.082,
  action: "sell_all",
  shares: 120,
  shares_remaining: 120,
  shares_initial: 120,
  entry_price: 118.4,
  bar_resolution: "daily",
};

const writeText = vi.fn(async (_text: string) => {});
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(navigator, { clipboard: { writeText } });
});

describe("quantityFor", () => {
  it("is exact for sell_all — everything still held", () => {
    expect(quantityFor(base)).toEqual({ kind: "exact", shares: "120" });
  });

  it("is exact for a FIRST scale-out on an untouched position", () => {
    const q = quantityFor({
      ...base, action: "sell_fraction", shares: 40,
      shares_remaining: 120, shares_initial: 120,
    });
    expect(q).toEqual({ kind: "exact", shares: "40" });
  });

  it("REFUSES a number for a later scale-out", () => {
    /* Not a temporary crutch. `shares_remaining` only decrements when the
     * user confirms a fill, so on a position with an unconfirmed earlier
     * exit we genuinely do not know what they hold. A confident number
     * there would describe a position that may not exist. */
    const q = quantityFor({
      ...base, action: "sell_fraction", shares: 40,
      shares_remaining: 80, shares_initial: 120,
    });
    expect(q.kind).toBe("ambiguous");
  });

  it("rounds DOWN, never up", () => {
    // A ticket must never instruct someone to sell more than the tier says.
    const q = quantityFor({
      ...base, action: "sell_fraction", shares: 26.667,
      shares_remaining: 80, shares_initial: 80,
    });
    expect(q).toEqual({ kind: "exact", shares: "26" });
  });

  it("never hands a broker 13.3333 when the user declared whole shares", () => {
    const q = quantityFor({
      ...base, action: "sell_fraction", shares: 13.3333,
      shares_remaining: 40, shares_initial: 40,
    });
    expect(q).toEqual({ kind: "exact", shares: "13" });
  });
});

describe("ticketText", () => {
  it("emits three lines: the order, the provenance, the caveat", () => {
    const lines = ticketText(base).split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("SELL 120 NVDA");
    expect(lines[1]).toContain("Momentum runner");
  });

  it("keeps the caveat attached to the number", () => {
    // Once pasted elsewhere, the caveat is the only thing stopping the
    // trigger price being read later as a quote.
    expect(ticketText(base)).toMatch(/not a fill price/i);
  });

  it("tells the DAILY staleness story for a daily position", () => {
    expect(ticketText(base)).toMatch(/next open/i);
  });

  it("tells the DELAYED-FEED story for an intraday position", () => {
    const t = ticketText({ ...base, bar_resolution: "15min" });
    expect(t).toMatch(/delayed data/i);
    expect(t).not.toMatch(/next open/i);
  });
});

describe("ExitTicket", () => {
  it("puts side, quantity and symbol in the headline — and no price", () => {
    /* The user's job at the broker is side/quantity/symbol. Price is not
     * needed for a market order, so the one structurally stale number is
     * also the one they do not need. */
    render(<ExitTicket item={base} />);
    const headline = screen.getByText(/SELL 120 NVDA/);
    expect(headline).toBeTruthy();
    expect(headline.textContent).not.toMatch(/\$/);
  });

  it("labels the price 'Trigger price', never 'Current'", () => {
    // A field name that cannot decay needs no warning attached.
    render(<ExitTicket item={base} />);
    expect(screen.getByText("Trigger price")).toBeTruthy();
    expect(screen.queryByText("Current")).toBeNull();
  });

  it("says Livermore does not place trades", () => {
    render(<ExitTicket item={base} />);
    expect(screen.getByText(/does not place trades/i)).toBeTruthy();
  });

  it("copies the three-line ticket", async () => {
    render(<ExitTicket item={base} />);
    fireEvent.click(screen.getByTestId("copy-ticket-NVDA"));
    await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    expect(writeText.mock.calls[0][0]).toBe(ticketText(base));
  });

  it("shows both readings instead of a number when holdings are unconfirmed", () => {
    render(
      <ExitTicket
        item={{
          ...base, action: "sell_fraction", shares: 40,
          shares_remaining: 80, shares_initial: 120, tier_label: "TP2",
        }}
      />,
    );
    expect(screen.getByText(/won't state a share count/i)).toBeTruthy();
    expect(screen.getByText(/If that tier was executed: 40 shares/)).toBeTruthy();
  });

  it("does not tell a daily user their price is delayed 20 minutes", () => {
    /* It isn't — it's a completed session's close. The spec was written for
     * the intraday path; saying "delayed" here would be both wrong and less
     * useful than the truth. */
    render(<ExitTicket item={base} />);
    const note = screen.getByText(/completed session/i);
    expect(note).toBeTruthy();
    expect(screen.queryByText(/delayed up to/i)).toBeNull();
  });
});
