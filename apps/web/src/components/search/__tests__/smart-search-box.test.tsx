/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  parseSearch: vi.fn(),
  searchSymbols: vi.fn().mockResolvedValue([]),
  getCompanyOverview: vi.fn().mockRejectedValue(new Error("no overview")),
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

import { parseSearch } from "@/lib/api";
import { launchScreenFromParsedRules } from "@/lib/flows/launch-screen";
import { SmartSearchBox } from "../smart-search-box";

const parseMock = parseSearch as unknown as ReturnType<typeof vi.fn>;
const launchMock = launchScreenFromParsedRules as unknown as ReturnType<typeof vi.fn>;

function submit(text: string) {
  const input = screen.getByTestId("smart-search-input");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
}

beforeEach(() => {
  vi.clearAllMocks();
  launchMock.mockResolvedValue(true);
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
      expect(launchMock).toHaveBeenCalledWith(rules, "sp500"),
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
