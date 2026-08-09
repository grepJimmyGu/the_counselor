/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  getMarketPulse: vi.fn(),
  getScreenerPresets: vi.fn(),
}));

import { getMarketPulse, getScreenerPresets } from "@/lib/api";
import { HomeMarketPulseBlock } from "../home-market-pulse-block";
import { HomeCuratedScreens } from "../home-curated-screens";

const pulseMock = getMarketPulse as unknown as ReturnType<typeof vi.fn>;
const presetsMock = getScreenerPresets as unknown as ReturnType<typeof vi.fn>;

const sector = (name: string, cmf: number) => ({
  symbol: name.slice(0, 3).toUpperCase(),
  name,
  price: 100,
  perf_1d: 0.01,
  perf_5d: 0.02,
  rs_vs_spy_5d: 0.01,
  cmf_20: cmf,
  volume_ratio: 1,
});

beforeEach(() => {
  pulseMock.mockReset();
  presetsMock.mockReset();
});

describe("HomeMarketPulseBlock", () => {
  it("shows three movers linking to their company pages", async () => {
    pulseMock.mockResolvedValue({
      top_assets: [
        { symbol: "NVDA", name: "NVIDIA", sector: "Tech", price: 218.99, perf_1d: -0.001, cmf_20: 0.1, market_cap: 1 },
        { symbol: "AAPL", name: "Apple", sector: "Tech", price: 230.1, perf_1d: 0.012, cmf_20: 0.2, market_cap: 1 },
        { symbol: "MSFT", name: "Microsoft", sector: "Tech", price: 510.0, perf_1d: 0.004, cmf_20: 0.3, market_cap: 1 },
        { symbol: "EXTRA", name: "Extra", sector: "Tech", price: 1, perf_1d: 0, cmf_20: 0, market_cap: 1 },
      ],
      sectors: [],
    });
    render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(screen.getAllByTestId("pulse-mover")).toHaveLength(3));
    expect(screen.getByText("NVDA").closest("a")?.getAttribute("href")).toBe("/stocks/NVDA");
    expect(screen.queryByText("EXTRA")).toBeNull();
  });

  it("shows money flow and includes an outflow sector, not just inflows", async () => {
    pulseMock.mockResolvedValue({
      top_assets: [],
      sectors: [
        sector("Financials", 0.19),
        sector("Technology", 0.11),
        sector("Industrials", 0.07),
        sector("Energy", 0.05),
        sector("Materials", -0.01),
        sector("Communication", -0.12),
      ],
    });
    render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(screen.getAllByTestId("pulse-sector").length).toBeGreaterThan(0));
    // A block that only ever shows inflow can't answer "what's being sold?".
    expect(screen.getByText("Communication")).toBeTruthy();
    expect(screen.getByText("-0.12")).toBeTruthy();
  });

  it("links a sector to the screener filtered by that sector", async () => {
    pulseMock.mockResolvedValue({ top_assets: [], sectors: [sector("Health Care", 0.09)] });
    render(<HomeMarketPulseBlock />);
    await waitFor(() =>
      expect(screen.getByText("Health Care").closest("a")?.getAttribute("href")).toBe(
        "/stocks?sector=Health%20Care",
      ),
    );
  });

  it("renders nothing when the pulse call fails, rather than an empty shell", async () => {
    pulseMock.mockRejectedValue(new Error("down"));
    const { container } = render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(container.querySelector('[data-testid="home-market-pulse"]')).toBeNull());
  });
});

describe("HomeCuratedScreens", () => {
  const preset = (slug: string, count: number) => ({
    slug,
    title: slug,
    description: "d",
    icon: "X",
    tier: "scout" as const,
    result_count: count,
    sample_tickers: ["AAA", "BBB"],
  });

  it('is titled "Special list"', async () => {
    presetsMock.mockResolvedValue({ presets: [preset("trending-ai", 24)] });
    render(<HomeCuratedScreens />);
    await waitFor(() =>
      expect(screen.getByTestId("home-curated-screens").textContent).toContain("Special list"),
    );
  });

  it("links straight to results — no intermediate page", async () => {
    presetsMock.mockResolvedValue({ presets: [preset("trending-ai", 24)] });
    render(<HomeCuratedScreens />);
    await waitFor(() =>
      expect(screen.getByTestId("curated-screen").getAttribute("href")).toBe(
        "/stocks?preset=trending-ai",
      ),
    );
  });

  it("hides empty presets instead of advertising a zero count", async () => {
    presetsMock.mockResolvedValue({
      presets: [preset("top-value", 0), preset("top-dividend", 68)],
    });
    render(<HomeCuratedScreens />);
    await waitFor(() => expect(screen.getAllByTestId("curated-screen")).toHaveLength(1));
    expect(screen.getByText("top-dividend")).toBeTruthy();
    expect(screen.queryByText("top-value")).toBeNull();
  });
});
