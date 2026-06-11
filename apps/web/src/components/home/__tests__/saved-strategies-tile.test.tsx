/**
 * <SavedStrategiesTile> — entry-point coverage.
 *
 * The tile heading "Your saved strategies" must itself link into the
 * /account/strategies repo in EVERY state (populated AND empty), because
 * "View all →" only renders when there are saved rows. Mr Gu's ask:
 * "the homepage 'your saved strategy' should also be an entry."
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  listSavedStrategies: vi.fn(),
  getSavedStrategySignal: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc", user: { email: "a@b.com" } },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
  signIn: vi.fn(),
}));

import { getSavedStrategySignal, listSavedStrategies } from "@/lib/api";
import { SavedStrategiesTile } from "../saved-strategies-tile";

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
    data: { backendToken: "tok_abc", user: { email: "a@b.com" } },
    status: "authenticated",
  });
  (getSavedStrategySignal as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
    { display: null, as_of_date: null },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SavedStrategiesTile heading entry-point", () => {
  it("links the heading into /account/strategies when strategies exist", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      row({ id: "s1", title: "Daily MA" }),
    ]);
    render(<SavedStrategiesTile />);
    await waitFor(() => screen.getByTestId("saved-strategy-row"));

    const heading = screen.getByTestId("saved-strategies-tile-heading");
    expect(heading.getAttribute("href")).toBe("/account/strategies");
  });

  it("STILL links the heading into the repo in the EMPTY state", async () => {
    (listSavedStrategies as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      [],
    );
    render(<SavedStrategiesTile />);
    // Empty-state copy confirms we're in the zero-strategies branch...
    await waitFor(() =>
      expect(screen.getByText(/haven.t saved a strategy yet/i)).toBeTruthy(),
    );
    // ...and the heading is still a live entry into the repo (the only one,
    // since "View all →" is hidden when there are no rows).
    const heading = screen.getByTestId("saved-strategies-tile-heading");
    expect(heading.getAttribute("href")).toBe("/account/strategies");
    expect(screen.queryByText("View all →")).toBeNull();
  });
});
