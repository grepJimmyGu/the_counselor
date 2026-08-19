/** @vitest-environment jsdom */

/**
 * Entry signals have always been detected — `flip_to_long` emails and
 * banners like any other change. Until 2026-08-19 the action link pointed
 * at `?action=executed`, so the user met the EXIT prompt: "nothing has been
 * sold… confirm what you sold."
 *
 * The consequence was structural, not cosmetic. An entry that never becomes
 * a declared position is invisible to the exit monitor, so the ladder the
 * user configured never runs on the trade it was configured for.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const searchParamsMock = vi.fn(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsMock(),
}));

import { EnteredFromEmail } from "../entered-from-email";

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsMock.mockReturnValue(new URLSearchParams());
});

describe("EnteredFromEmail", () => {
  it("renders nothing on a normal visit", () => {
    render(<EnteredFromEmail strategyId="strat_1" />);
    expect(screen.queryByTestId("entered-from-email")).toBeNull();
  });

  it("does NOT render for an exit link", () => {
    // The two prompts must not both fire — an exit is not an entry.
    searchParamsMock.mockReturnValue(new URLSearchParams("action=executed"));
    render(<EnteredFromEmail strategyId="strat_1" />);
    expect(screen.queryByTestId("entered-from-email")).toBeNull();
  });

  it("appears when arriving from an entry signal", () => {
    searchParamsMock.mockReturnValue(new URLSearchParams("action=entered"));
    render(<EnteredFromEmail strategyId="strat_1" />);
    expect(screen.getByTestId("entered-from-email")).toBeTruthy();
  });

  it("states that Livermore did not buy anything", () => {
    // §11: never imply Livermore transacted, in either direction.
    searchParamsMock.mockReturnValue(new URLSearchParams("action=entered"));
    render(<EnteredFromEmail strategyId="strat_1" />);
    expect(screen.getByText(/we do not place trades/i)).toBeTruthy();
  });

  it("explains that recording is what starts the ladder watching", () => {
    /* The reason this prompt exists. Without a declared position the exit
     * monitor never sees the trade. */
    searchParamsMock.mockReturnValue(new URLSearchParams("action=entered"));
    render(<EnteredFromEmail strategyId="strat_1" />);
    expect(screen.getByText(/starts the exit ladder watching/i)).toBeTruthy();
  });

  it("routes to the declare form rather than inventing a fill", () => {
    /* Declaring needs the user's real shares and entry price. Seeding those
     * would start the ladder against a position that never existed. */
    searchParamsMock.mockReturnValue(new URLSearchParams("action=entered"));
    const target = document.createElement("div");
    target.setAttribute("data-testid", "active-execution-dashboard");
    target.scrollIntoView = vi.fn();
    document.body.appendChild(target);

    render(<EnteredFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/record the position/i));
    expect(target.scrollIntoView).toHaveBeenCalled();

    document.body.removeChild(target);
  });

  it("lets the user say they didn't take the entry", () => {
    // Not taking a signal is an ordinary decision, not non-compliance.
    searchParamsMock.mockReturnValue(new URLSearchParams("action=entered"));
    render(<EnteredFromEmail strategyId="strat_1" />);
    fireEvent.click(screen.getByText(/i didn't take it/i));
    expect(screen.queryByTestId("entered-from-email")).toBeNull();
  });
});
