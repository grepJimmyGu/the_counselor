/** @vitest-environment jsdom */

/**
 * Stored results were deliberately not re-run when the backtest
 * methodology changed on 2026-08-18 — rewriting someone's saved backtest
 * without asking is worse than a visible stamp. This note is what stops
 * that decision from becoming a silent trap when a user re-runs an old
 * strategy and the figures no longer match their own card.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MethodologyNote } from "../methodology-note";

describe("MethodologyNote", () => {
  it("names the methodology when a result carries one", () => {
    render(<MethodologyNote version="2026.08.18" />);
    expect(screen.getByText("2026.08.18")).toBeTruthy();
    expect(screen.getByTestId("methodology-note").textContent).toMatch(
      /next session/i,
    );
  });

  it("says a pre-versioning result is GROSS of costs", () => {
    // The load-bearing case. An old result looks better than a fresh run of
    // the same strategy, and the reason must be on screen.
    render(<MethodologyNote version={null} />);
    const text = screen.getByTestId("methodology-note").textContent ?? "";
    expect(text).toMatch(/gross of costs/i);
  });

  it("warns that a fresh run will report lower figures", () => {
    render(<MethodologyNote version={undefined} />);
    expect(screen.getByTestId("methodology-note").textContent).toMatch(
      /lower/i,
    );
  });

  it("never claims an unversioned result used the current methodology", () => {
    render(<MethodologyNote version={null} />);
    expect(screen.queryByText("2026.08.18")).toBeNull();
  });
});
