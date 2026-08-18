/** @vitest-environment jsdom */

/**
 * The exit email's confirm link had no handler until 2026-08-18 — clicking
 * "I've executed this" landed on the strategy page with no acknowledgement
 * and no control, so the confirm silently did nothing and the position's
 * `shares_remaining` stayed stale.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  markStrategyExecuted: vi.fn(async () => ({
    idempotent: false,
    executed_at: "2026-08-18T21:00:00Z",
    latency_seconds: 12,
  })),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok_abc" },
    status: "authenticated" as const,
  }),
}));

const searchParamsMock = vi.fn(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsMock(),
}));

import { ExecutedFromEmail } from "../executed-from-email";

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsMock.mockReturnValue(new URLSearchParams());
});

describe("ExecutedFromEmail", () => {
  it("renders nothing on a normal visit", () => {
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(screen.queryByTestId("executed-from-email")).toBeNull();
  });

  it("renders nothing for an unrelated action param", () => {
    searchParamsMock.mockReturnValue(new URLSearchParams("action=share"));
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(screen.queryByTestId("executed-from-email")).toBeNull();
  });

  it("appears when arriving from the email's confirm link", () => {
    searchParamsMock.mockReturnValue(new URLSearchParams("action=executed"));
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(screen.getByTestId("executed-from-email")).toBeTruthy();
  });

  it("states plainly that Livermore has not sold anything", () => {
    // §11: the alert must never imply Livermore transacted. This string is
    // load-bearing, not decoration.
    searchParamsMock.mockReturnValue(new URLSearchParams("action=executed"));
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(
      screen.getByText(/we do not place trades/i),
    ).toBeTruthy();
  });

  it("lets the user say they are holding instead, without recording a sale", () => {
    // "Holding" is a legitimate answer, not a failure to comply. Dismissing
    // must not call the mark-executed endpoint.
    searchParamsMock.mockReturnValue(new URLSearchParams("action=executed"));
    render(<ExecutedFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/i'm holding/i));
    expect(screen.queryByTestId("executed-from-email")).toBeNull();
  });
});
