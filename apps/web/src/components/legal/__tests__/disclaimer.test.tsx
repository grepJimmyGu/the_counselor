/** @vitest-environment jsdom */

/**
 * §11 specified this placement and it was never implemented — the full
 * text existed nowhere a user could reach.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getDisclaimerMock = vi.fn();
vi.mock("@/lib/api", () => ({
  getDisclaimer: () => getDisclaimerMock(),
}));

import { Disclaimer } from "../disclaimer";

const TEXT = {
  short: "Not investment advice. Livermore does not place trades on your behalf.",
  short_digest: "Not investment advice.",
  full: "Research only — not investment advice.\n\nWe can see the holdings you choose to connect. We do not use them to change what any strategy tells you.",
};

beforeEach(() => {
  vi.clearAllMocks();
  getDisclaimerMock.mockResolvedValue(TEXT);
});

describe("Disclaimer", () => {
  it("shows the short form by default", async () => {
    render(<Disclaimer />);
    await waitFor(() => screen.getByTestId("disclaimer"));
    expect(screen.getByText(/does not place trades/i)).toBeTruthy();
    expect(screen.queryByTestId("disclaimer-full")).toBeNull();
  });

  it("expands to the full text on request", async () => {
    render(<Disclaimer />);
    await waitFor(() => screen.getByTestId("disclaimer"));
    fireEvent.click(screen.getByTestId("disclaimer-toggle"));
    expect(screen.getByTestId("disclaimer-full")).toBeTruthy();
    expect(screen.getByText(/do not use them to change/i)).toBeTruthy();
  });

  it("renders nothing rather than an error when the fetch fails", async () => {
    /* A spinner or an error where legal text belongs is worse than absent
     * — it reads as broken exactly where a reader needs confidence. */
    getDisclaimerMock.mockRejectedValue(new Error("offline"));
    render(<Disclaimer />);
    await waitFor(() => expect(getDisclaimerMock).toHaveBeenCalled());
    expect(screen.queryByTestId("disclaimer")).toBeNull();
  });

  it("does not hardcode the wording", async () => {
    /* The text must come from the backend, which is the single source. If
     * someone inlines a copy here it will drift from the emails. */
    getDisclaimerMock.mockResolvedValue({
      ...TEXT, short: "SENTINEL SHORT TEXT",
    });
    render(<Disclaimer />);
    await waitFor(() => screen.getByTestId("disclaimer"));
    expect(screen.getByText(/SENTINEL SHORT TEXT/)).toBeTruthy();
  });
});
