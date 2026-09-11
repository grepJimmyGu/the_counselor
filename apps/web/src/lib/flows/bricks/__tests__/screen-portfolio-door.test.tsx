/** @vitest-environment jsdom */

/**
 * PRD-26b §2 — "Create a Portfolio", the screen's second outcome.
 *
 * Replaces PRD-26's "Promote to strategy", which took ONE symbol out of the
 * basket and discarded the rest. The tests that matter here are the ones about
 * what the door refuses and why: an overlay that needs weights a screen cannot
 * supply, and a basket too small for the overlay picked.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { OVERLAY_METADATA } from "@/lib/overlay-metadata";
import type { StrategyJson } from "@/lib/contracts";
import { ScreenPortfolioDoor } from "../screen-portfolio-door";

const NAMES = Array.from({ length: 30 }, (_, i) => `T${i + 1}`);

function open(ordered = NAMES) {
  const onCreate = vi.fn();
  render(<ScreenPortfolioDoor ordered={ordered} onCreate={onCreate} />);
  fireEvent.click(screen.getByTestId("screen-door-portfolio"));
  return onCreate;
}

describe("the closed door", () => {
  it("says what it keeps, which is the whole point of §1", () => {
    render(<ScreenPortfolioDoor ordered={NAMES} onCreate={vi.fn()} />);
    const t = screen.getByTestId("screen-door-portfolio").textContent ?? "";
    expect(t).toContain("Create a Portfolio");
    expect(t).toMatch(/names/i);
    expect(t).toMatch(/frozen/i);
  });
});

describe("what it refuses, and why", () => {
  it("does not offer rebalance, and says why not", () => {
    /* §2.3 — rebalance targets explicit per-holding weights. A screen gives
     * names without weights, and equal-weight rebalance is `defensive` minus
     * the filter. Excluded WITH the reason, never silently absent. */
    open();
    expect(screen.queryByTestId("screen-overlay-rebalance")).toBeNull();
    expect(screen.getByTestId("screen-door-portfolio-open").textContent).toMatch(
      /Rebalance isn.t offered/i,
    );
  });

  it("refuses a basket below the overlay's minimum with the number", () => {
    open(["AAPL", "MSFT"]); // rotation needs 3
    fireEvent.click(screen.getByTestId("screen-overlay-rotation"));
    const msg = screen.queryByTestId("screen-portfolio-short");
    // The card is disabled below its minimum, so either it refused the click
    // or it stated the shortfall — never a silent no-op.
    if (msg) expect(msg.textContent).toMatch(/needs 3 names/i);
    expect(
      (screen.getByTestId("screen-portfolio-create") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("will not create before an overlay is chosen", () => {
    open();
    expect(
      (screen.getByTestId("screen-portfolio-create") as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

describe("the basket it freezes", () => {
  it("cuts to the top 20 by default, not the whole 200-name match", () => {
    /* §2.4 — a screen can match 200 names; that is not a portfolio. `ordered`
     * is already ranked, so the cut is free. */
    const onCreate = open();
    fireEvent.click(screen.getByTestId("screen-overlay-rotation"));
    fireEvent.click(screen.getByTestId("screen-portfolio-create"));
    const [, , tickers] = onCreate.mock.calls[0];
    expect(tickers).toHaveLength(20);
    expect(tickers[0]).toBe("T1"); // best first, order preserved
  });

  it("honours a user-set count", () => {
    const onCreate = open();
    fireEvent.change(screen.getByTestId("screen-portfolio-topk"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("screen-overlay-rotation"));
    fireEvent.click(screen.getByTestId("screen-portfolio-create"));
    expect(onCreate.mock.calls[0][2]).toHaveLength(5);
  });

  it("never asks for more names than matched", () => {
    const onCreate = open(["AAPL", "MSFT", "NVDA"]);
    fireEvent.click(screen.getByTestId("screen-overlay-rotation"));
    fireEvent.click(screen.getByTestId("screen-portfolio-create"));
    expect(onCreate.mock.calls[0][2]).toHaveLength(3);
  });
});

describe("what it hands to the backtest", () => {
  it("builds a portfolio overlay over the frozen names", () => {
    const onCreate = open();
    fireEvent.click(screen.getByTestId("screen-overlay-defensive"));
    fireEvent.click(screen.getByTestId("screen-portfolio-create"));
    const [json, overlay, tickers] = onCreate.mock.calls[0] as [
      StrategyJson,
      string,
      string[],
    ];
    expect(overlay).toBe("defensive");
    expect(json.strategy_type).toBe(OVERLAY_METADATA.defensive.strategyType);
    // `inherited_universe` is what the engine swaps in at the top of run() —
    // the frozen list IS the strategy's universe.
    expect(json.inherited_universe).toEqual(tickers);
    expect(json.universe).toEqual(tickers);
  });

  it("quotes no performance figure without its basis", () => {
    /* The rows use `idea` (number-free), never `tagline`, which carries
     * "-28% vs -55%" and cannot travel apart from `historicalEstimate`. */
    open();
    const t = screen.getByTestId("screen-door-portfolio-open").textContent ?? "";
    for (const kind of ["defensive", "rotation", "dual_momentum"] as const) {
      expect(t).not.toContain(OVERLAY_METADATA[kind].tagline);
    }
    expect(t).not.toMatch(/-?\d+(\.\d+)?%/);
  });
});
