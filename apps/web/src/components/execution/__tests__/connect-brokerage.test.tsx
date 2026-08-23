/** @vitest-environment jsdom */

/**
 * THE MISSING LINK. `POST /api/snaptrade/connect` shipped in #334 with zero
 * callers, so `status.registered` was false for every user, so
 * `<PlaceOrder>` (#336) never rendered once. Two merged features waiting on
 * this component.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getSnapTradeStatusMock = vi.fn();
const connectBrokerageMock = vi.fn();
vi.mock("@/lib/api", () => ({
  getSnapTradeStatus: (...a: unknown[]) => getSnapTradeStatusMock(...a),
  connectBrokerage: (...a: unknown[]) => connectBrokerageMock(...a),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

import { ConnectBrokerage } from "../connect-brokerage";

const OFF = {
  configured: false, registered: false, connected_accounts: 0,
  trading_enabled: false, last_synced_at: null,
};
const READY = { ...OFF, configured: true };
const CONNECTED = {
  ...READY, registered: true, connected_accounts: 1,
  last_synced_at: "2026-08-21T21:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  getSnapTradeStatusMock.mockResolvedValue(READY);
  connectBrokerageMock.mockResolvedValue({
    redirect_uri: "https://app.snaptrade.com/connect/abc",
  });
  Object.defineProperty(window, "location", {
    value: { assign: vi.fn() },
    writable: true,
  });
});

describe("ConnectBrokerage", () => {
  it("renders nothing when the integration is switched off", async () => {
    /* Operator state, not user state. A button that 503s on click is worse
     * than no button. */
    getSnapTradeStatusMock.mockResolvedValue(OFF);
    render(<ConnectBrokerage />);
    await waitFor(() => expect(getSnapTradeStatusMock).toHaveBeenCalled());
    expect(screen.queryByTestId("connect-brokerage")).toBeNull();
  });

  it("offers the connection when configured and not yet connected", async () => {
    render(<ConnectBrokerage />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
  });

  it("says Livermore never sees the broker credentials", async () => {
    /* This is the objection that stops people. "Connect your brokerage"
     * sounds like handing over a login to anyone who hasn't thought about
     * it, and the answer has to be on the card, not in a help doc. */
    render(<ConnectBrokerage />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    expect(screen.getByText(/never sees those credentials/i)).toBeTruthy();
    expect(screen.getByText(/not move your money/i)).toBeTruthy();
  });

  it("sends the user to the portal it was given", async () => {
    render(<ConnectBrokerage returnPath="/flow/portfolio_mode?connected=1" />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    fireEvent.click(screen.getByTestId("connect-brokerage-start"));
    await waitFor(() =>
      expect(window.location.assign).toHaveBeenCalledWith(
        "https://app.snaptrade.com/connect/abc",
      ),
    );
  });

  it("REGRESSION: passes a PATH, never a URL", async () => {
    /* The server builds the origin. A full URL from the client would be an
     * open redirect at the moment we've just asked someone to trust us with
     * a brokerage login. */
    render(<ConnectBrokerage returnPath="/flow/portfolio_mode?connected=1" />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    fireEvent.click(screen.getByTestId("connect-brokerage-start"));
    await waitFor(() => expect(connectBrokerageMock).toHaveBeenCalled());
    const [, returnPath] = connectBrokerageMock.mock.calls[0];
    expect(returnPath).toBe("/flow/portfolio_mode?connected=1");
    expect(returnPath).not.toMatch(/^https?:/);
  });

  it("can be declined where it is a peer, not a gate", async () => {
    /* A brokerage login is high-trust and a real share of users decline it
     * on first contact. Declining must cost nothing — the manual paths are
     * untouched. */
    render(<ConnectBrokerage dismissible />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    fireEvent.click(screen.getByTestId("connect-brokerage-dismiss"));
    expect(screen.queryByTestId("connect-brokerage")).toBeNull();
  });

  it("offers no dismissal on a settings surface", async () => {
    // A settings page you can hide a setting on is one that loses it.
    render(<ConnectBrokerage />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    expect(screen.queryByTestId("connect-brokerage-dismiss")).toBeNull();
  });

  it("reports an existing connection instead of re-offering it", async () => {
    getSnapTradeStatusMock.mockResolvedValue(CONNECTED);
    render(<ConnectBrokerage />);
    await waitFor(() => screen.getByTestId("brokerage-connected"));
    expect(screen.getByText(/1 brokerage account connected/i)).toBeTruthy();
    expect(screen.queryByTestId("connect-brokerage-start")).toBeNull();
  });

  it("surfaces a failure instead of stranding the user", async () => {
    connectBrokerageMock.mockRejectedValue(new Error("upstream is down"));
    render(<ConnectBrokerage />);
    await waitFor(() => screen.getByTestId("connect-brokerage"));
    fireEvent.click(screen.getByTestId("connect-brokerage-start"));
    await waitFor(() => screen.getByText(/upstream is down/i));
    expect(window.location.assign).not.toHaveBeenCalled();
  });
});
