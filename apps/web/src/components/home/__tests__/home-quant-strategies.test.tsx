/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { researchTemplates } from "@/lib/contracts";
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
    expect(text).not.toMatch(/(returned|gained|up)\s+\d+(\.\d+)?\s*%/i);

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
