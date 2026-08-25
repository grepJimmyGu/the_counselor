/** @vitest-environment jsdom */

/**
 * /account/positions — PRD-28 Step 4.
 *
 * The claims under test are about honesty rather than layout: an untracked
 * brokerage holding must never look like something Livermore is watching, a
 * position with an unresolved tier must not look settled, and the page must
 * never say a price is live when it is a stale close.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const listOpenPositions = vi.fn(async () => [] as unknown[]);
const listBrokerPositions = vi.fn(async () => [] as unknown[]);

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

vi.mock("@/lib/api", () => ({
  listOpenPositions: (...a: unknown[]) => listOpenPositions(...(a as [])),
  listBrokerPositions: (...a: unknown[]) => listBrokerPositions(...(a as [])),
  // <UnresolvedExits> and <ConnectBrokerage> both render here and fetch
  // their own state; without these the page's own assertions fail for
  // reasons that have nothing to do with the page.
  listUnresolvedExits: async () => [],
  holdThroughExit: async () => ({}),
  confirmPositionExit: async () => ({}),
  getSnapTradeStatus: async () => ({
    configured: false, registered: false, connected_accounts: 0,
    trading_enabled: false, last_synced_at: null,
  }),
  connectBrokerage: async () => ({ redirect_uri: "https://example.test" }),
  previewOrder: async () => ({}),
  placeOrder: async () => ({}),
}));

import PositionsPage from "../page";
import type { TrackedPosition } from "@/lib/contracts";

const NVDA: TrackedPosition = {
  strategy_id: "s1",
  strategy_title: "Momentum runner",
  position_id: "p1",
  symbol: "NVDA",
  entered_at: "2026-08-01T00:00:00Z",
  entry_price: 100,
  shares_initial: 120,
  shares_remaining: 120,
  latest_price: 105,
  price_source: "daily_close",
  price_at: "2026-08-22",
  pct_change_from_entry: 0.05,
  stop: { label: "Stop", trigger_pct: -0.08, price: 92, distance_pct: -0.1238 },
  next_target: { label: "TP1", trigger_pct: 0.15, price: 115, distance_pct: 0.0952 },
  unresolved_count: 0,
  bar_resolution: "daily",
};

beforeEach(() => {
  vi.clearAllMocks();
  listOpenPositions.mockResolvedValue([]);
  listBrokerPositions.mockResolvedValue([]);
});

describe("tracked positions", () => {
  it("shows the live stop and next target as prices, not just percentages", async () => {
    /* "8% below entry" requires arithmetic against a number the user has to
     * remember. "$92" is the thing they'd type into a broker. */
    listOpenPositions.mockResolvedValue([NVDA]);
    render(<PositionsPage />);

    const stop = await screen.findByTestId("tracked-NVDA-stop");
    expect(stop.textContent).toMatch(/\$92\.00/);
    const target = screen.getByTestId("tracked-NVDA-target");
    expect(target.textContent).toMatch(/\$115\.00/);
  });

  it("labels a close as a close rather than implying a live quote", async () => {
    /* A daily strategy is evaluated at the close. Presenting that price as
     * "current" would suggest the monitor is watching tick by tick. */
    listOpenPositions.mockResolvedValue([NVDA]);
    render(<PositionsPage />);
    const row = await screen.findByTestId("tracked-NVDA");
    expect(row.textContent).toMatch(/last close/i);
  });

  it("says so when there is no recent price, rather than showing a blank", async () => {
    listOpenPositions.mockResolvedValue([
      { ...NVDA, latest_price: null, price_source: "none", pct_change_from_entry: null },
    ]);
    render(<PositionsPage />);
    const row = await screen.findByTestId("tracked-NVDA");
    expect(row.textContent).toMatch(/no recent price/i);
  });

  it("surfaces a position that owes a decision", async () => {
    /* An unresolved tier means a stop fired and the user has not answered.
     * That position must not read as settled. */
    listOpenPositions.mockResolvedValue([{ ...NVDA, unresolved_count: 1 }]);
    render(<PositionsPage />);
    const flag = await screen.findByTestId("tracked-NVDA-unresolved");
    expect(flag.textContent).toMatch(/waiting on you/i);
  });

  it("says 'none set' rather than inventing a stop", async () => {
    /* Possible now that `track` can leave a strategy untracked. Showing a
     * blank would read as "no risk"; showing a made-up number is worse. */
    listOpenPositions.mockResolvedValue([{ ...NVDA, stop: null, next_target: null }]);
    render(<PositionsPage />);
    await screen.findByTestId("tracked-NVDA");
    expect(screen.queryByTestId("tracked-NVDA-stop")).toBeNull();
  });

  it("points somewhere useful when nothing is tracked", async () => {
    render(<PositionsPage />);
    const empty = await screen.findByTestId("positions-empty");
    expect(empty.textContent).toMatch(/nothing tracked yet/i);
    expect(screen.getByTestId("positions-empty-cta")).toBeTruthy();
  });
});

describe("brokerage holdings", () => {
  it("keeps untracked holdings separate and says nothing is watching them", async () => {
    /* THE POINT OF THE THIRD SECTION. A brokerage holding has no strategy
     * and no exit ladder. Mixing it in with the tracked positions would
     * imply Livermore is monitoring it. */
    listOpenPositions.mockResolvedValue([NVDA]);
    listBrokerPositions.mockResolvedValue([
      { account_id: "a1", symbol: "AAPL", units: 50, average_purchase_price: 180 },
    ]);
    render(<PositionsPage />);

    const list = await screen.findByTestId("untracked-holdings");
    expect(list.textContent).toMatch(/AAPL/);
    expect(screen.getByText(/nothing is watching them/i)).toBeTruthy();
  });

  it("does not list a holding that IS tracked", async () => {
    /* The broker reports NVDA and so do we — showing it twice, once under
     * "nothing is watching them", would be actively misleading. */
    listOpenPositions.mockResolvedValue([NVDA]);
    listBrokerPositions.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 100 },
    ]);
    render(<PositionsPage />);

    await screen.findByTestId("tracked-NVDA");
    expect(screen.queryByTestId("untracked-NVDA")).toBeNull();
  });

  it("a broker read that fails does not take the tracked positions down", async () => {
    /* Two independent fetches. The brokerage section is a bonus; the
     * tracked positions are the page. */
    listOpenPositions.mockResolvedValue([NVDA]);
    listBrokerPositions.mockRejectedValue(new Error("upstream 502"));
    render(<PositionsPage />);

    expect(await screen.findByTestId("tracked-NVDA")).toBeTruthy();
    expect(screen.queryByTestId("positions-error")).toBeNull();
  });
});

describe("failures", () => {
  it("reports a load failure instead of showing an empty page", async () => {
    /* "Nothing tracked yet" on a failed fetch would tell a user their
     * positions are gone. */
    listOpenPositions.mockRejectedValue(new Error("boom"));
    render(<PositionsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("positions-error")).toBeTruthy(),
    );
    expect(screen.queryByTestId("positions-empty")).toBeNull();
  });
});

describe("the standing promise", () => {
  it("never implies Livermore places orders", async () => {
    listOpenPositions.mockResolvedValue([NVDA]);
    render(<PositionsPage />);
    await screen.findByTestId("tracked-NVDA");
    expect(
      screen.getByText(/never places or cancels an order/i),
    ).toBeTruthy();
  });
});
