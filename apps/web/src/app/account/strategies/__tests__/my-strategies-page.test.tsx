/**
 * "My Strategies" repo (/account/strategies) — list page tests.
 *
 * The repo is the user's landing spot for their saved live strategies:
 * each row links to /account/strategies/{id} where the dashboard renders.
 * Mocks `listSavedStrategies` + `useSession` so no network is touched.
 *
 * Trap #19: the page must wait for sessionStatus !== "loading" and pass
 * the backendToken — covered here.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  listSavedStrategies: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

import { listSavedStrategies } from "@/lib/api";
import MyStrategiesPage from "../page";

type Row = {
  id: string;
  user_id: string;
  title: string;
  strategy_json: unknown;
  is_public: boolean;
  backtest_record_id: string | null;
  created_at: string;
  updated_at: string;
};

function row(over: Partial<Row> = {}): Row {
  return {
    id: "s1",
    user_id: "u1",
    title: "My Strategy",
    strategy_json: { bar_resolution: "daily" },
    is_public: true,
    backtest_record_id: "bt1",
    created_at: "2026-06-10T00:00:00Z",
    updated_at: "2026-06-10T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useSessionMock.mockReturnValue({
    data: { backendToken: "tok_abc" },
    status: "authenticated",
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MyStrategiesPage", () => {
  it("renders a row per saved strategy, linking to its dashboard", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      row({ id: "s1", title: "Daily MA" }),
      row({
        id: "s2",
        title: "SpaceX Active",
        strategy_json: { bar_resolution: "15min" },
      }),
    ]);

    render(<MyStrategiesPage />);
    await waitFor(() => screen.getByTestId("my-strategies-list"));

    const r1 = screen.getByTestId("my-strategy-row-s1");
    const r2 = screen.getByTestId("my-strategy-row-s2");
    expect(r1.getAttribute("href")).toBe("/account/strategies/s1");
    expect(r2.getAttribute("href")).toBe("/account/strategies/s2");
    expect(screen.getByText("Daily MA")).toBeTruthy();
    expect(screen.getByText("SpaceX Active")).toBeTruthy();
  });

  it("flags active-execution strategies with a Live badge", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      row({ id: "s1", title: "Daily MA", strategy_json: { bar_resolution: "daily" } }),
      row({
        id: "s2",
        title: "SpaceX Active",
        strategy_json: { bar_resolution: "15min" },
      }),
    ]);

    render(<MyStrategiesPage />);
    await waitFor(() => screen.getByTestId("my-strategies-list"));

    // Exactly one "Live" badge — the 15min strategy, not the daily one.
    const live = screen.getAllByText("Live");
    expect(live.length).toBe(1);
  });

  it("renders the empty state when there are no saved strategies", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      [],
    );
    render(<MyStrategiesPage />);
    await waitFor(() => screen.getByTestId("my-strategies-empty"));
  });

  it("renders an error state on api failure", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("503 boom"),
    );
    render(<MyStrategiesPage />);
    await waitFor(() => screen.getByTestId("my-strategies-error"));
    expect(screen.getByTestId("my-strategies-error").textContent).toContain(
      "503",
    );
  });

  it("waits for sessionStatus !== 'loading' before fetching (trap #19)", () => {
    useSessionMock.mockReturnValue({
      data: { backendToken: "tok_abc" },
      status: "loading" as unknown as "authenticated",
    });
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      [],
    );
    render(<MyStrategiesPage />);
    expect(listSavedStrategies).not.toHaveBeenCalled();
  });

  it("passes the backendToken to listSavedStrategies", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      [],
    );
    render(<MyStrategiesPage />);
    await waitFor(() =>
      expect(listSavedStrategies).toHaveBeenCalledWith("tok_abc"),
    );
  });
});
