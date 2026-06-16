/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ screenCount: vi.fn() }));
vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: null, status: "unauthenticated" }),
}));

import { screenCount } from "@/lib/api";
import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import type { SignalPrimitive } from "@/lib/contracts";
import { ScreenMatchCount } from "../screen-match-count";

function rule(): BuildRule {
  return {
    uid: "u1",
    primitive_id: "rsi",
    primitive: { id: "rsi" } as SignalPrimitive,
    primitive_params: {},
    operator: "lt",
    threshold: 30,
    logic_with_prior: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (screenCount as ReturnType<typeof vi.fn>).mockResolvedValue({
    matched_count: 42,
    universe_size: 503,
    as_of_date: "2026-06-15",
    unsupported_primitives: [],
    default_param_primitives: [],
  });
});

afterEach(() => vi.restoreAllMocks());

describe("ScreenMatchCount", () => {
  it("renders the live count for a standing universe", async () => {
    render(<ScreenMatchCount universeId="sp500" rules={[rule()]} debounceMs={0} />);
    await waitFor(() =>
      expect(screen.getByTestId("screen-match-count-value").textContent).toBe("42"),
    );
    expect(screen.getByTestId("screen-match-count").textContent).toContain("of 503");
    expect(screenCount).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for a non-standing (entered) universe", () => {
    const { container } = render(
      <ScreenMatchCount universeId="symbols" rules={[rule()]} debounceMs={0} />,
    );
    expect(container.firstChild).toBeNull();
    expect(screenCount).not.toHaveBeenCalled();
  });

  it("prompts to add a rule when the reading is empty", () => {
    render(<ScreenMatchCount universeId="sp500" rules={[]} debounceMs={0} />);
    expect(screen.getByTestId("screen-match-count").textContent).toContain("Add a rule");
    expect(screenCount).not.toHaveBeenCalled();
  });
});
