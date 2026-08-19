/** @vitest-environment jsdom */

/**
 * An exit alert arrives as an email and a dismissible banner, both of which
 * can be missed. This surface is derived server-side from `trade_log`, so
 * there is nothing to dismiss — missing the email makes an exit LATE, not
 * LOST.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const listUnresolvedExitsMock = vi.fn();
const holdThroughExitMock = vi.fn();
vi.mock("@/lib/api", () => ({
  listUnresolvedExits: (...a: unknown[]) => listUnresolvedExitsMock(...a),
  holdThroughExit: (...a: unknown[]) => holdThroughExitMock(...a),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok_abc" },
    status: "authenticated" as const,
  }),
}));

import { UnresolvedExits } from "../unresolved-exits";

const exit1 = {
  strategy_id: "strat_1",
  strategy_title: "Momentum runner",
  position_id: "pos_1",
  symbol: "NVDA",
  trigger_type: "tier0_hit",
  tier_label: "Stop",
  signaled_at: "2026-08-18T21:00:00Z",
  price: 108.9,
  pct_change: -0.082,
  action: "sell_all",
  shares: 120,
  shares_remaining: 120,
  shares_initial: 120,
  entry_price: 118.4,
  bar_resolution: "daily",
  bar_date: "2026-08-18",
};

beforeEach(() => {
  vi.clearAllMocks();
  listUnresolvedExitsMock.mockResolvedValue([]);
  holdThroughExitMock.mockResolvedValue({});
});

describe("UnresolvedExits", () => {
  it("renders nothing when there is nothing unresolved", async () => {
    render(<UnresolvedExits />);
    await waitFor(() => expect(listUnresolvedExitsMock).toHaveBeenCalled());
    expect(screen.queryByTestId("unresolved-exits")).toBeNull();
  });

  it("shows an unresolved exit with the tier and the move", async () => {
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));
    expect(screen.getByTestId("unresolved-exit-NVDA")).toBeTruthy();
    expect(screen.getByText(/Stop tier reached at -8\.2%/)).toBeTruthy();
  });

  it("states plainly that Livermore has not sold anything", async () => {
    // §11: load-bearing, not decoration.
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));
    expect(screen.getByText(/Livermore does not place trades/i)).toBeTruthy();
  });

  it("offers no way to dismiss without deciding", async () => {
    /* The whole point. If this could be cleared without answering, it would
     * be another banner — and the fact that a stop fired would be lost the
     * same way it was before. */
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));
    expect(screen.queryByLabelText(/dismiss/i)).toBeNull();
    expect(screen.queryByText(/^×$/)).toBeNull();
  });

  it("records 'I'm holding' and stops asking", async () => {
    // Holding is an ordinary decision, not non-compliance.
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));

    fireEvent.click(screen.getByText(/i'm holding/i));

    await waitFor(() =>
      expect(holdThroughExitMock).toHaveBeenCalledWith(
        "strat_1",
        "pos_1",
        { trigger_type: "tier0_hit" },
        "tok_abc",
      ),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("unresolved-exits")).toBeNull(),
    );
  });

  it("sends 'I sold' to the position rather than confirming a fill it invented", async () => {
    /* Confirming needs the user's ACTUAL shares and price. Posting a
     * synthesised fill would write a trade that never happened into the
     * position's P&L, so this navigates to the confirm affordance. */
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));

    const link = screen.getByText(/i sold — record it/i).closest("a");
    expect(link?.getAttribute("href")).toContain("/strategies/strat_1");
    expect(link?.getAttribute("href")).toContain("action=executed");
  });

  it("keeps the ticket collapsed until asked", async () => {
    // Several open exits must stay scannable; the ticket is what you reach
    // for once you have decided to act on a particular one.
    listUnresolvedExitsMock.mockResolvedValue([exit1]);
    render(<UnresolvedExits />);
    await waitFor(() => screen.getByTestId("unresolved-exits"));
    expect(screen.queryByTestId("exit-ticket-NVDA")).toBeNull();

    fireEvent.click(screen.getByTestId("toggle-ticket-NVDA"));
    expect(screen.getByTestId("exit-ticket-NVDA")).toBeTruthy();
  });

  it("survives the endpoint failing rather than breaking the page", async () => {
    listUnresolvedExitsMock.mockRejectedValue(new Error("boom"));
    render(<UnresolvedExits />);
    await waitFor(() => expect(listUnresolvedExitsMock).toHaveBeenCalled());
    expect(screen.queryByTestId("unresolved-exits")).toBeNull();
  });
});
