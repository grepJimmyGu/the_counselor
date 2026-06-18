/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { MarketSnapshotItem } from "@/lib/contracts";

const getMarketOverviewMock = vi.fn();
vi.mock("@/lib/api", () => ({
  getMarketOverview: (...a: unknown[]) => getMarketOverviewMock(...a),
}));

import { HomeMarketStrip } from "../home-market-strip";

function item(symbol: string, change_pct: number): MarketSnapshotItem {
  return {
    symbol,
    name: symbol,
    last_price: 100,
    change_pct,
    change_abs: change_pct * 100,
    last_date: "2026-06-18",
    sparkline: [1, 2, 3],
  } as unknown as MarketSnapshotItem;
}

describe("HomeMarketStrip", () => {
  beforeEach(() => getMarketOverviewMock.mockReset());

  it("renders the four major indices with labels, signed DoD%, and /stocks links", async () => {
    getMarketOverviewMock.mockResolvedValue([
      item("SPY", 0.0042),
      item("QQQ", 0.0061),
      item("DIA", -0.0013),
      item("IWM", 0.0009),
    ]);
    render(<HomeMarketStrip />);

    await waitFor(() => screen.getByTestId("home-market-strip-SPY"));
    // Friendly index labels, not raw tickers.
    expect(screen.getByText("S&P 500")).toBeTruthy();
    expect(screen.getByText("Nasdaq 100")).toBeTruthy();
    expect(screen.getByText("Dow Jones")).toBeTruthy();
    expect(screen.getByText("Russell 2000")).toBeTruthy();

    // Signed, 2-dp percentages.
    expect(screen.getByText("+0.42%")).toBeTruthy();
    expect(screen.getByText("-0.13%")).toBeTruthy();

    // Each pill links to the asset's analysis page.
    const spy = screen.getByTestId("home-market-strip-SPY") as HTMLAnchorElement;
    expect(spy.getAttribute("href")).toBe("/stocks/SPY");

    // It was queried with the four index ETFs.
    expect(getMarketOverviewMock).toHaveBeenCalledWith([
      "SPY",
      "QQQ",
      "DIA",
      "IWM",
    ]);
  });

  it("colors gainers and losers differently (§3.8)", async () => {
    getMarketOverviewMock.mockResolvedValue([
      item("SPY", 0.01),
      item("QQQ", -0.01),
      item("DIA", 0.0),
      item("IWM", 0.0),
    ]);
    render(<HomeMarketStrip />);
    await waitFor(() => screen.getByTestId("home-market-strip-SPY"));

    const up = screen.getByText("+1.00%");
    const down = screen.getByText("-1.00%");
    expect(up.className).toContain("var(--profit)");
    expect(down.className).toContain("var(--loss)");
  });

  it("renders nothing when the market endpoint returns no data (non-essential accent)", async () => {
    getMarketOverviewMock.mockResolvedValue([]);
    const { container } = render(<HomeMarketStrip />);
    await waitFor(() =>
      expect(screen.queryByTestId("home-market-strip")).toBeNull(),
    );
    expect(container.querySelector('[data-testid="home-market-strip"]')).toBeNull();
  });
});
