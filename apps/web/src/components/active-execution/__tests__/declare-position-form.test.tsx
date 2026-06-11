/**
 * active-execution-v2 PR2 — DeclarePositionForm tests.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

vi.mock("@/lib/api", () => ({
  declarePosition: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

import { declarePosition } from "@/lib/api";

import { DeclarePositionForm } from "../declare-position-form";

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

function _fill() {
  fireEvent.click(screen.getByTestId("declare-position-open"));
  fireEvent.change(screen.getByTestId("declare-symbol"), {
    target: { value: "nvda" },
  });
  fireEvent.change(screen.getByTestId("declare-shares"), {
    target: { value: "100" },
  });
  fireEvent.change(screen.getByTestId("declare-entry-price"), {
    target: { value: "145" },
  });
}

describe("DeclarePositionForm", () => {
  it("starts collapsed behind a button", () => {
    render(<DeclarePositionForm strategyId="s1" />);
    expect(screen.getByTestId("declare-position-open")).toBeTruthy();
    expect(screen.queryByTestId("declare-position-form")).toBeNull();
  });

  it("opens the form when the button is clicked", () => {
    render(<DeclarePositionForm strategyId="s1" />);
    fireEvent.click(screen.getByTestId("declare-position-open"));
    expect(screen.getByTestId("declare-position-form")).toBeTruthy();
  });

  it("submits the declared position and calls onDeclared", async () => {
    (declarePosition as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "p1",
      symbol: "NVDA",
    });
    const onDeclared = vi.fn();
    render(<DeclarePositionForm strategyId="s1" onDeclared={onDeclared} />);
    _fill();
    fireEvent.click(screen.getByTestId("declare-submit"));

    await waitFor(() => expect(onDeclared).toHaveBeenCalledTimes(1));
    expect(declarePosition).toHaveBeenCalledWith(
      "s1",
      { symbol: "NVDA", shares: 100, entry_price: 145 },
      "tok_abc",
    );
  });

  it("surfaces the backend error detail on failure", async () => {
    (declarePosition as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("An open position for NVDA already exists on this strategy."),
    );
    render(<DeclarePositionForm strategyId="s1" />);
    _fill();
    fireEvent.click(screen.getByTestId("declare-submit"));

    await waitFor(() => screen.getByTestId("declare-error"));
    expect(screen.getByTestId("declare-error").textContent).toContain(
      "already exists",
    );
  });

  it("disables submit until symbol + positive shares + positive price", () => {
    render(<DeclarePositionForm strategyId="s1" />);
    fireEvent.click(screen.getByTestId("declare-position-open"));
    const submit = screen.getByTestId("declare-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("declare-symbol"), {
      target: { value: "NVDA" },
    });
    fireEvent.change(screen.getByTestId("declare-shares"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByTestId("declare-entry-price"), {
      target: { value: "145" },
    });
    // shares=0 → still disabled.
    expect(submit.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("declare-shares"), {
      target: { value: "100" },
    });
    expect(submit.disabled).toBe(false);
  });
});
