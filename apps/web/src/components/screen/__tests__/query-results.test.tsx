/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  parseSearch: vi.fn(),
  screenScan: vi.fn(),
  screenCount: vi.fn(),
  getFundamentalsBySymbols: vi.fn(),
  getMetricValues: vi.fn(),
}));
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));
vi.mock("@/lib/useLiveQuotes", () => ({
  useLiveQuotes: (syms: string[]) => ({
    quotes: Object.fromEntries(
      syms.map((s, i) => [
        s,
        {
          symbol: s,
          name: `${s} Inc.`,
          price: 100 + i * 10,
          change: 1,
          change_percent: i === 0 ? 1.5 : -2.25,
          market_cap: (i + 1) * 1e12,
          volume: (i + 1) * 1e6,
          day_high: null, day_low: null, exchange: "NASDAQ", fetched_at: 0,
        },
      ]),
    ),
  }),
}));
vi.mock("@/components/search/smart-search-box", () => ({
  SmartSearchBox: () => <div data-testid="stub-search-box" />,
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { backendToken: "tok" }, status: "authenticated" }),
}));

import {
  parseSearch,
  screenScan,
  screenCount,
  getFundamentalsBySymbols,
  getMetricValues,
} from "@/lib/api";
import { QueryResults } from "../query-results";

const parseMock = parseSearch as unknown as ReturnType<typeof vi.fn>;
const scanMock = screenScan as unknown as ReturnType<typeof vi.fn>;
const countMock = screenCount as unknown as ReturnType<typeof vi.fn>;
const fundMock = getFundamentalsBySymbols as unknown as ReturnType<typeof vi.fn>;
const metricMock = getMetricValues as unknown as ReturnType<typeof vi.fn>;

const RULES = [
  { primitive_id: "rsi", operator: "lt", threshold: 30 },
  { primitive_id: "price_above_ma", operator: "is_true" },
];

function parsedOk() {
  return {
    intent: "screen",
    query: "oversold and above the 200-day",
    note: "Screened the S&P 500.",
    confidence: 0.8,
    options: [],
    screen: {
      universe_id: "sp500",
      rules: RULES,
      readings: ["RSI below 30 (oversold)", "price above the 200-day average"],
      symbols: [],
      fundamental_filters: [],
      screener_params: {},
    },
  };
}

function scanned() {
  return {
    matched: ["AAPL", "MSFT", "JPM"],
    readings: {
      AAPL: ["RSI below 30 (oversold)", "price above the 200-day average"],
      MSFT: ["RSI below 30 (oversold)"],
      JPM: ["price above the 200-day average"],
    },
    values: {
      AAPL: { rsi: 25.0, price_above_ma: 1 },
      MSFT: { rsi: 28.5 },
      JPM: { price_above_ma: 1 },
    },
    as_of_date: "2026-08-08",
    universe_size: 525,
    matched_count: 3,
    unsupported_primitives: [],
    default_param_primitives: [],
  };
}

beforeEach(() => {
  parseMock.mockReset();
  scanMock.mockReset();
  countMock.mockReset();
  pushMock.mockReset();
  fundMock.mockReset();
  metricMock.mockReset();
});

describe("QueryResults", () => {
  it("shows the VALUE each name scored, one column per condition", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100, universe_size: 525 });

    render(<QueryResults query="oversold and above the 200-day" universeId="sp500" />);

    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
    // "Each with relative conditions details" — the number, not just a label.
    // A list saying AAPL matched "RSI below 30" doesn't tell you it scored 25
    // while MSFT scraped in at 28.5.
    const rsiCells = screen.getAllByTestId("cell-rsi").map((c) => c.textContent);
    expect(rsiCells).toContain("25.00");
    expect(rsiCells).toContain("28.50");
  });

  it("renders an absent value as an em dash, never as zero", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));

    // JPM has no rsi. Showing 0.00 would read as a real measurement and sort
    // as the lowest value in the set.
    expect(screen.getAllByTestId("cell-rsi").map((c) => c.textContent)).toContain("—");
  });

  it("sorts by a condition column, and unknowns sink in both directions", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));

    fireEvent.click(screen.getByTestId("sort-rsi"));           // desc first
    let order = screen.getAllByTestId("result-row").map((r) => r.textContent?.slice(0, 8));
    expect(order[0]).toContain("MSFT");                        // 28.5 > 25
    expect(order[2]).toContain("JPM");                         // no value → last

    fireEvent.click(screen.getByTestId("sort-rsi"));           // toggle to asc
    order = screen.getAllByTestId("result-row").map((r) => r.textContent?.slice(0, 8));
    expect(order[0]).toContain("AAPL");                        // 25 < 28.5
    // Still last: an unknown is not the smallest value.
    expect(order[2]).toContain("JPM");
  });

  it("offers a way to ADD a condition, not just remove one", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });

    render(<QueryResults query="oversold" universeId="sp500" />);
    // Without this the page is a dead end — you can narrow a screen but never
    // widen it except by starting over.
    await waitFor(() =>
      expect(screen.getByTestId("add-condition").getAttribute("href")).toContain("q=oversold"),
    );
  });

  it("counts every condition IN PARALLEL, not one after another", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    const started: number[] = [];
    countMock.mockImplementation(() => {
      started.push(Date.now());
      return new Promise((res) => setTimeout(() => res({ matched_count: 7 }), 20));
    });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(countMock).toHaveBeenCalledTimes(2));

    // /api/screen/count is ~1.9s warm. Serial counting would make a
    // six-condition page a twelve-second wait.
    expect(Math.max(...started) - Math.min(...started)).toBeLessThan(15);
  });

  it("counts each condition ALONE, not cumulatively", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 7 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(countMock).toHaveBeenCalledTimes(2));

    for (const call of countMock.mock.calls) {
      expect(call[0].rules).toHaveLength(1);
    }
  });

  it("marks a failed count instead of spinning forever", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockImplementation(() => Promise.reject(new Error("nope")));

    render(<QueryResults query="q" universeId="sp500" />);
    // A chip stuck on "…" reads as the page being broken.
    await waitFor(() =>
      expect(screen.getAllByTestId("condition-chip")[0].textContent).toContain("(—)"),
    );
  });

  it("dropping a condition re-runs with the rest", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 7 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("condition-chip")).toHaveLength(2));

    fireEvent.click(screen.getByLabelText("Remove RSI below 30 (oversold)"));
    expect(pushMock).toHaveBeenCalledWith(
      expect.stringContaining("price%20above%20the%20200-day%20average"),
    );
    // The dropped one must not survive into the new query.
    expect(pushMock.mock.calls[0][0]).not.toContain("oversold");
  });

  it("a row leads to that stock's page", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 7 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row").length).toBe(3));

    fireEvent.click(screen.getAllByTestId("result-row")[0]);
    // query -> results -> click -> /stocks/[ticker], per Jimmy's routing.
    expect(pushMock).toHaveBeenCalledWith("/stocks/AAPL");
  });

  it("surfaces primitives that could not be screened", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue({ ...scanned(), unsupported_primitives: ["fcf_yield"] });
    countMock.mockResolvedValue({ matched_count: 7 });

    render(<QueryResults query="q" universeId="sp500" />);
    // Otherwise a short result reads as "nothing qualifies" when really a
    // condition was never evaluated.
    await waitFor(() =>
      expect(screen.getByTestId("unsupported-warning").textContent).toContain("fcf_yield"),
    );
  });

  it("explains itself when the query isn't a screen", async () => {
    parseMock.mockResolvedValue({
      intent: "ambiguous",
      query: "???",
      note: "Which strategy type should I use?",
      confidence: 0.3,
      options: [],
    });

    render(<QueryResults query="???" universeId="sp500" />);
    await waitFor(() =>
      expect(screen.getByText("Which strategy type should I use?")).toBeTruthy(),
    );
    expect(screen.queryAllByTestId("result-row")).toHaveLength(0);
  });
});

describe("default metrics and paging", () => {
  it("keeps the search box on the page", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    // Spec item 1: editable in place, not "go back to change it".
    await waitFor(() => expect(screen.getByTestId("stub-search-box")).toBeTruthy());
  });

  it("shows price, change %, market cap and volume on every row", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);

    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
    // Present regardless of what was screened — without them a row is a score
    // with no anchor.
    expect(screen.getAllByTestId("cell-price")[0].textContent).toBe("100.00");
    expect(screen.getAllByTestId("cell-change_percent")[0].textContent).toBe("+1.50%");
    expect(screen.getAllByTestId("cell-market_cap")[0].textContent).toBe("1.00T");
    expect(screen.getAllByTestId("cell-volume")[0].textContent).toBe("1.0M");
  });

  it("sorts on a quote metric across the whole result, not just the page", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));

    fireEvent.click(screen.getByTestId("sort-market_cap"));
    const caps = screen.getAllByTestId("cell-market_cap").map((c) => c.textContent);
    expect(caps).toEqual(["3.00T", "2.00T", "1.00T"]); // desc
  });

  it("offers feedback actions under the table", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getByTestId("result-feedback")).toBeTruthy());
    expect(screen.getByLabelText("Share this screen")).toBeTruthy();
    expect(screen.getByLabelText("These results look wrong")).toBeTruthy();
  });

  it("shows no pager when everything fits on one screen", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
    expect(screen.queryByTestId("pagination")).toBeNull();
  });
});

describe("paging at 25 per screen", () => {
  const many = (n: number) => ({
    matched: Array.from({ length: n }, (_, i) => `S${i}`),
    readings: {},
    values: Object.fromEntries(
      Array.from({ length: n }, (_, i) => [`S${i}`, { rsi: 10 + i }]),
    ),
    as_of_date: "2026-08-08",
    universe_size: 525,
    matched_count: n,
    unsupported_primitives: [],
    default_param_primitives: [],
  });

  it("caps a screen at 25 rows and pages the rest", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(many(60));
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);

    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(25));
    expect(screen.getByTestId("page-indicator").textContent).toBe("1 / 3");

    fireEvent.click(screen.getByLabelText("Next page"));
    await waitFor(() => expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 3"));
    expect(screen.getAllByTestId("result-row")).toHaveLength(25);

    fireEvent.click(screen.getByLabelText("Next page"));
    await waitFor(() => expect(screen.getByTestId("page-indicator").textContent).toBe("3 / 3"));
    expect(screen.getAllByTestId("result-row")).toHaveLength(10);
  });

  it("row numbers continue across pages", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(many(60));
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(25));

    fireEvent.click(screen.getByLabelText("Next page"));
    // Restarting at 1 on page 2 would misrepresent rank in a ranked list.
    await waitFor(() =>
      expect(screen.getAllByTestId("result-row")[0].textContent).toContain("26"),
    );
  });

  it("returns to page 1 when the sort changes", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(many(60));
    countMock.mockResolvedValue({ matched_count: 100 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getByTestId("page-indicator").textContent).toBe("1 / 3"));

    fireEvent.click(screen.getByLabelText("Next page"));
    await waitFor(() => expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 3"));

    fireEvent.click(screen.getByTestId("sort-rsi"));
    // Re-ranking while parked on page 2 would show an arbitrary slice of a
    // list the user just asked to reorder.
    await waitFor(() => expect(screen.getByTestId("page-indicator").textContent).toBe("1 / 3"));
  });
});

describe("a null value must not take the page down", () => {
  it("renders null and NaN as an em dash instead of throwing", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue({
      ...scanned(),
      // The cell checked `undefined` only, so a null threw
      // "Cannot read properties of null (reading 'toFixed')" and the whole
      // results page went blank. One missing number should never do that.
      values: { AAPL: { rsi: null as unknown as number }, MSFT: { rsi: NaN }, JPM: {} },
    });
    countMock.mockResolvedValue({ matched_count: 100 });

    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
    expect(screen.getAllByTestId("cell-rsi").map((c) => c.textContent)).toEqual([
      "—", "—", "—",
    ]);
  });
});

/**
 * The additional-metrics picker (spec item 3): the user adds fundamental /
 * technical columns and can then filter AND rank on them.
 */
describe("QueryResults — additional metrics", () => {
  const setup = async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100, universe_size: 525 });
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
  };

  const addMetric = async (key: string) => {
    fireEvent.click(screen.getByTestId("metric-picker-toggle"));
    fireEvent.click(await screen.findByTestId(`metric-option-${key}`));
  };

  it("adds a fundamental column and fills it from the by-symbols endpoint", async () => {
    fundMock.mockResolvedValue({
      results: [
        { symbol: "AAPL", name: "Apple", pe_ratio: 30.5, dividend_yield: 0.005 },
        { symbol: "MSFT", name: "Microsoft", pe_ratio: 27.76, dividend_yield: 0.0071 },
      ],
      total: 2,
      offset: 0,
      limit: 2,
      filters_applied: {},
    });
    await setup();
    await addMetric("pe_ratio");

    await waitFor(() =>
      expect(screen.getAllByTestId("cell-pe_ratio").map((c) => c.textContent)).toContain("30.50"),
    );
    // Asked for exactly the names on screen — not a filter re-derivation that
    // could return a different set than the one displayed.
    expect(fundMock).toHaveBeenCalledWith(["AAPL", "MSFT", "JPM"]);
  });

  it("renders dividend yield as a percent, from the stored fraction", async () => {
    fundMock.mockResolvedValue({
      results: [{ symbol: "AAPL", name: "Apple", dividend_yield: 0.0071 }],
      total: 1,
      offset: 0,
      limit: 1,
      filters_applied: {},
    });
    await setup();
    await addMetric("dividend_yield");

    // 0.71%, not 0.01% and not 71%. The store holds a FRACTION — the units bug
    // this pins is the one that made "dividend yield above 4%" return every
    // payer while looking like it worked.
    await waitFor(() =>
      expect(screen.getAllByTestId("cell-dividend_yield").map((c) => c.textContent)).toContain(
        "0.71%",
      ),
    );
  });

  it("adds a technical column from the snapshot without re-running the scan", async () => {
    metricMock.mockResolvedValue({
      values: { AAPL: { adx: 31.2 }, MSFT: { adx: 18.4 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    scanMock.mockClear();
    await addMetric("adx");

    await waitFor(() =>
      expect(screen.getAllByTestId("cell-adx").map((c) => c.textContent)).toContain("31.2"),
    );
    // A re-scan could return a DIFFERENT matched set than the one on screen if
    // the snapshot rolled over between the two calls.
    expect(scanMock).not.toHaveBeenCalled();
  });

  it("filters the full match list on an added metric, not just the visible page", async () => {
    metricMock.mockResolvedValue({
      values: { AAPL: { adx: 31.2 }, MSFT: { adx: 18.4 }, JPM: { adx: 40.0 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    await addMetric("adx");
    await waitFor(() => expect(screen.getAllByTestId("cell-adx")).toHaveLength(3));

    fireEvent.click(screen.getByTestId("metric-filter-toggle"));
    fireEvent.change(screen.getByTestId("metric-filter-key"), { target: { value: "adx" } });
    fireEvent.change(screen.getByTestId("metric-filter-min"), { target: { value: "30" } });
    fireEvent.click(screen.getByTestId("metric-filter-apply"));

    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(2));
    // The headline count still describes the SCREEN; the filtered count is
    // stated separately rather than overwriting it.
    expect(screen.getByTestId("match-count").textContent).toContain("3 match");
    expect(screen.getByTestId("filtered-count").textContent).toContain("2 after filters");
  });

  it("excludes names with no value for a filtered metric", async () => {
    metricMock.mockResolvedValue({
      // MSFT has no ADX at all.
      values: { AAPL: { adx: 31.2 }, JPM: { adx: 40.0 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    await addMetric("adx");
    fireEvent.click(screen.getByTestId("metric-filter-toggle"));
    fireEvent.change(screen.getByTestId("metric-filter-key"), { target: { value: "adx" } });
    fireEvent.change(screen.getByTestId("metric-filter-min"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("metric-filter-apply"));

    // A name we can't evaluate hasn't met the bound — keeping it would put a
    // row in a filtered list that visibly doesn't qualify.
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(2));
  });

  it("ranks on an added metric", async () => {
    metricMock.mockResolvedValue({
      values: { AAPL: { adx: 31.2 }, MSFT: { adx: 18.4 }, JPM: { adx: 40.0 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    await addMetric("adx");
    await waitFor(() => expect(screen.getAllByTestId("cell-adx")).toHaveLength(3));

    fireEvent.click(screen.getByTestId("sort-adx"));
    await waitFor(() =>
      expect(screen.getAllByTestId("cell-adx").map((c) => c.textContent)).toEqual([
        "40.0",
        "31.2",
        "18.4",
      ]),
    );
  });

  it("removing a column drops its filter with it", async () => {
    metricMock.mockResolvedValue({
      values: { AAPL: { adx: 31.2 }, MSFT: { adx: 18.4 }, JPM: { adx: 40.0 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    await addMetric("adx");
    fireEvent.click(screen.getByTestId("metric-filter-toggle"));
    fireEvent.change(screen.getByTestId("metric-filter-key"), { target: { value: "adx" } });
    fireEvent.change(screen.getByTestId("metric-filter-min"), { target: { value: "30" } });
    fireEvent.click(screen.getByTestId("metric-filter-apply"));
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(2));

    fireEvent.click(screen.getByTestId("remove-metric-adx"));
    // A filter left behind would keep hiding a third of the table with nothing
    // on screen explaining why.
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));
    expect(screen.queryByTestId("metric-filter-adx")).toBeNull();
  });

  it("says so when the snapshot can't serve a requested metric", async () => {
    metricMock.mockResolvedValue({ values: {}, as_of_date: null, unavailable: ["adx"] });
    await setup();
    await addMetric("adx");

    // An empty column would claim these stocks have no ADX, which is a
    // different — and false — statement than "we don't carry it".
    await waitFor(() =>
      expect(screen.getByTestId("unavailable-metrics-warning").textContent).toContain("adx"),
    );
  });

  it("doesn't offer a metric that's already a screened-condition column", async () => {
    await setup();
    fireEvent.click(screen.getByTestId("metric-picker-toggle"));
    await screen.findByTestId("metric-picker-panel");
    // The query screens on RSI, so RSI is already a column. Offering it again
    // would add a second identical one.
    expect(screen.queryByTestId("metric-option-rsi")).toBeNull();
    expect(screen.getByTestId("metric-option-adx")).toBeTruthy();
  });

  it("explains the empty table when filters, not conditions, emptied it", async () => {
    metricMock.mockResolvedValue({
      values: { AAPL: { adx: 5 }, MSFT: { adx: 6 }, JPM: { adx: 7 } },
      as_of_date: "2026-08-08",
      unavailable: [],
    });
    await setup();
    await addMetric("adx");
    fireEvent.click(screen.getByTestId("metric-filter-toggle"));
    fireEvent.change(screen.getByTestId("metric-filter-key"), { target: { value: "adx" } });
    fireEvent.change(screen.getByTestId("metric-filter-min"), { target: { value: "90" } });
    fireEvent.click(screen.getByTestId("metric-filter-apply"));

    // Pointing at conditions here would send the user to widen something that
    // isn't the cause.
    await waitFor(() =>
      expect(screen.getByText(/Loosen a metric filter/)).toBeTruthy(),
    );
  });
});

describe("QueryResults — metric source failures", () => {
  it("distinguishes a failed fetch from an absent value", async () => {
    parseMock.mockResolvedValue(parsedOk());
    scanMock.mockResolvedValue(scanned());
    countMock.mockResolvedValue({ matched_count: 100 });
    metricMock.mockRejectedValue(new Error("503"));
    render(<QueryResults query="q" universeId="sp500" />);
    await waitFor(() => expect(screen.getAllByTestId("result-row")).toHaveLength(3));

    fireEvent.click(screen.getByTestId("metric-picker-toggle"));
    fireEvent.click(await screen.findByTestId("metric-option-adx"));

    // Both an outage and a genuinely missing value render em dashes. Without
    // this the user reads a backend failure as "these stocks have no ADX".
    await waitFor(() =>
      expect(screen.getByTestId("metric-fetch-failed").textContent).toContain("technical"),
    );
  });
});
