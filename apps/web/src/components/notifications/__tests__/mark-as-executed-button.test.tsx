/** @vitest-environment jsdom */

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  markStrategyExecuted: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

import { markStrategyExecuted } from "@/lib/api";
import { MarkAsExecutedButton } from "../mark-as-executed-button";

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

describe("MarkAsExecutedButton", () => {
  it("renders the unmarked CTA by default for a signed-in user", () => {
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    expect(screen.getByTestId("mark-as-executed-idle").textContent).toMatch(
      /I executed this/i,
    );
  });

  it("disables and hints when user is unauthenticated", () => {
    useSessionMock.mockReturnValue({ data: null, status: "unauthenticated" });
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    const btn = screen.getByRole("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toMatch(/Sign in to track/i);
  });

  it("POSTs and flips to 'Marked' on success", async () => {
    (markStrategyExecuted as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      latency_seconds: 120,
      signal_event_id: "evt_1",
      executed_at: new Date().toISOString(),
      idempotent: false,
    });
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    fireEvent.click(screen.getByTestId("mark-as-executed-idle"));

    await waitFor(() => {
      expect(screen.getByTestId("mark-as-executed-marked")).toBeTruthy();
    });
    expect(markStrategyExecuted).toHaveBeenCalledWith(
      "strat_123",
      { user_note: null },
      "tok_abc",
    );
    // First click → "Marked", not "Already marked".
    expect(screen.getByTestId("mark-as-executed-marked").textContent).toMatch(
      /^Marked/,
    );
  });

  it("shows 'Already marked' on an idempotent response", async () => {
    (markStrategyExecuted as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      latency_seconds: 300,
      signal_event_id: "evt_1",
      executed_at: new Date().toISOString(),
      idempotent: true,
    });
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    fireEvent.click(screen.getByTestId("mark-as-executed-idle"));

    await waitFor(() => {
      const node = screen.getByTestId("mark-as-executed-marked");
      expect(node.textContent).toMatch(/Already marked/);
    });
  });

  it("reverts to an error state when the POST throws", async () => {
    (markStrategyExecuted as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Network down"),
    );
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    fireEvent.click(screen.getByTestId("mark-as-executed-idle"));

    await waitFor(() => {
      expect(screen.getByText(/Network down/i)).toBeTruthy();
    });
    // Retry CTA visible.
    expect(screen.getByText(/Try again/i)).toBeTruthy();
  });

  it("invokes onMarked with the resolved row data", async () => {
    const onMarked = vi.fn();
    const executed_at = "2026-06-09T01:00:00.000Z";
    (markStrategyExecuted as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      latency_seconds: 60,
      signal_event_id: "evt_1",
      executed_at,
      idempotent: false,
    });

    render(
      <MarkAsExecutedButton strategyId="strat_123" onMarked={onMarked} />,
    );
    fireEvent.click(screen.getByTestId("mark-as-executed-idle"));

    await waitFor(() => {
      expect(onMarked).toHaveBeenCalledWith({
        idempotent: false,
        executed_at,
        latency_seconds: 60,
      });
    });
  });

  it("does not re-fire when the user double-clicks while submitting", async () => {
    let resolveSend!: (v: unknown) => void;
    (markStrategyExecuted as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((res) => {
        resolveSend = res;
      }),
    );
    render(<MarkAsExecutedButton strategyId="strat_123" />);
    const btn = screen.getByTestId("mark-as-executed-idle");
    fireEvent.click(btn);
    // Click again while the promise is still pending.
    fireEvent.click(btn);
    fireEvent.click(btn);
    // Resolve so the test finishes cleanly.
    resolveSend({
      ok: true,
      latency_seconds: 1,
      signal_event_id: "x",
      executed_at: new Date().toISOString(),
      idempotent: false,
    });
    await waitFor(() => {
      expect(screen.getByTestId("mark-as-executed-marked")).toBeTruthy();
    });
    // Exactly one POST despite three clicks.
    expect(markStrategyExecuted).toHaveBeenCalledTimes(1);
  });
});
