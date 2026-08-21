/** @vitest-environment jsdom */

/**
 * The one component in the product that moves real money.
 *
 * What these pin is the shape of the flow, not the styling: there is no
 * path from idle to sent, the account is never a free choice, and nothing
 * fires without a click.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getSnapTradeStatusMock = vi.fn();
const listBrokerPositionsMock = vi.fn();
const previewOrderMock = vi.fn();
const placeOrderMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getSnapTradeStatus: (...a: unknown[]) => getSnapTradeStatusMock(...a),
  listBrokerPositions: (...a: unknown[]) => listBrokerPositionsMock(...a),
  previewOrder: (...a: unknown[]) => previewOrderMock(...a),
  placeOrder: (...a: unknown[]) => placeOrderMock(...a),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

import { PlaceOrder } from "../place-order";

const READY = {
  configured: true, registered: true, connected_accounts: 1,
  trading_enabled: true, last_synced_at: null,
};
const HELD = [{ account_id: "acct-1", symbol: "NVDA", units: 120 }];
const PREVIEW = {
  trade_id: "trade-1", symbol: "NVDA", action: "SELL", units: 40,
  estimated_commission: 0, remaining_cash: 4200,
};

beforeEach(() => {
  vi.clearAllMocks();
  getSnapTradeStatusMock.mockResolvedValue(READY);
  listBrokerPositionsMock.mockResolvedValue(HELD);
  previewOrderMock.mockResolvedValue(PREVIEW);
  placeOrderMock.mockResolvedValue({ status: "EXECUTED" });
});

describe("PlaceOrder", () => {
  it("renders nothing when trading is disabled", async () => {
    getSnapTradeStatusMock.mockResolvedValue({ ...READY, trading_enabled: false });
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => expect(getSnapTradeStatusMock).toHaveBeenCalled());
    expect(screen.queryByTestId("place-order-NVDA")).toBeNull();
  });

  it("renders nothing when no broker is connected", async () => {
    getSnapTradeStatusMock.mockResolvedValue({ ...READY, registered: false });
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => expect(getSnapTradeStatusMock).toHaveBeenCalled());
    expect(screen.queryByTestId("place-order-NVDA")).toBeNull();
  });

  it("renders nothing when the broker doesn't report that holding", async () => {
    /* The account is derived from where the shares actually are. No
     * holding, no account, no order — and no dropdown to get wrong. */
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "acct-1", symbol: "MSFT", units: 10 },
    ]);
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => expect(listBrokerPositionsMock).toHaveBeenCalled());
    expect(screen.queryByTestId("place-order-NVDA")).toBeNull();
  });

  it("REGRESSION: nothing is sent on mount — it takes two clicks", async () => {
    /* The preview is the confirmation, and it costs a deliberate action.
     * If an effect could reach `sent`, an order would leave on render. */
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    expect(previewOrderMock).not.toHaveBeenCalled();
    expect(placeOrderMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("preview-order-NVDA"));
    await waitFor(() => screen.getByTestId("send-order-NVDA"));
    expect(placeOrderMock).not.toHaveBeenCalled();  // priced, not sent

    fireEvent.click(screen.getByTestId("send-order-NVDA"));
    await waitFor(() => expect(placeOrderMock).toHaveBeenCalledOnce());
  });

  it("shows the broker's real numbers before sending", async () => {
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    fireEvent.click(screen.getByTestId("preview-order-NVDA"));
    await waitFor(() => screen.getByText(/Cash after/i));
    expect(screen.getByText("$4200.00")).toBeTruthy();
    expect(screen.getByText(/SELL 40 NVDA/)).toBeTruthy();
  });

  it("sends ONLY the previewed trade id", async () => {
    /* Not a symbol and a quantity. A caller cannot preview one order and
     * send a different one. */
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    fireEvent.click(screen.getByTestId("preview-order-NVDA"));
    await waitFor(() => screen.getByTestId("send-order-NVDA"));
    fireEvent.click(screen.getByTestId("send-order-NVDA"));
    await waitFor(() => expect(placeOrderMock).toHaveBeenCalled());
    expect(placeOrderMock).toHaveBeenCalledWith("trade-1", "tok");
  });

  it("never offers to sell more than the broker says is held", async () => {
    listBrokerPositionsMock.mockResolvedValue([
      { account_id: "acct-1", symbol: "NVDA", units: 25 },
    ]);
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    expect(screen.getByText(/25 of 25 held/)).toBeTruthy();
  });

  it("lets the user back out after seeing the price", async () => {
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    fireEvent.click(screen.getByTestId("preview-order-NVDA"));
    await waitFor(() => screen.getByTestId("send-order-NVDA"));
    fireEvent.click(screen.getByText(/cancel/i));
    await waitFor(() => screen.getByTestId("preview-order-NVDA"));
    expect(placeOrderMock).not.toHaveBeenCalled();
  });

  it("surfaces a failed placement instead of implying success", async () => {
    placeOrderMock.mockRejectedValue(new Error("insufficient buying power"));
    render(<PlaceOrder symbol="NVDA" units={40} />);
    await waitFor(() => screen.getByTestId("place-order-NVDA"));
    fireEvent.click(screen.getByTestId("preview-order-NVDA"));
    await waitFor(() => screen.getByTestId("send-order-NVDA"));
    fireEvent.click(screen.getByTestId("send-order-NVDA"));
    await waitFor(() => screen.getByText(/insufficient buying power/i));
  });
});
