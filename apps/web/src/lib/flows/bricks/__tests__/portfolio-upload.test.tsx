/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  searchSymbols: vi.fn(async () => [{ symbol: "NVDA", name: "NVIDIA Corp" }]),
  // `<ConnectBrokerage>` renders in this step and fetches its own status.
  // Reported unconfigured so it renders nothing — these tests are about the
  // manual add/CSV paths, which the connect card sits beside and does not
  // change.
  getSnapTradeStatus: () => getSnapTradeStatusMock(),
  connectBrokerage: async () => ({ redirect_uri: "" }),
  listBrokerPositions: () => listBrokerPositionsMock(),
  // The Mirror mounts here when a broker is connected. Its own suites cover
  // what it renders; these only need it not to explode, and to record the
  // window it was asked for.
  getTradingBehavior: (...a: unknown[]) =>
    getTradingBehaviorMock(...(a as [string, { startDate: string }])),
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
/** Default: nothing connected, so the connect card renders and the Mirror
 *  stays away — which is what most of this file is about. */
const DISCONNECTED = {
  configured: false, registered: false, connected_accounts: 0,
  trading_enabled: false, last_synced_at: null,
};
const CONNECTED = {
  configured: true, registered: true, connected_accounts: 1,
  trading_enabled: false, last_synced_at: null,
};
const getSnapTradeStatusMock = vi.fn(async () => DISCONNECTED);
// Params declared so `mock.calls[n][1]` types — the window assertion below
// reads the startDate the panel was asked for, and an untyped mock makes that
// a cast against an empty tuple.
const getTradingBehaviorMock = vi.fn(async (_token: string, _opts: { startDate: string }) => ({
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

/** Every mock in this file is module-scoped, and `mockResolvedValue` sets the
 *  implementation while KEEPING call history. Three separate bugs in this
 *  suite have come from one describe inheriting another's leftovers — a
 *  `?connected=1` that was never cleared, a call count that included the
 *  previous test's calls. One reset at the top, so a describe only has to
 *  state what it actually needs. */
beforeEach(() => {
  searchParamsMock.mockReturnValue(new URLSearchParams());
  listBrokerPositionsMock.mockClear();
  listBrokerPositionsMock.mockResolvedValue([]);
  getSnapTradeStatusMock.mockClear();
  getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
  getTradingBehaviorMock.mockClear();
});

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
    // mockResolvedValue sets the implementation but KEEPS call history, so a
    // count assertion here would silently include the previous test's calls.
    listBrokerPositionsMock.mockClear();
    listBrokerPositionsMock.mockResolvedValue([]);
    getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
  });

  it("does not read the broker when there is no broker to read", async () => {
    /* CONTRACT CHANGE, stated openly per CLAUDE.md.
     *
     * This was "does not read the broker on a normal visit", asserting that
     * only `?connected=1` triggers a position read. That is no longer true and
     * should not be: the card above the form says "holdings up to date", and
     * for a user who connected in an EARLIER session the form underneath it
     * was empty — the page contradicted its own copy.
     *
     * What survives is the half that still matters: an unconnected visitor
     * costs the broker API nothing. */
    renderUpload();
    await waitFor(() => screen.getByTestId("portfolio-upload"));
    expect(listBrokerPositionsMock).not.toHaveBeenCalled();
  });

  it("reads holdings for someone who connected in an earlier session", async () => {
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();                       // note: NO ?connected=1
    expect(await screen.findByDisplayValue("NVDA")).toBeTruthy();
  });

  it("reads the broker once, not once per resolving effect", async () => {
    /* `connected` arrives asynchronously, so without the ref guard this
     * effect re-runs and re-adds broker rows the user has since deleted. */
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();
    await screen.findByDisplayValue("NVDA");
    expect(listBrokerPositionsMock).toHaveBeenCalledTimes(1);
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
  /* MOVED AGAIN, and the invariants came with them — twice now. These were
   * written against Home's <StrategyCard> grid, re-homed here in #363, and the
   * cards have since become six one-line rows because the grid measured
   * 8,138px and put the flow's own CTA in the last 0.7% of a 9,831px page.
   *
   * The guarantees did not change form with the UI. What each overlay needs is
   * still stated up front; no performance figure appears without its basis;
   * and no fit is claimed before there is a book to fit. */

  it("still shows all six, and they are not choices yet", () => {
    renderUpload();
    const rows = screen.getAllByTestId(/^overlay-row-/);
    expect(rows.length).toBe(OVERLAY_DISPLAY_ORDER.length);
    // The pick happens after the diagnosis; nothing here is clickable.
    for (const r of rows) expect(r.querySelector("button")).toBeNull();
  });

  it("says up front how many holdings each one needs", () => {
    renderUpload();
    const first = OVERLAY_DISPLAY_ORDER[0];
    expect(screen.getByTestId(`overlay-row-${first}`).textContent).toContain(
      `needs ${OVERLAY_METADATA[first].minHoldings}+`,
    );
  });

  it("carries NO performance figure at all, because a row cannot carry a basis", () => {
    /* STRENGTHENED. The card version could show "−28% vs −55%" as long as
     * `historicalEstimate` sat beside it. A collapsed row has no room for the
     * basis, so the rule here is absolute: no figure, not "a figure with its
     * source". That is what makes the compaction safe rather than just short. */
    renderUpload();
    const t = screen.getByTestId("overlay-shortlist-rows").textContent ?? "";
    expect(t).not.toMatch(/[-−+]?\d+(\.\d+)?\s*%/);
    expect(t).not.toMatch(/\$\s*\d/);
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      const meta = OVERLAY_METADATA[kind];
      expect(t).not.toContain(meta.tagline);
      expect(t).not.toContain(meta.historicalEstimate);
    }
  });

  it("keeps every oneLine free of a figure, so a future edit cannot sneak one in", () => {
    /* A guard on the DATA, not the render — the row is the one place a number
     * can appear with nothing to qualify it. Mechanics are fine and necessary:
     * "200-day average" is what the overlay does, not what it earned. */
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      const line = OVERLAY_METADATA[kind].oneLine;
      expect(line, kind).not.toMatch(/%/);
      expect(line, kind).not.toMatch(/\$/);
      expect(line.length, kind).toBeLessThanOrEqual(90);
    }
  });

  it("claims no fit while the book is still empty", () => {
    renderUpload();
    const t = screen.getByTestId("portfolio-upload-book") ? "" : "";
    const summary = screen.getByTestId("overlay-shortlist-summary").textContent ?? "";
    expect(summary).toContain("add holdings to see which fit");
    expect(screen.queryByTestId("overlay-shortlist-fit")).toBeNull();
    // `fitLabel` is the diagnosis step's verdict; nothing has been diagnosed.
    const rows = screen.getByTestId("overlay-shortlist-rows").textContent ?? "";
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      expect(rows).not.toContain(OVERLAY_METADATA[kind].fitLabel);
    }
    expect(t).toBe("");
  });

  it("counts the fits against the book once there IS one — typed counts too", async () => {
    /* The fit column reads a holdings COUNT, so it works for someone who never
     * connects. On a one-holding book "1 of 6" is a finding about
     * concentration, which six cards could never have told them. */
    renderUpload();
    fireEvent.change(screen.getByTestId("portfolio-upload-search"), {
      target: { value: "NVDA" },
    });
    const hit = await screen.findByTestId("portfolio-upload-suggestion-NVDA");
    fireEvent.click(hit);

    const expected = OVERLAY_DISPLAY_ORDER.filter(
      (k) => OVERLAY_METADATA[k].minHoldings <= 1,
    ).length;
    await waitFor(() => {
      expect(screen.getByTestId("overlay-shortlist-fit").textContent).toBe(
        `${expected} of ${OVERLAY_DISPLAY_ORDER.length} fit${expected === 1 ? "s" : ""} this book`,
      );
    });
  });
});

describe("the Mirror", () => {
  // Nothing else in this file clears it, and earlier tests mount a connected
  // book — so a call-count assertion here needs its own clean slate.
  beforeEach(() => {
    getTradingBehaviorMock.mockClear();
    listBrokerPositionsMock.mockResolvedValue([]);
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
  });

  it("stays away until there is a connected account to read", async () => {
    getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
    renderUpload();
    await waitFor(() => expect(screen.getByTestId("portfolio-upload")).toBeTruthy());
    expect(screen.queryByTestId("portfolio-upload-mirror")).toBeNull();
    expect(getTradingBehaviorMock).not.toHaveBeenCalled();
  });

  it("REGRESSION: appears for someone who connected in an EARLIER session", async () => {
    /* THE BUG. The gate was `brokerCount > 0`, and `brokerCount` is only set
     * by the `?connected=1` portal round-trip. Every returning user — nearly
     * all of them — opened a page whose own card said "1 brokerage account
     * connected" above a Mirror that never rendered. */
    renderUpload();                       // NO ?connected=1
    expect(await screen.findByTestId("portfolio-upload-mirror")).toBeTruthy();
  });

  it("REGRESSION: appears for someone holding NOTHING", async () => {
    /* The old gate was wrong in principle as well as in practice. The Mirror
     * reads CLOSED-TRADE history, not holdings: someone who sold everything
     * has zero positions and the most to learn from it. Gating on a position
     * count showed them nothing. */
    listBrokerPositionsMock.mockResolvedValue([]);
    renderUpload();
    expect(await screen.findByTestId("portfolio-upload-mirror")).toBeTruthy();
  });

  it("NAMES the window it covers", async () => {
    /* THE INVARIANT THAT MOVED. On /account/brokerage the panel sat under a
     * 1M/6M/1Y selector, so its repeated "this window" pointed at something
     * the reader could see. There is no trade list here to anchor it, so the
     * period is printed — and it must match the date the panel was actually
     * asked for, or the label describes a different span than the numbers. */
    renderUpload();
    const panel = await screen.findByTestId("portfolio-upload-mirror");

    await waitFor(() => expect(getTradingBehaviorMock).toHaveBeenCalled());
    const asked = getTradingBehaviorMock.mock.calls.at(-1)![1].startDate;

    expect(panel.textContent).toContain(asked);
    expect(panel.textContent).toMatch(/last 12 months/i);
  });
});

describe("the two states of this page", () => {
  it("does not call it an upload when the broker already filled it in", async () => {
    /* "Upload your portfolio" above a book the broker supplied contradicts the
     * card directly beneath it, which says the holdings are up to date. */
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    renderUpload();
    expect(await screen.findByText("Your portfolio")).toBeTruthy();
    expect(screen.queryByText("Upload your portfolio")).toBeNull();
  });

  it("still calls it an upload when there is nothing yet", async () => {
    getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
    renderUpload();
    expect(await screen.findByText("Upload your portfolio")).toBeTruthy();
  });

  it("opens the form when the book is empty and folds it once filled", async () => {
    /* For someone with nothing the table IS the task. For a connected user it
     * is confirmation, and left open it pushes the reason they came below the
     * fold. */
    getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
    renderUpload();
    await waitFor(() =>
      expect(screen.getByTestId("portfolio-upload-book")).toHaveProperty("open", true),
    );

    cleanup();
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "a1", symbol: "NVDA", units: 120, average_purchase_price: 118.4 },
    ]);
    renderUpload();
    await screen.findByDisplayValue("NVDA");
    expect(screen.getByTestId("portfolio-upload-book")).toHaveProperty("open", false);
  });

  it("tells you WHY the button is dead instead of just dimming it", async () => {
    /* A disabled CTA with no reason is a dead end wearing a CTA's clothes, and
     * it names BOTH ways out — typing one, or connecting. */
    getSnapTradeStatusMock.mockResolvedValue(DISCONNECTED);
    renderUpload();
    const cta = await screen.findByTestId("portfolio-upload-continue");
    expect(cta).toHaveProperty("disabled", true);
    const why = screen.getByTestId("portfolio-upload-blocked").textContent ?? "";
    expect(why).toMatch(/at least one holding/i);
    expect(why).toMatch(/connect a brokerage/i);
  });

  it("argues for connecting from INSIDE the card, so it cannot outlive it", async () => {
    /* Rendered as a sibling this copy survives every path that makes
     * <ConnectBrokerage> return null — an operator who has not configured
     * SnapTrade, and a user who just dismissed it — leaving prose arguing for
     * a button that is not on the page. */
    getSnapTradeStatusMock.mockResolvedValue({ ...DISCONNECTED, configured: true });
    renderUpload();
    const why = await screen.findByTestId("connect-brokerage-extra");
    // The honest asymmetry: holdings can be typed, trade history cannot.
    expect(why.textContent).toMatch(/trade history, which cannot be typed/i);
    expect(screen.getByTestId("connect-brokerage").contains(why)).toBe(true);

    cleanup();
    fireEvent.click(screen.queryByTestId("connect-brokerage-dismiss") ?? document.body);
  });

  it("says nothing about connecting once a broker is connected", async () => {
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    renderUpload();
    await screen.findByText("Your portfolio");
    expect(screen.queryByTestId("connect-brokerage-extra")).toBeNull();
  });
});
