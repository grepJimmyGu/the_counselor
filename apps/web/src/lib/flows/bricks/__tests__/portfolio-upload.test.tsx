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
