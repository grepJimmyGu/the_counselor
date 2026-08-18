/** @vitest-environment jsdom */

/**
 * The exit email's confirm link had no handler until 2026-08-18 — clicking
 * "I've executed this" landed on the strategy page with no acknowledgement
 * and no route to finish, so the confirm silently did nothing and the
 * position's `shares_remaining` stayed stale.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const markStrategyExecutedMock = vi.fn();
vi.mock("@/lib/api", () => ({
  markStrategyExecuted: markStrategyExecutedMock,
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

const fromEmail = () =>
  searchParamsMock.mockReturnValue(new URLSearchParams("action=executed"));

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
    fromEmail();
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(screen.getByTestId("executed-from-email")).toBeTruthy();
  });

  it("states plainly that Livermore has not sold anything", () => {
    // §11: the prompt must never imply Livermore transacted. Load-bearing.
    fromEmail();
    render(<ExecutedFromEmail strategyId="strat_1" />);
    expect(screen.getByText(/we do not place trades/i)).toBeTruthy();
  });

  it("REGRESSION: never fires the mark-executed METRIC endpoint", () => {
    /* The first version of this component offered a one-click confirm wired
     * to `markStrategyExecuted`. That is the wrong endpoint twice over:
     *
     *   - `/mark-executed` is a retention metric. It writes a
     *     MarkAsExecutedEvent, never touches `shares_remaining`, and 404s
     *     unless a SignalEvent exists — which the position monitors never
     *     write, so on a position-only strategy it fails outright.
     *   - the real confirm, `/positions/{id}/confirm-exit`, needs the
     *     user's actual fill (tier, shares, price). A single button cannot
     *     supply that, and inventing the numbers would write a fill that
     *     never happened into the position's P&L.
     *
     * So this prompt routes to the position card instead of transacting.
     */
    fromEmail();
    render(<ExecutedFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/go to the position/i));
    expect(markStrategyExecutedMock).not.toHaveBeenCalled();
  });

  it("routes the user to the position rather than confirming for them", () => {
    fromEmail();
    const target = document.createElement("div");
    target.setAttribute("data-testid", "active-execution-dashboard");
    target.scrollIntoView = vi.fn();
    document.body.appendChild(target);

    render(<ExecutedFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/go to the position/i));
    expect(target.scrollIntoView).toHaveBeenCalled();

    document.body.removeChild(target);
  });

  it("lets the user say they are holding instead", () => {
    // "Holding" is a legitimate answer, not a failure to comply.
    fromEmail();
    render(<ExecutedFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/i'm holding/i));
    expect(screen.queryByTestId("executed-from-email")).toBeNull();
    expect(markStrategyExecutedMock).not.toHaveBeenCalled();
  });
});
