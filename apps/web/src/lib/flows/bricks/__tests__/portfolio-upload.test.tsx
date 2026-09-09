/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  searchSymbols: vi.fn(async () => [{ symbol: "NVDA", name: "NVIDIA Corp" }]),
  // `<ConnectBrokerage>` renders in this step and fetches its own status.
  // Reported unconfigured so it renders nothing — these tests are about the
  // manual add/CSV paths, which the connect card sits beside and does not
  // change.
  getSnapTradeStatus: async () => ({
    configured: false, registered: false, connected_accounts: 0,
    trading_enabled: false, last_synced_at: null,
  }),
  connectBrokerage: async () => ({ redirect_uri: "" }),
  listBrokerPositions: () => listBrokerPositionsMock(),
  // The Mirror mounts here when a broker is connected. Its own suites cover
  // what it renders; these only need it not to explode, and to record the
  // window it was asked for.
  getTradingBehavior: (...a: unknown[]) => getTradingBehaviorMock(...(a as [])),
  getMirrorTiming: async () => ({}),
  createExitPlan: async () => ({ rule_id: "r", strategy_id: "s", tracked: [], skipped: [] }),
}));

type BrokerRow = {
  account_id: string;
  symbol: string;
  units: number;
  average_purchase_price?: number;
};
const listBrokerPositionsMock = vi.fn<() => Promise<BrokerRow[]>>(
  async () => [],
);
const getTradingBehaviorMock = vi.fn(async () => ({
  total_buys: 0, total_sells: 0, symbols_traded: 0, round_trips: 0,
  realised_pnl: 0, fees_paid: 0, wins: 0, losses: 0,
  top_symbols_by_trades: [], top_symbols_by_pnl: [], worst_symbols_by_pnl: [],
  unmatched_sells: 0, unmatched_sell_symbols: [], open_lots: 0,
}));

// The brick reads `?connected=1` to know it is returning from the portal.
const searchParamsMock = vi.fn(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsMock(),
}));

// Same reason: the connect card reads the session, which this brick did not
// before the card was mounted inside it.
vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { PortfolioUpload } from "../portfolio-upload";

function renderUpload(overrides: { context?: Partial<{ holdings: any[] }> } = {}) {
  const advance = vi.fn();
  const updateContext = vi.fn();
  const ctx = {
    fromTrigger: "test/start",
    ...overrides.context,
  } as any;
  render(
    <PortfolioUpload
      context={ctx}
      updateContext={updateContext}
      advance={advance}
      back={() => {}}
      abort={() => {}}
    />,
  );
  return { advance, updateContext };
}

describe("PortfolioUpload", () => {
  it("renders the upload title from useFlowCopy", () => {
    renderUpload();
    expect(screen.getByText("Upload your portfolio")).toBeTruthy();
  });

  it("disables Continue when no tickers are entered", () => {
    renderUpload();
    const continueBtn = screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(true);
  });

  it("allows continuing once a ticker is typed", () => {
    const { advance, updateContext } = renderUpload();
    const tickerInput = screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement;
    fireEvent.change(tickerInput, { target: { value: "AAPL" } });
    const continueBtn = screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(false);
    fireEvent.click(continueBtn);
    expect(advance).toHaveBeenCalledTimes(1);
    expect(updateContext).toHaveBeenCalledTimes(1);
    const patch = updateContext.mock.calls[0][0];
    expect(patch.holdings).toHaveLength(1);
    expect(patch.holdings[0].ticker).toBe("AAPL");
  });

  it("parses CSV paste into rows", () => {
    renderUpload();
    const paste = screen.getByTestId("portfolio-upload-paste") as HTMLTextAreaElement;
    fireEvent.change(paste, {
      target: { value: "AAPL,0.4\nMSFT,0.3\nNVDA,0.3" },
    });
    fireEvent.click(screen.getByTestId("portfolio-upload-paste-apply"));
    // Three rows should now be in the table.
    expect((screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement).value).toBe("AAPL");
    expect((screen.getByTestId("portfolio-upload-ticker-1") as HTMLInputElement).value).toBe("MSFT");
    expect((screen.getByTestId("portfolio-upload-ticker-2") as HTMLInputElement).value).toBe("NVDA");
  });

  it("normalizes lowercase tickers to upper-case", () => {
    const { updateContext } = renderUpload();
    const input = screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "aapl" } });
    fireEvent.click(screen.getByTestId("portfolio-upload-continue"));
    const patch = updateContext.mock.calls[0][0];
    expect(patch.holdings[0].ticker).toBe("AAPL");
  });

  it("adds a holding from the search typeahead", async () => {
    renderUpload();
    fireEvent.change(screen.getByTestId("portfolio-upload-search"), {
      target: { value: "NVDA" },
    });
    fireEvent.click(await screen.findByTestId("portfolio-upload-suggestion-NVDA"));
    // The first (empty) row is filled with the picked ticker.
    expect(
      (screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement).value,
    ).toBe("NVDA");
  });

  it("does not add a duplicate ticker from search", async () => {
    renderUpload({ context: { holdings: [{ ticker: "NVDA", shares: 1 }] } });
    fireEvent.change(screen.getByTestId("portfolio-upload-search"), {
      target: { value: "NVDA" },
    });
    fireEvent.click(await screen.findByTestId("portfolio-upload-suggestion-NVDA"));
    // Already held → no second row appended.
    expect(screen.queryByTestId("portfolio-upload-ticker-1")).toBeNull();
  });

  it("warns (does not block) when weights don't sum to 1.0", () => {
    renderUpload();
    fireEvent.change(screen.getByTestId("portfolio-upload-ticker-0"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("portfolio-upload-weight-0"), { target: { value: "0.4" } });
    fireEvent.click(screen.getByTestId("portfolio-upload-add"));
    fireEvent.change(screen.getByTestId("portfolio-upload-ticker-1"), { target: { value: "MSFT" } });
    fireEvent.change(screen.getByTestId("portfolio-upload-weight-1"), { target: { value: "0.3" } });
    // Total weight = 0.7. Should show the warning string.
    expect(screen.getByText(/Weights sum to 70%/)).toBeTruthy();
    // Continue button is still enabled (warning, not block).
    expect((screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement).disabled).toBe(false);
  });
});


// ── returning from the brokerage portal (PRD-28 Step 2) ────────────────────

describe("PortfolioUpload — holdings from a connected broker", () => {
  const fromBroker = () =>
    searchParamsMock.mockReturnValue(new URLSearchParams("connected=1"));

  beforeEach(() => {
    searchParamsMock.mockReturnValue(new URLSearchParams());
    listBrokerPositionsMock.mockResolvedValue([]);
  });

  it("does not read the broker on a normal visit", async () => {
    renderUpload();
    await waitFor(() => screen.getByTestId("portfolio-upload"));
    expect(listBrokerPositionsMock).not.toHaveBeenCalled();
  });

  it("REGRESSION: loads holdings when returning from the portal", async () => {
    /* Without this the user authorises their broker, comes back, and finds
     * the same empty form they left — which reads as the connection having
     * failed. */
    fromBroker();
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();
    await waitFor(() => screen.getByTestId("portfolio-upload-from-broker"));
    expect(screen.getByDisplayValue("NVDA")).toBeTruthy();
  });

  it("MERGES with typed rows rather than clobbering them", async () => {
    /* Someone may have typed tickers before deciding to connect. Losing
     * them would punish the user who engaged most. */
    fromBroker();
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload({ context: { holdings: [{ ticker: "MSFT", weight: 0.5 }] } });
    await waitFor(() => screen.getByTestId("portfolio-upload-from-broker"));
    expect(screen.getByDisplayValue("NVDA")).toBeTruthy();
    expect(screen.getByDisplayValue("MSFT")).toBeTruthy();
  });

  it("prefers the broker's row when both sources have the same ticker", async () => {
    /* The broker's share count and cost basis are real; the typed row was
     * a guess. One row, not two. */
    fromBroker();
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload({ context: { holdings: [{ ticker: "NVDA", weight: 0.9 }] } });
    await waitFor(() => screen.getByTestId("portfolio-upload-from-broker"));
    expect(screen.getAllByDisplayValue("NVDA")).toHaveLength(1);
  });

  it("says so, and stays usable, when the read fails after connecting", async () => {
    /* "Connected but we couldn't read your holdings" is a different and
     * more recoverable problem than "connection failed" — the manual paths
     * still work. */
    fromBroker();
    listBrokerPositionsMock.mockRejectedValue(new Error("upstream down"));
    renderUpload();
    await waitFor(() => screen.getByTestId("portfolio-upload-broker-error"));
    expect(screen.getByTestId("portfolio-upload-search")).toBeTruthy();
  });
});

/* ── moved here 2026-09-09 ────────────────────────────────────────────────
 *
 * The overlay overview and the Mirror both used to live on Home. The overview
 * described rules for a portfolio nobody had uploaded yet, and the Mirror sat
 * on /account/brokerage above a trade list. Both belong beside the holdings a
 * rule would actually be put over.
 *
 * The three overlay invariants below came WITH the cards from
 * `home-quant-strategies.test.tsx` — they are product guarantees, not tests of
 * a location, so moving the UI without moving them would have dropped them.
 */

describe("the overlays it will offer", () => {
  it("shows all six, read-only, before the choice is made", () => {
    renderUpload();
    const cards = screen.getAllByTestId(/^strategy-card-/);
    expect(cards.length).toBe(OVERLAY_DISPLAY_ORDER.length);
    // Read-only: the pick happens after the diagnosis, not here.
    for (const c of cards) expect(c.tagName).not.toBe("BUTTON");
  });

  it("says up front how many holdings an overlay needs", () => {
    renderUpload();
    const first = OVERLAY_DISPLAY_ORDER[0];
    expect(screen.getByTestId(`strategy-card-${first}`).textContent).toMatch(
      new RegExp(`Needs ${OVERLAY_METADATA[first].minHoldings}\\+ holding`),
    );
  });

  it("never shows a performance figure without its basis", () => {
    /* A number never travels without what produced it. */
    renderUpload();
    const t = screen.getByTestId("portfolio-upload-overlays").textContent ?? "";
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      const meta = OVERLAY_METADATA[kind];
      if (t.includes(meta.tagline)) expect(t).toContain(meta.historicalEstimate);
    }
  });

  it("claims no portfolio fit while the book is still empty", () => {
    /* `fitLabel` is the diagnosis step's verdict; nothing has been diagnosed. */
    renderUpload();
    const t = screen.getByTestId("portfolio-upload-overlays").textContent ?? "";
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      expect(t).not.toContain(OVERLAY_METADATA[kind].fitLabel);
    }
  });
});

describe("the Mirror", () => {
  // Nothing else in this file clears it, and earlier tests mount a connected
  // book — so a call-count assertion here needs its own clean slate.
  beforeEach(() => {
    getTradingBehaviorMock.mockClear();
    listBrokerPositionsMock.mockResolvedValue([]);
  });

  it("stays away until there is a connected account to read", async () => {
    listBrokerPositionsMock.mockResolvedValueOnce([]);
    renderUpload();
    await waitFor(() => expect(screen.getByTestId("portfolio-upload")).toBeTruthy());
    expect(screen.queryByTestId("portfolio-upload-mirror")).toBeNull();
    expect(getTradingBehaviorMock).not.toHaveBeenCalled();
  });

  it("appears once a broker is connected", async () => {
    listBrokerPositionsMock.mockResolvedValueOnce([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();
    expect(await screen.findByTestId("portfolio-upload-mirror")).toBeTruthy();
  });

  it("NAMES the window it covers", async () => {
    /* THE INVARIANT THAT MOVED. On /account/brokerage the panel sat under a
     * 1M/6M/1Y selector, so its repeated "this window" pointed at something
     * the reader could see. There is no trade list here to anchor it, so the
     * period is printed — and it must match the date the panel was actually
     * asked for, or the label describes a different span than the numbers. */
    listBrokerPositionsMock.mockResolvedValueOnce([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();
    const panel = await screen.findByTestId("portfolio-upload-mirror");

    await waitFor(() => expect(getTradingBehaviorMock).toHaveBeenCalled());
    const asked = (getTradingBehaviorMock.mock.calls.at(-1)![1] as { startDate: string })
      .startDate;

    expect(panel.textContent).toContain(asked);
    expect(panel.textContent).toMatch(/last 12 months/i);
  });
});
