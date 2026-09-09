/** @vitest-environment jsdom */

/**
 * Home block 3 — Quant Rules.
 *
 * RESTRUCTURED 2026-09-09, and this suite with it. The block used to be
 * "Try a Template" beside three named templates, an overlay section with a
 * six-card expander, and "Build your own signals" at the bottom. It is now
 * two tier-badged entry points and one brokerage row.
 *
 * The tests that covered the overlay cards did NOT go away — the overlay
 * overview moved to the portfolio upload step, and its invariants moved with
 * it (see `lib/flows/bricks/__tests__/portfolio-upload.test.tsx`): how many
 * holdings each needs, no performance figure without its basis, and no claim
 * of portfolio fit. Deleting them here without re-homing them would have
 * quietly dropped three product guarantees.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/lib/flows/runtime", () => ({ startFlow: vi.fn() }));

import { researchTemplates } from "@/lib/contracts";
import { WIZARD_QUESTIONS } from "@/components/strategy-builder/wizard/strategy-wizard-data";
import { startFlow } from "@/lib/flows/runtime";
import {
  HomeQuantStrategies,
  PRIMITIVE_COUNT,
  QUESTION_COUNT,
  TEMPLATE_COUNT,
} from "../home-quant-strategies";

const block = () => screen.getByTestId("home-quant-strategies").textContent ?? "";

describe("the two ways in", () => {
  it("offers exactly two entry points, tiered", () => {
    render(<HomeQuantStrategies />);
    expect(screen.getByTestId("quant-guided-start").textContent).toContain(
      "Start with a Proven Strategy",
    );
    expect(screen.getByTestId("quant-guided-start").textContent).toContain("Entry level");
    expect(screen.getByTestId("quant-build-from-scratch").textContent).toContain(
      "Write Your Own Rules",
    );
    expect(screen.getByTestId("quant-build-from-scratch").textContent).toContain("Expert");
  });

  it("signposts the tiers rather than claiming to gate them", () => {
    /* Nothing stops a beginner opening the composer, so "Expert only" would
     * be a restriction the product does not enforce. */
    render(<HomeQuantStrategies />);
    expect(block()).not.toMatch(/only/i);
  });

  it("sends the guided path to the wizard and the expert path to the composer", () => {
    render(<HomeQuantStrategies />);
    fireEvent.click(screen.getByTestId("quant-guided-start"));
    expect(startFlow).toHaveBeenCalledWith("one_asset_mode", expect.anything());

    fireEvent.click(screen.getByTestId("quant-build-from-scratch"));
    expect(startFlow).toHaveBeenCalledWith(
      "custom_build_mode",
      expect.objectContaining({
        initialContext: expect.objectContaining({ fromTrigger: "home/custom_build" }),
      }),
    );
  });

  it("no longer advertises three templates as if they were a third way in", () => {
    /* They landed in the same wizard the guided card opens, so they competed
     * for the eye without offering a different path. Still reachable from
     * Home's "Popular templates" row. */
    render(<HomeQuantStrategies />);
    const runnable = researchTemplates.filter((t) => t.availability !== "unavailable");
    const t = block();
    for (const tmpl of runnable.slice(0, 3)) expect(t).not.toContain(tmpl.name);
  });
});

describe("the numbers it quotes", () => {
  it("counts the questions the wizard actually asks", () => {
    /* The copy promises five. If a question is added or removed, the copy
     * follows rather than becoming a small lie nobody re-read. */
    render(<HomeQuantStrategies />);
    expect(QUESTION_COUNT).toBe(WIZARD_QUESTIONS.length);
    expect(block()).toContain(`${QUESTION_COUNT} plain questions`);
  });

  it("counts only the templates that can actually be run", () => {
    render(<HomeQuantStrategies />);
    const runnable = researchTemplates.filter((t) => t.availability !== "unavailable");
    expect(TEMPLATE_COUNT).toBe(runnable.length);
    expect(TEMPLATE_COUNT).toBeLessThan(researchTemplates.length); // some ARE unavailable
    expect(block()).toContain(`${TEMPLATE_COUNT}`);
  });

  it("keeps the primitive count in one place, since it can't be derived", () => {
    /* The catalog is served by GET /api/signal-primitives, not bundled, so
     * this is the single line to update — never a literal in the copy. */
    render(<HomeQuantStrategies />);
    expect(block()).toContain(`${PRIMITIVE_COUNT} primitives`);
  });
});

describe("what it promises about money", () => {
  it("never presents a performance claim", () => {
    render(<HomeQuantStrategies />);
    const t = block();
    expect(t).not.toMatch(/CAGR|Sharpe|max drawdown|annualized|annualised/i);
    expect(t).not.toMatch(/(returned|gained|delivered)\s+\d+(\.\d+)?\s*%/i);
  });

  it("makes the guarantee it can keep, not the one that stopped being true", () => {
    /* "Read only" was retired when order placement shipped. What replaced it
     * is stronger and enforced: test_snaptrade_readonly_guard bans
     * `place_force_order` outright and every trading call under `jobs/`, so
     * no order exists that the user did not price and approve. */
    render(<HomeQuantStrategies />);
    const t = block();
    expect(t).not.toMatch(/read[- ]only/i);
    expect(t).toMatch(/without you approving a priced preview/i);
  });
});

describe("the book you already have", () => {
  it("promotes the connection and routes it to the portfolio flow", () => {
    render(<HomeQuantStrategies />);
    const row = screen.getByTestId("quant-connect-brokerage");
    expect(row.textContent).toContain("Connect your brokerage");
    fireEvent.click(row);
    expect(startFlow).toHaveBeenCalledWith(
      "portfolio_mode",
      expect.objectContaining({
        initialContext: expect.objectContaining({ fromTrigger: "home/upload_portfolio" }),
      }),
    );
  });

  it("says the manual path still exists, so the connection reads as a choice", () => {
    render(<HomeQuantStrategies />);
    expect(block()).toMatch(/by hand/i);
  });

  it("does not describe overlays before a portfolio exists", () => {
    /* The overlay overview moved to the upload step for exactly this reason:
     * here it described rules for a book that had not been uploaded. */
    render(<HomeQuantStrategies />);
    expect(screen.queryByTestId("quant-overlay-cards")).toBeNull();
    expect(screen.queryByTestId("quant-overlay-overview")).toBeNull();
  });
});
