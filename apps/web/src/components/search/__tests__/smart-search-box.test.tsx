/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  parseSearch: vi.fn(),
  searchSymbols: vi.fn().mockResolvedValue([]),
  getCompanyOverview: vi.fn().mockRejectedValue(new Error("no overview")),
  listSavedScreens: vi.fn(),
}));
vi.mock("@/lib/flows/launch-screen", () => ({
  launchScreenFromParsedRules: vi.fn(),
}));
vi.mock("@/lib/flows/runtime", () => ({ startFlow: vi.fn() }));
vi.mock("@/lib/flows/one-asset-mode", () => ({}));
vi.mock("@/lib/useLiveQuotes", () => ({ useLiveQuotes: () => ({ quotes: {} }) }));
vi.mock("@/components/stocks/evaluation-dashboard", () => ({
  EvaluationDashboard: () => null,
}));
vi.mock("@/components/stocks/business-model-section", () => ({
  BusinessModelSection: () => null,
}));
// The builder calls the live-count endpoint on selection; stub it and expose a
// pick button so the Conditions wiring is still exercised here. The builder's
// own behaviour is covered in condition-builder.test.tsx.
vi.mock("@/components/search/condition-builder", () => ({
  ConditionBuilder: ({ onAppend, universeId }: { onAppend: (p: string) => void; universeId?: string }) => (
    <button data-testid="stub-pick" data-universe={universeId} onClick={() => onAppend("oversold")}>
      pick
    </button>
  ),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({ useSession: () => useSessionMock() }));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

import { listSavedScreens, parseSearch } from "@/lib/api";
import { launchScreenFromParsedRules } from "@/lib/flows/launch-screen";
import { SmartSearchBox } from "../smart-search-box";

const parseMock = parseSearch as unknown as ReturnType<typeof vi.fn>;
const launchMock = launchScreenFromParsedRules as unknown as ReturnType<typeof vi.fn>;
const savedMock = listSavedScreens as unknown as ReturnType<typeof vi.fn>;

function submit(text: string) {
  const input = screen.getByTestId("smart-search-input");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
}

beforeEach(() => {
  vi.clearAllMocks();
  launchMock.mockResolvedValue(true);
  savedMock.mockResolvedValue({ screens: [] });
  useSessionMock.mockReturnValue({
    data: { backendToken: "tok" },
    status: "authenticated",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SmartSearchBox routing", () => {
  it("routes a COMPANY result to the in-place preview", async () => {
    parseMock.mockResolvedValue({
      intent: "company",
      query: "nvidia",
      symbol: "NVDA",
      company_name: "NVIDIA Corp",
      options: [],
      confidence: 0.9,
    });
    render(<SmartSearchBox />);
    submit("nvidia");
    await waitFor(() => expect(screen.getByTestId("smart-search-preview")).toBeTruthy());
    expect(screen.getByText("NVDA")).toBeTruthy();
    expect(launchMock).not.toHaveBeenCalled();
  });

  it("routes a SCREEN result into the composer via parsed rules", async () => {
    const rules = [{ primitive_id: "rsi", operator: "lt", threshold: 30 }];
    parseMock.mockResolvedValue({
      intent: "screen",
      query: "oversold names",
      screen: { universe_id: "sp500", rules },
      strategy_json: { rules },
      options: [],
      note: "Screened the S&P 500 …",
      confidence: 0.7,
    });
    render(<SmartSearchBox />);
    submit("oversold names above their 200 day");
    await waitFor(() =>
      expect(launchMock).toHaveBeenCalledWith(
        rules,
        "sp500",
        undefined,          // technical-only → no pre-narrowed universe
        "Screened the S&P 500 …",
      ),
    );
    // Launch navigates away — no "ask" note on the happy path.
    expect(screen.queryByTestId("smart-search-note")).toBeNull();
  });

  it("shows an ask-note for an AMBIGUOUS result (never guesses)", async () => {
    parseMock.mockResolvedValue({
      intent: "ambiguous",
      query: "do something",
      options: [],
      note: "Try naming an indicator, e.g. RSI below 30.",
      confidence: 0.3,
    });
    render(<SmartSearchBox />);
    submit("do something");
    await waitFor(() => expect(screen.getByTestId("smart-search-note")).toBeTruthy());
    expect(screen.getByTestId("smart-search-note").textContent).toMatch(/indicator/i);
    expect(launchMock).not.toHaveBeenCalled();
  });

  it("asks when a screen's rules map to no known primitive", async () => {
    launchMock.mockResolvedValue(false); // nothing hydrated
    parseMock.mockResolvedValue({
      intent: "screen",
      query: "weird",
      screen: { universe_id: "sp500", rules: [{ primitive_id: "unknown_x" }] },
      options: [],
      confidence: 0.7,
    });
    render(<SmartSearchBox />);
    submit("some weird screen phrase");
    await waitFor(() => expect(screen.getByTestId("smart-search-note")).toBeTruthy());
    expect(screen.getByTestId("smart-search-note").textContent).toMatch(/indicator/i);
  });
});

// ── PRD-29 additions ──────────────────────────────────────────────────────

describe("SmartSearchBox mixed queries + controls", () => {
  it("passes the pre-narrowed symbol universe and the note through", async () => {
    const rules = [{ primitive_id: "rsi", operator: "lt", threshold: 30 }];
    parseMock.mockResolvedValue({
      intent: "screen",
      query: "small caps that are oversold",
      screen: {
        universe_id: "symbols",
        rules,
        symbols: ["AAA", "BBB"],
        fundamental_filters: ["small-cap"],
      },
      options: [],
      note: "Matched 2 names on small-cap, then screened them on your technical rules.",
      confidence: 0.7,
    });
    render(<SmartSearchBox />);
    submit("small caps that are oversold");

    await waitFor(() =>
      expect(launchMock).toHaveBeenCalledWith(
        rules,
        "symbols",
        ["AAA", "BBB"],
        "Matched 2 names on small-cap, then screened them on your technical rules.",
      ),
    );
  });

  it("shows the scope, conditions and saved controls inside the box", () => {
    render(<SmartSearchBox />);
    // The scope is a universe picker now, not a static "US equities" label.
    expect(screen.getByTestId("smart-search-scope").textContent).toMatch(/S&P 500/);
    expect(screen.getByTestId("smart-search-conditions")).toBeTruthy();
    expect(screen.getByTestId("smart-search-saved")).toBeTruthy();
  });

  it("Conditions opens the builder and a pick lands in the query", () => {
    render(<SmartSearchBox />);
    fireEvent.click(screen.getByTestId("smart-search-conditions"));
    expect(screen.getByTestId("smart-search-conditions-panel")).toBeTruthy();

    fireEvent.click(screen.getByTestId("stub-pick"));
    const input = screen.getByTestId("smart-search-input") as HTMLInputElement;
    // A pick writes a COMPLETE readable condition, not a bare primitive name.
    expect(input.value).toBe("oversold");
  });

  it("Saved lists the user's screens", async () => {
    savedMock.mockResolvedValue({
      screens: [
        { saved_strategy_id: "s1", title: "Oversold semis", universe_id: "sp500",
          basket_size: 12, created_at: null },
      ],
    });
    render(<SmartSearchBox />);
    fireEvent.click(screen.getByTestId("smart-search-saved"));
    await waitFor(() =>
      expect(screen.getByTestId("smart-search-saved-s1").textContent).toMatch(
        /Oversold semis/,
      ),
    );
  });

  it("tells an anonymous visitor to sign in rather than showing an empty list", () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    render(<SmartSearchBox />);
    fireEvent.click(screen.getByTestId("smart-search-saved"));
    expect(screen.getByTestId("smart-search-saved-panel").textContent).toMatch(
      /Sign in to see your saved screens/,
    );
    expect(savedMock).not.toHaveBeenCalled();
  });
});

describe("universe picker", () => {
  it("defaults to the S&P 500 and offers the Russell 3000", () => {
    render(<SmartSearchBox />);
    const sel = screen.getByTestId("smart-search-scope") as HTMLSelectElement;
    expect(sel.value).toBe("sp500");
    expect(
      Array.from(sel.options).map((o) => o.value),
    ).toEqual(["sp500", "russell3000"]);
  });

  it("sends the chosen universe with the query", async () => {
    parseMock.mockResolvedValue({
      intent: "ambiguous", query: "x", options: [], note: "n", confidence: 0.3,
    });
    render(<SmartSearchBox />);
    fireEvent.change(screen.getByTestId("smart-search-scope"), {
      target: { value: "russell3000" },
    });
    submit("oversold");
    await waitFor(() =>
      expect(parseMock).toHaveBeenCalledWith("oversold", "russell3000"),
    );
  });

  it("counts conditions against the chosen universe too", () => {
    render(<SmartSearchBox />);
    fireEvent.change(screen.getByTestId("smart-search-scope"), {
      target: { value: "russell3000" },
    });
    fireEvent.click(screen.getByTestId("smart-search-conditions"));
    expect(screen.getByTestId("stub-pick").getAttribute("data-universe")).toBe(
      "russell3000",
    );
  });
});

describe("fundamental-only queries", () => {
  it("navigates to the stock screener instead of a rule-less scan", async () => {
    pushMock.mockClear();
    parseMock.mockResolvedValue({
      intent: "screen",
      query: "p/e under 15",
      note: "Matched 42 names on P/E under 15.",
      confidence: 0.8,
      screen: {
        universe_id: "symbols",
        rules: [],
        symbols: ["JPM", "XOM"],
        fundamental_filters: ["P/E under 15"],
        screener_params: { max_pe: "15" },
      },
    });
    render(<SmartSearchBox />);
    submit("p/e under 15");
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/stocks?max_pe=15"));
    // The signal-scan launcher rejects an empty rule set, so routing there
    // would have shown "try naming an indicator".
    expect(launchScreenFromParsedRules).not.toHaveBeenCalled();
  });

  it("encodes multi-filter params", async () => {
    pushMock.mockClear();
    parseMock.mockResolvedValue({
      intent: "screen", query: "healthcare small caps", note: "n", confidence: 0.8,
      screen: {
        universe_id: "symbols", rules: [], symbols: ["X"],
        fundamental_filters: ["healthcare sector", "small-cap"],
        screener_params: { sector: "Health Care", market_cap_category: "small" },
      },
    });
    render(<SmartSearchBox />);
    submit("healthcare small caps");
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(
        "/stocks?sector=Health+Care&market_cap_category=small",
      ),
    );
  });

  it("still launches the scan when the query has technical rules", async () => {
    pushMock.mockClear();
    parseMock.mockResolvedValue({
      intent: "screen", query: "oversold", note: "n", confidence: 0.8,
      screen: {
        universe_id: "sp500",
        rules: [{ primitive_id: "rsi", operator: "lt", threshold: 30 }],
        symbols: [], fundamental_filters: [], screener_params: {},
      },
    });
    vi.mocked(launchScreenFromParsedRules).mockResolvedValue(true);
    render(<SmartSearchBox />);
    submit("oversold");
    await waitFor(() => expect(launchScreenFromParsedRules).toHaveBeenCalled());
    expect(pushMock).not.toHaveBeenCalled();
  });
});
