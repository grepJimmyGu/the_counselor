/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ screenScan: vi.fn(), screenRank: vi.fn(), saveScreen: vi.fn() }));
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
let sessionValue: { data: unknown; status: string } = {
  data: null,
  status: "unauthenticated",
};
vi.mock("next-auth/react", () => ({ useSession: () => sessionValue }));

import { screenScan, screenRank, saveScreen } from "@/lib/api";
import type { CustomBuildModeContext } from "@/lib/flows/custom-build-mode-context";
import type { SignalPrimitive } from "@/lib/contracts";
import { ScreenResults } from "../screener-results";

function ctx(): CustomBuildModeContext {
  return {
    fromTrigger: "test",
    universe_id: "sp500",
    entered_symbols: [],
    symbol: null,
    rules: [
      {
        uid: "u1",
        primitive_id: "rsi",
        primitive: { id: "rsi", family: "RSI" } as SignalPrimitive,
        primitive_params: {},
        operator: "lt",
        threshold: 30,
        logic_with_prior: null,
      },
    ],
    active_execution_enabled: false,
    bar_resolution: "daily",
    exit_ladder: [],
  };
}

function renderResults(over: { back?: () => void } = {}) {
  render(
    <ScreenResults
      context={ctx()}
      updateContext={vi.fn()}
      advance={vi.fn()}
      back={over.back ?? vi.fn()}
      abort={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionValue = { data: null, status: "unauthenticated" };
  (screenScan as ReturnType<typeof vi.fn>).mockResolvedValue({
    matched: ["AAPL", "MSFT"],
    readings: { AAPL: ["Oversold extreme"], MSFT: ["Oversold extreme"] },
    as_of_date: "2026-06-15",
    universe_size: 503,
    matched_count: 2,
    unsupported_primitives: [],
    default_param_primitives: [],
  });
});

afterEach(() => vi.restoreAllMocks());

describe("ScreenResults", () => {
  it("renders the matched basket from scan with the as-of byline", async () => {
    renderResults();
    await waitFor(() => expect(screen.getByTestId("screen-results")).toBeTruthy());
    expect(screen.getByTestId("screen-result-row-AAPL")).toBeTruthy();
    expect(screen.getByTestId("screen-result-row-MSFT")).toBeTruthy();
    expect(screen.getByText(/as of 2026-06-15/)).toBeTruthy();
    expect(screen.getAllByText(/Oversold extreme/).length).toBeGreaterThan(0);
  });

  it("shows a sign-in gate for the rank step when anonymous", async () => {
    renderResults();
    await waitFor(() => expect(screen.getByTestId("screen-results-rank-gate")).toBeTruthy());
    expect(screenRank).not.toHaveBeenCalled();
  });

  it("ranks + fills returns when signed in, sorted best-first", async () => {
    sessionValue = { data: { backendToken: "tok" }, status: "authenticated" };
    (screenRank as ReturnType<typeof vi.fn>).mockResolvedValue({
      ranked: [
        { symbol: "MSFT", total_return: 0.31, annualized_return: 0.3, sharpe_ratio: 1.1, readings: [] },
        { symbol: "AAPL", total_return: 0.12, annualized_return: 0.11, sharpe_ratio: 0.6, readings: [] },
      ],
      as_of_date: "2026-06-15",
      matched_count: 2,
      backtested_count: 2,
      dropped_count: 0,
      universe_size: 503,
      unsupported_primitives: [],
      default_param_primitives: [],
    });
    renderResults();
    await waitFor(() => expect(screen.getByText("+31.0%")).toBeTruthy());
    expect(screen.getByText("+12.0%")).toBeTruthy();
    // MSFT (higher return) sorts above AAPL.
    const rows = screen.getAllByTestId(/screen-result-row-/);
    expect(rows[0].getAttribute("data-testid")).toBe("screen-result-row-MSFT");
  });

  it("surfaces a rank failure inline without blanking the basket", async () => {
    sessionValue = { data: { backendToken: "tok" }, status: "authenticated" };
    (screenRank as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("rank timed out"));
    renderResults();
    // The scan basket still renders...
    await waitFor(() => expect(screen.getByTestId("screen-result-row-AAPL")).toBeTruthy());
    // ...and the rank failure is shown inline (not a silent stuck skeleton).
    await waitFor(() =>
      expect(screen.getByTestId("screen-results-rank-error")).toBeTruthy(),
    );
  });

  it("offers an in-flow 'Edit reading' back affordance", async () => {
    const back = vi.fn();
    renderResults({ back });
    await waitFor(() => expect(screen.getByTestId("screen-results-edit")).toBeTruthy());
    screen.getByTestId("screen-results-edit").click();
    expect(back).toHaveBeenCalled();
  });

  it("shows the empty state when nothing matches", async () => {
    (screenScan as ReturnType<typeof vi.fn>).mockResolvedValue({
      matched: [],
      readings: {},
      as_of_date: "2026-06-15",
      universe_size: 503,
      matched_count: 0,
      unsupported_primitives: [],
      default_param_primitives: [],
    });
    renderResults();
    await waitFor(() => expect(screen.getByTestId("screen-results-empty")).toBeTruthy());
  });

  it("shows the save sign-in gate when anonymous", async () => {
    renderResults(); // default sessionValue is unauthenticated
    await waitFor(() =>
      expect(screen.getByTestId("screen-results-save-gate")).toBeTruthy(),
    );
    expect(saveScreen).not.toHaveBeenCalled();
  });

  it("saves + tracks the screen when signed in, then confirms", async () => {
    sessionValue = { data: { backendToken: "tok" }, status: "authenticated" };
    (screenRank as ReturnType<typeof vi.fn>).mockResolvedValue({
      ranked: [],
      as_of_date: "2026-06-15",
      matched_count: 2,
      backtested_count: 0,
      dropped_count: 0,
      universe_size: 503,
      unsupported_primitives: [],
      default_param_primitives: [],
    });
    (saveScreen as ReturnType<typeof vi.fn>).mockResolvedValue({
      saved_strategy_id: "s1",
      basket: ["AAPL", "MSFT"],
      as_of_date: "2026-06-17",
      universe_size: 503,
    });
    renderResults();
    await waitFor(() => expect(screen.getByTestId("screen-results-save")).toBeTruthy());
    screen.getByTestId("screen-results-save").click();
    await waitFor(() => expect(screen.getByTestId("screen-results-saved")).toBeTruthy());
    expect(saveScreen).toHaveBeenCalledWith(
      expect.objectContaining({ universe_id: "sp500", title: "S&P 500 screen" }),
      { backendToken: "tok" },
    );
    expect(screen.getByText(/watching 2 names/)).toBeTruthy();
  });
});
