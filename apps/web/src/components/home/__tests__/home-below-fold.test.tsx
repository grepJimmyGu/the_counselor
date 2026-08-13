/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  getDailyBrief: vi.fn(),
  getScreenerPresets: vi.fn(),
  screenCount: vi.fn(),
  // The block now carries <ShareCardButton>, which imports these. A module
  // mock replaces the WHOLE module, so omitting them makes the button throw
  // on mount and takes the entire block's render down with it.
  getDailyCardLanguages: vi.fn().mockResolvedValue({ languages: ["en"] }),
  createDailyCard: vi.fn(),
  dailyCardImageUrl: () => "http://api.test/card.png",
}));

import { getDailyBrief, getScreenerPresets, screenCount } from "@/lib/api";
import { HomeMarketPulseBlock } from "../home-market-pulse-block";
import { HomeCuratedScreens } from "../home-curated-screens";

const briefMock = getDailyBrief as unknown as ReturnType<typeof vi.fn>;
const presetsMock = getScreenerPresets as unknown as ReturnType<typeof vi.fn>;
const countMock = screenCount as unknown as ReturnType<typeof vi.fn>;

const mover = (symbol: string, change_percent: number) => ({
  symbol,
  name: `${symbol} Inc.`,
  change_percent,
});
const sector = (name: string, change_percent: number, money_flow: number | null = null) => ({
  name,
  change_percent,
  money_flow,
});

function brief(over: Record<string, unknown> = {}) {
  return {
    as_of: "2026-08-09T11:29:43",
    indices: [
      { symbol: "^GSPC", name: "S&P 500", price: 7757.64, change_percent: 0.62 },
      { symbol: "^IXIC", name: "Nasdaq Composite", price: 26690.62, change_percent: 1.3 },
      { symbol: "^DJI", name: "Dow Jones", price: 54036.93, change_percent: 0.28 },
    ],
    vix: { symbol: "^VIX", name: "VIX", price: 14.9, change_percent: -1.65 },
    macro: [
      {
        category: "Inflation",
        label: "CPI YoY: 3.9%",
        direction: "up",
        trend: "Rising",
        takeaway: "Could delay rate cuts",
      },
    ],
    gainers: [mover("TEAM", 35.31), mover("TWLO", 24.89), mover("ABNB", 17.43)],
    losers: [mover("AKAM", -6.76), mover("PARA", -6.04), mover("ZTS", -5.97)],
    sector_leading: sector("Consumer Disc.", 1.49),
    sector_lagging: sector("Energy", -1.13),
    flow_into: sector("Financials", -0.36, 0.1192),
    flow_out_of: sector("Utilities", 0.53, -0.1846),
    unusual: mover("TEAM", 35.31),
    ...over,
  };
}

beforeEach(() => {
  briefMock.mockReset();
  presetsMock.mockReset();
});

describe("HomeMarketPulseBlock", () => {
  it("shows index LEVELS, not ETF share prices", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    // 7,757.64 is the S&P; ~650 would be SPY. An ETF price shown as an index
    // level is wrong, not merely different — and this block gets shared.
    await waitFor(() => expect(screen.getByText("7,757.64")).toBeTruthy());
    expect(screen.getByText("S&P 500")).toBeTruthy();
  });

  it("shows both gainers and losers, each linking to its company page", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(screen.getAllByTestId("brief-mover")).toHaveLength(6));
    expect(screen.getAllByText("TEAM")[0].closest("a")?.getAttribute("href")).toBe("/stocks/TEAM");
    // A block that only ever shows gainers can't answer "what got sold?".
    expect(screen.getByText("AKAM")).toBeTruthy();
  });

  it("leaves VIX uncoloured — it is a level, not a return", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    const vix = await screen.findByTestId("brief-vix");
    // "VIX down 1.65%" is not good news the way "S&P up 0.62%" is, so it must
    // not borrow the green/red coding that means exactly one thing elsewhere.
    expect(vix.className).not.toContain("emerald");
    expect(vix.textContent).toContain("calm");
  });

  it("shows the Chaikin numbers behind the money-flow arrow", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    const flow = await screen.findByTestId("brief-flow");
    // Without the figures, "money flowing X → Y" is an assertion the reader
    // has to take on faith.
    expect(flow.textContent).toContain("-0.18");
    expect(flow.textContent).toContain("0.12");
  });

  it("ranks money flow separately from sector performance", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(screen.getByTestId("brief-flow")).toBeTruthy());
    // Consumer Disc. led on price while money went to Financials. Collapsing
    // the two rankings would make the flow line a restatement.
    expect(screen.getByText("Consumer Disc.")).toBeTruthy();
    expect(screen.getByText("Financials")).toBeTruthy();
  });

  it("keeps sector names linking to the screener", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    // The pre-redesign block had this affordance; dropping a working control
    // in a redesign is a regression even when the new layout is better.
    await waitFor(() =>
      expect(screen.getByText("Energy").closest("a")?.getAttribute("href")).toBe(
        "/stocks?sector=Energy",
      ),
    );
  });

  it("stamps the date above the headline", async () => {
    briefMock.mockResolvedValue(brief());
    render(<HomeMarketPulseBlock />);
    // Product invariant: a calendar anchor is readable at a glance, never
    // buried in muted footer text.
    await waitFor(() => expect(screen.getByTestId("brief-as-of").textContent).toContain("2026-08-09"));
  });

  it("hides the unusual callout on a quiet day", async () => {
    briefMock.mockResolvedValue(brief({ unusual: null }));
    render(<HomeMarketPulseBlock />);
    await waitFor(() => expect(screen.getAllByTestId("brief-mover").length).toBe(6));
    // Flagging the top of a quiet leaderboard as UNUSUAL every session cries
    // wolf, so the backend withholds it and the block must not fake one.
    expect(screen.queryByTestId("brief-unusual")).toBeNull();
  });

  it("says the snapshot failed instead of vanishing from the grid", async () => {
    briefMock.mockRejectedValue(new Error("down"));
    render(<HomeMarketPulseBlock />);
    // The block sits in a 2x2 grid. Removing it entirely reflows the three
    // siblings and leaves no clue anything went wrong; a two-line message
    // keeps the layout and tells the user.
    const el = await screen.findByTestId("home-market-pulse");
    expect(el.textContent).toContain("Couldn't load");
  });
});

describe("HomeCuratedScreens — Hot Market Picks", () => {
  it('is titled "Hot Market Picks"', async () => {
    countMock.mockResolvedValue({ matched_count: 24, universe_size: 525 });
    render(<HomeCuratedScreens />);
    await waitFor(() =>
      expect(screen.getByTestId("home-curated-screens").textContent).toContain(
        "Hot Market Picks",
      ),
    );
  });

  it("lands on the search-results surface, carrying the template and universe", async () => {
    // Not `/stocks`, not an intermediate page. The whole point of routing to
    // `/screen` is that a pick arrives where a typed query arrives, so the
    // user's next move — edit a chip, add a ticker — is the same.
    countMock.mockResolvedValue({ matched_count: 24, universe_size: 525 });
    render(<HomeCuratedScreens />);
    const href = await waitFor(() =>
      screen.getByTestId("home-pick-best_momentum").getAttribute("href"),
    );
    expect(href).toBe("/screen?template=best_momentum&universe=sp500");
  });

  it("shows only the composer picks — the sentiment ones cannot produce a list", async () => {
    countMock.mockResolvedValue({ matched_count: 12, universe_size: 525 });
    render(<HomeCuratedScreens />);
    await waitFor(() => expect(screen.getByTestId("home-pick-best_momentum")).toBeTruthy());
    // `positive_catalyst` routes to the sentiment hub; it belongs in Catalysts.
    expect(screen.queryByTestId("home-pick-positive_catalyst")).toBeNull();
  });

  it("hides a pick matching nothing rather than advertising a zero", async () => {
    countMock.mockImplementation((body: { rules: { primitive_id: string }[] }) =>
      Promise.resolve({
        matched_count: body.rules[0]?.primitive_id === "rank_return_6m" ? 0 : 31,
        universe_size: 525,
      }),
    );
    render(<HomeCuratedScreens />);
    await waitFor(() => expect(screen.getByTestId("home-pick-breakout")).toBeTruthy());
    expect(screen.queryByTestId("home-pick-best_momentum")).toBeNull();
  });

  it("renders nothing when every count fails — five dead cards is worse than none", async () => {
    countMock.mockRejectedValue(new Error("scan down"));
    const { container } = render(<HomeCuratedScreens />);
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
  });
});
