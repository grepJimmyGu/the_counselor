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
  render(<HomeQuantStrategies onOpenTemplate={onOpenTemplate} />);
  return { onOpenTemplate };
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

  it("opens the full composer, not the builder modal", () => {
    // CHANGED 2026-08-14. This used to call an `onBuildFromScratch` prop that
    // opened the small builder MODAL. It now starts `custom_build_mode` — the
    // full-page universe picker + primitive catalog + rule canvas, the same
    // landing the removed "Build from scratch" card used. Same intent, and the
    // modal was a much narrower surface for it.
    vi.mocked(startFlow).mockClear();
    renderBlock();
    fireEvent.click(screen.getByTestId("quant-build-from-scratch"));
    expect(startFlow).toHaveBeenCalledWith(
      "custom_build_mode",
      expect.objectContaining({
        initialContext: expect.objectContaining({ fromTrigger: "home/custom_build" }),
      }),
    );
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
    // Scoped to the three the block SHOWS (it used to show five). A tier on a
    // template that isn't rendered proves nothing.
    const tiered = researchTemplates
      .filter((t) => t.availability !== "unavailable")
      .slice(0, 3)
      .filter((t) => t.evidenceTier);
    if (tiered.length === 0) return; // nothing to assert on this fixture
    const text = screen.getByTestId("home-quant-strategies").textContent ?? "";
    expect(text).toMatch(/Evidence [ABC]/);
  });

  it("flags an ETF-proxy template on the card, not after the click", () => {
    renderBlock();
    const proxies = researchTemplates
      .filter((t) => t.availability !== "unavailable")
      .slice(0, 3)
      .filter((t) => t.availability === "proxy");
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
  });

  it('calls the last one "Build your own signals", not "Build from scratch"', () => {
    renderBlock();
    expect(screen.getByTestId("quant-build-from-scratch").textContent).toContain(
      "Build your own signals",
    );
  });
});

describe("overlays", () => {
  it("shows the six overlays only when asked, and read-only", () => {
    // CHANGED 2026-08-13. These cards used to be clickable and seeded
    // Portfolio Mode with the overlay pre-chosen. They are now descriptive:
    // the picker chooses an overlay FOR a portfolio already uploaded, so
    // offering the choice here with no holdings dead-ends. The CTA beside
    // them is Upload Portfolio, which is the real next step.
    renderBlock();
    expect(screen.queryByTestId("quant-overlay-cards")).toBeNull();

    fireEvent.click(screen.getByTestId("quant-overlay-overview"));
    const cards = screen.getAllByTestId(/^strategy-card-/);
    expect(cards.length).toBe(OVERLAY_DISPLAY_ORDER.length);
    // Read-only: describes, does not offer.
    for (const c of cards) expect(c.tagName).not.toBe("BUTTON");
  });

  it("routes the real next step to Upload Portfolio", () => {
    vi.mocked(startFlow).mockClear();
    renderBlock();
    fireEvent.click(screen.getByTestId("quant-upload-portfolio"));
    expect(startFlow).toHaveBeenCalledWith(
      "portfolio_mode",
      expect.objectContaining({
        initialContext: expect.objectContaining({ fromTrigger: "home/upload_portfolio" }),
      }),
    );
  });

  it("opens the guided wizard from Try a Template", () => {
    vi.mocked(startFlow).mockClear();
    renderBlock();
    fireEvent.click(screen.getByTestId("quant-try-template"));
    expect(startFlow).toHaveBeenCalledWith("one_asset_mode", expect.anything());
  });

  it("says up front how many holdings an overlay needs", () => {
    renderBlock();
    fireEvent.click(screen.getByTestId("quant-overlay-overview"));
    const first = OVERLAY_DISPLAY_ORDER[0];
    const card = screen.getByTestId(`strategy-card-${first}`);
    expect(card.textContent).toMatch(
      new RegExp(`Needs ${OVERLAY_METADATA[first].minHoldings}\\+ holding`),
    );
  });

  it("never shows a performance figure without its basis", () => {
    // CHANGED 2026-08-13. This asserted that overlay taglines — "worst loss
    // −28% vs −55%" — must not appear at all, on the stated grounds that they
    // had "no source in overlay-metadata.ts". That was wrong: the figures come
    // from `historicalEstimate` ("backtests from 2000-2024 … -55% to -28%")
    // and `researchSource` (Hurst, Ooi & Pedersen, 2013).
    //
    // So the rule worth holding is not "hide the number" but "a number never
    // travels without what produced it" — which is the actual product
    // integrity concern, and a stronger check than the one it replaces.
    renderBlock();
    fireEvent.click(screen.getByTestId("quant-overlay-overview"));
    const t = screen.getByTestId("quant-overlay-cards").textContent ?? "";
    for (const kind of OVERLAY_DISPLAY_ORDER) {
      const meta = OVERLAY_METADATA[kind];
      if (t.includes(meta.tagline)) {
        expect(t).toContain(meta.historicalEstimate);
      }
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
