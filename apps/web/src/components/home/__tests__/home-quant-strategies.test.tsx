/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/lib/flows/runtime", () => ({ startFlow: vi.fn() }));

import { researchTemplates } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { startFlow } from "@/lib/flows/runtime";
import { HomeQuantStrategies } from "../home-quant-strategies";

function renderBlock() {
  const onOpenTemplate = vi.fn();
  const onBuildFromScratch = vi.fn();
  render(
    <HomeQuantStrategies
      onOpenTemplate={onOpenTemplate}
      onBuildFromScratch={onBuildFromScratch}
    />,
  );
  return { onOpenTemplate, onBuildFromScratch };
}

describe("HomeQuantStrategies", () => {
  it("hides templates that cannot actually be run", () => {
    renderBlock();
    const unavailable = researchTemplates.filter((t) => t.availability === "unavailable");
    expect(unavailable.length).toBeGreaterThan(0); // guard: the fixture still has some
    for (const t of unavailable) {
      // A card you can't run is an advert, not a strategy.
      expect(screen.queryByText(t.name)).toBeNull();
    }
  });

  it("opens the wizard with the chosen template", () => {
    const { onOpenTemplate } = renderBlock();
    const first = researchTemplates.find((t) => t.availability !== "unavailable")!;
    fireEvent.click(screen.getByText(first.name));
    expect(onOpenTemplate).toHaveBeenCalledWith(expect.objectContaining({ id: first.id }));
  });

  it("offers build-from-scratch", () => {
    const { onBuildFromScratch } = renderBlock();
    fireEvent.click(screen.getByTestId("quant-build-from-scratch"));
    expect(onBuildFromScratch).toHaveBeenCalled();
  });

  it("never presents a performance claim", () => {
    renderBlock();
    const text = screen.getByTestId("home-quant-strategies").textContent ?? "";

    // Note this deliberately does NOT ban percentages: strategy descriptions
    // legitimately contain PARAMETERS ("an 8% stop loss", "top 2 by 6-month
    // return"). What must never appear is a claim about how the strategy has
    // PERFORMED — `perfContext` is hand-written prose, and no per-template
    // performance store exists to replace it with.
    expect(text).not.toMatch(/CAGR|Sharpe|max drawdown|annualized|annualised/i);
    // `up N%` is deliberately NOT banned: it appears in illustrative theses
    // ("a stock that drifts up 10% is a smoother ride") and in parameters,
    // neither of which is a claim about how the strategy performed. This
    // over-fired twice before being narrowed — the invariant that actually
    // matters is covered by the vocabulary check above and the perfContext /
    // tagline / fitLabel checks below.
    expect(text).not.toMatch(/(returned|gained|delivered)\s+\d+(\.\d+)?\s*%/i);

    // And the field itself must not leak in verbatim.
    for (const t of researchTemplates) {
      const perf = (t as { perfContext?: string }).perfContext;
      if (perf) expect(text).not.toContain(perf);
    }
  });

  it("shows the evidence tier, which is a sourced claim", () => {
    renderBlock();
    const tiered = researchTemplates.filter(
      (t) => t.availability !== "unavailable" && t.evidenceTier,
    );
    if (tiered.length === 0) return; // nothing to assert on this fixture
    const text = screen.getByTestId("home-quant-strategies").textContent ?? "";
    expect(text).toMatch(/Evidence [ABC]/);
  });

  it("flags an ETF-proxy template on the card, not after the click", () => {
    renderBlock();
    const proxies = researchTemplates.filter((t) => t.availability === "proxy");
    if (proxies.length === 0) return;
    const text = screen.getByTestId("home-quant-strategies").textContent ?? "";
    expect(text).toContain("ETF proxy");
  });
});

describe("the three offerings", () => {
  it("explains how each one differs, since the cards alone don't", () => {
    renderBlock();
    const t = screen.getByTestId("home-quant-strategies").textContent ?? "";
    // The distinction is WHAT each decides for you — the failure mode is a
    // user backtesting an overlay expecting it to pick names.
    expect(t).toMatch(/Templates/);
    expect(t).toMatch(/pick the names for you/i);
    expect(t).toMatch(/Overlays/);
    expect(t).toMatch(/already hold/i);
    expect(t).toMatch(/Build your own/);
    expect(t).toMatch(/raw signals/i);
  });

  it('calls the last one "Build your own signals", not "Build from scratch"', () => {
    renderBlock();
    expect(screen.getByTestId("quant-build-from-scratch").textContent).toContain(
      "Build your own signals",
    );
  });
});

describe("overlays", () => {
  it("offers every overlay, grouped under its own label", () => {
    renderBlock();
    const cards = screen.getAllByTestId("quant-overlay");
    expect(cards.length).toBe(OVERLAY_DISPLAY_ORDER.length);
    expect(screen.getByTestId("home-quant-strategies").textContent).toMatch(
      /Overlays — for a portfolio you already hold/,
    );
  });

  it("starts Portfolio Mode with the overlay ALREADY chosen", () => {
    vi.mocked(startFlow).mockClear();
    renderBlock();
    const first = OVERLAY_DISPLAY_ORDER[0];
    fireEvent.click(screen.getByText(OVERLAY_METADATA[first].label));

    // The whole point of item C: choose here, then upload, then results.
    // The picker seeds from `context.selectedOverlay`, so passing it makes
    // that step a confirm rather than a second decision.
    expect(startFlow).toHaveBeenCalledWith(
      "portfolio_mode",
      expect.objectContaining({
        initialContext: expect.objectContaining({ selectedOverlay: first }),
      }),
    );
  });

  it("says up front how many holdings an overlay needs", () => {
    renderBlock();
    // `OverlayPicker` silently rejects an under-qualified overlay, so a user
    // who picks one with too few holdings would otherwise just find the CTA
    // dead with no explanation.
    const first = OVERLAY_DISPLAY_ORDER[0];
    const card = screen.getByTestId("home-quant-strategies")
      .querySelector(`[data-overlay="${first}"]`);
    expect(card?.textContent).toMatch(
      new RegExp(`Needs ${OVERLAY_METADATA[first].minHoldings}\\+ holding`),
    );
  });

  it("puts no unsourced performance number on an overlay card", () => {
    renderBlock();
    const t = screen.getByTestId("home-quant-strategies").textContent ?? "";
    // `tagline` carries figures like "worst loss -28% vs -55%" with no source
    // in overlay-metadata.ts. Same rule as the template cards.
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      expect(t).not.toContain(OVERLAY_METADATA[kind].tagline);
    }
  });

  it("claims no portfolio fit before a portfolio exists", () => {
    renderBlock();
    const t = screen.getByTestId("home-quant-strategies").textContent ?? "";
    // fitLabel comes from the diagnosis step; on home there is no portfolio.
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      expect(t).not.toContain(OVERLAY_METADATA[kind].fitLabel);
    }
  });
});
