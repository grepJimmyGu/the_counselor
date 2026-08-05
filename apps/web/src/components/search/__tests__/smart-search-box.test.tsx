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
// The catalog browser fetches the 110-primitive catalog on mount; stub it and
// expose a pick button so the Conditions wiring is still exercised.
vi.mock("@/components/signal-library/signal-catalog-browser", () => ({
  SignalCatalogBrowser: ({ onPick }: { onPick: (p: { name: string }) => void }) => (
    <button data-testid="stub-pick" onClick={() => onPick({ name: "RSI" })}>
      pick
    </button>
  ),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({ useSession: () => useSessionMock() }));

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
    expect(screen.getByTestId("smart-search-scope").textContent).toMatch(/US equities/);
    expect(screen.getByTestId("smart-search-conditions")).toBeTruthy();
    expect(screen.getByTestId("smart-search-saved")).toBeTruthy();
  });

  it("Conditions opens the catalog and a pick lands in the query", () => {
    render(<SmartSearchBox />);
    fireEvent.click(screen.getByTestId("smart-search-conditions"));
    expect(screen.getByTestId("smart-search-conditions-panel")).toBeTruthy();

    fireEvent.click(screen.getByTestId("stub-pick"));
    const input = screen.getByTestId("smart-search-input") as HTMLInputElement;
    expect(input.value).toBe("RSI");
    // Picking closes the panel — the user is back at the query.
    expect(screen.queryByTestId("smart-search-conditions-panel")).toBeNull();
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
