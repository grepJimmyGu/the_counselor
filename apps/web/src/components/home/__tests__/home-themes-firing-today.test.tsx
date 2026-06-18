/** @vitest-environment jsdom */

import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  runSentimentAnalyze: vi.fn(async () => ({
    candidates: [{ symbol: "AAPL" }, { symbol: "MSFT" }],
    provider_status: {},
    warnings: [],
    toolkit_id: null,
  })),
  screenScan: vi.fn(async () => ({
    matched: ["NVDA", "AVGO", "AMD"],
    matched_count: 3,
    readings: {},
    as_of_date: null,
    universe_size: 500,
    unsupported_primitives: [],
    default_param_primitives: [],
  })),
}));
vi.mock("@/lib/useLiveQuotes", () => ({
  useLiveQuotes: () => ({
    quotes: { NVDA: { symbol: "NVDA", price: 100, change_percent: 1.2 } },
    loading: false,
  }),
}));

import { HomeThemesFiringToday } from "../home-themes-firing-today";

describe("HomeThemesFiringToday", () => {
  it("renders 3 theme cards with live counts + correct routes", async () => {
    render(<HomeThemesFiringToday />);

    expect(screen.getByTestId("home-theme-positive_catalyst")).toBeTruthy();
    expect(screen.getByTestId("home-theme-best_momentum")).toBeTruthy();
    expect(screen.getByTestId("home-theme-news_community_confirmed")).toBeTruthy();

    // Counts resolve: sentiment cards = 2 candidates; the momentum scan = 3 matched.
    await waitFor(() => screen.getByTestId("home-theme-count-best_momentum"));
    expect(
      screen.getByTestId("home-theme-count-best_momentum").textContent,
    ).toContain("3 matches");
    expect(
      screen.getByTestId("home-theme-count-positive_catalyst").textContent,
    ).toContain("2 matches");

    // Routing per §4.2 / §8.
    expect(
      (screen.getByTestId("home-theme-positive_catalyst") as HTMLAnchorElement).getAttribute(
        "href",
      ),
    ).toContain("/sentiment?toolkit=positive_catalyst");
    expect(
      (screen.getByTestId("home-theme-best_momentum") as HTMLAnchorElement).getAttribute(
        "href",
      ),
    ).toContain("template=best_momentum");
    expect(
      (screen.getByTestId("home-theme-news_community_confirmed") as HTMLAnchorElement).getAttribute(
        "href",
      ),
    ).toContain("display=mainstream_buyers");
  });
});
