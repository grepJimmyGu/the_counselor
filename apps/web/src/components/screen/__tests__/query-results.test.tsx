/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  parseSearch: vi.fn(),
  screenScan: vi.fn(),
  screenCount: vi.fn(),
}));
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));
vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { backendToken: "tok" }, status: "authenticated" }),
}));

import { parseSearch, screenScan, screenCount } from "@/lib/api";
import { QueryResults } from "../query-results";

const parseMock = parseSearch as unknown as ReturnType<typeof vi.fn>;
const scanMock = screenScan as unknown as ReturnType<typeof vi.fn>;
const countMock = screenCount as unknown as ReturnType<typeof vi.fn>;

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
