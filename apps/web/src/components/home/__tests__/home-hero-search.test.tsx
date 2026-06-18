/** @vitest-environment jsdom */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  searchSymbols: vi.fn(async () => [{ symbol: "NVDA", name: "NVIDIA Corp" }]),
  getCompanyOverview: vi.fn(async () => ({ symbol: "NVDA", name: "NVIDIA Corp" })),
}));
vi.mock("@/lib/useLiveQuotes", () => ({
  useLiveQuotes: () => ({
    quotes: {
      NVDA: {
        symbol: "NVDA",
        price: 887.45,
        change: 10.9,
        change_percent: 1.24,
        name: "NVIDIA Corp",
      },
    },
    loading: false,
  }),
}));
// Stub the heavy reused sections (recharts + self-fetch).
vi.mock("@/components/stocks/evaluation-dashboard", () => ({
  EvaluationDashboard: () => <div data-testid="eval-dashboard" />,
}));
vi.mock("@/components/stocks/business-model-section", () => ({
  BusinessModelSection: () => <div data-testid="biz-model" />,
}));
const startFlowMock = vi.fn();
vi.mock("@/lib/flows/runtime", () => ({
  startFlow: (...a: unknown[]) => startFlowMock(...a),
}));
vi.mock("@/lib/flows/one-asset-mode", () => ({}));

import { HomeHeroSearch } from "../home-hero-search";

describe("HomeHeroSearch", () => {
  it("searches, opens an in-place preview with price + DoD, and exposes both CTAs", async () => {
    render(<HomeHeroSearch />);

    fireEvent.change(screen.getByTestId("home-hero-search-input"), {
      target: { value: "NVDA" },
    });
    fireEvent.click(await screen.findByTestId("home-hero-search-result-NVDA"));

    // Preview renders the reused stock-profile sections.
    await waitFor(() => screen.getByTestId("eval-dashboard"));
    expect(screen.getByTestId("biz-model")).toBeTruthy();

    // Price + day-over-day % (cardinal rule §3.8).
    expect(screen.getByText("$887.45")).toBeTruthy();
    expect(screen.getByTestId("home-hero-quote-change").textContent).toContain(
      "+1.24%",
    );

    // CTA 1 — open full detail in a new tab.
    const link = screen.getByTestId("home-hero-open-detail") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/stocks/NVDA");
    expect(link.getAttribute("target")).toBe("_blank");

    // CTA 2 — apply a strategy launches one_asset_mode with the ticker.
    fireEvent.click(screen.getByTestId("home-hero-apply-strategy"));
    expect(startFlowMock).toHaveBeenCalledWith("one_asset_mode", {
      initialContext: { fromTrigger: "home/hero_preview", ticker: "NVDA" },
    });
  });
});
