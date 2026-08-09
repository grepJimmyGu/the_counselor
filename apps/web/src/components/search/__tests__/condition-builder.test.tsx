/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

vi.mock("@/lib/api", () => ({ screenCount: vi.fn() }));

import { screenCount } from "@/lib/api";
import { ConditionBuilder } from "../condition-builder";

const countMock = screenCount as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  countMock.mockResolvedValue({
    matched_count: 12,
    universe_size: 525,
    as_of_date: "2026-08-05",
    unsupported_primitives: [],
    default_param_primitives: [],
  });
});

afterEach(() => vi.restoreAllMocks());

function openPill(label: string) {
  fireEvent.click(screen.getByTestId(`condition-pill-${label}`));
}

describe("ConditionBuilder", () => {
  it("renders all six v3.1 categories", () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    for (const key of [
      "technical", "quote", "stage", "financials", "fundamentals", "special",
    ]) {
      expect(screen.getByTestId(`condition-group-${key}`)).toBeTruthy();
    }
  });

  it("a pill opens a dropdown of concrete values — no navigation away", () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    expect(screen.queryByTestId("condition-options-RSI")).toBeNull();
    openPill("RSI");
    const panel = screen.getByTestId("condition-options-RSI");
    // The VALUE is selectable inline; that's the whole point.
    expect(panel.textContent).toMatch(/Oversold \(below 30\)/);
    expect(panel.textContent).toMatch(/Overbought \(above 70\)/);
  });

  it("picking writes a complete readable condition, not a bare name", () => {
    const onAppend = vi.fn();
    render(<ConditionBuilder onAppend={onAppend} />);
    openPill("RSI");
    fireEvent.click(screen.getByText("Oversold (below 30)"));
    expect(onAppend).toHaveBeenCalledWith("oversold");
  });

  it("stacks multiple conditions as removable chips", () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    openPill("RSI");
    fireEvent.click(screen.getByText("Oversold (below 30)"));
    openPill("Moving average");
    fireEvent.click(screen.getByText("Above the 200-day"));
    expect(screen.getAllByTestId("condition-chip")).toHaveLength(2);

    fireEvent.click(screen.getByLabelText("Remove RSI Oversold (below 30)"));
    expect(screen.getAllByTestId("condition-chip")).toHaveLength(1);
  });

  it("shows a live match count for the selected technical conditions", async () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    openPill("RSI");
    fireEvent.click(screen.getByText("Oversold (below 30)"));

    await waitFor(() =>
      expect(screen.getByTestId("condition-count").textContent).toMatch(/12.*of.*525/),
    );
    const [body] = countMock.mock.calls[0];
    expect(body.rules[0].primitive_id).toBe("rsi");
    // The backend validator rejects a first rule carrying a fold operator.
    expect(body.rules[0].logic_with_prior).toBeNull();
  });

  it("folds the second and later rules with AND", async () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    openPill("RSI");
    fireEvent.click(screen.getByText("Oversold (below 30)"));
    openPill("Moving average");
    fireEvent.click(screen.getByText("Above the 200-day"));

    await waitFor(() => expect(countMock).toHaveBeenCalled());
    const body = countMock.mock.calls[countMock.mock.calls.length - 1][0];
    expect(body.rules).toHaveLength(2);
    expect(body.rules[0].logic_with_prior).toBeNull();
    expect(body.rules[1].logic_with_prior).toBe("AND");
  });

  it("does not count fundamental-only selections (they filter, not scan)", async () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    openPill("Market cap");
    fireEvent.click(screen.getByText("Small cap"));

    expect(screen.getByTestId("condition-chip")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("condition-count").textContent).toMatch(
        /run to see matches/,
      ),
    );
    expect(countMock).not.toHaveBeenCalled();
  });

  it("flags that the count excludes fundamentals when both are selected", async () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    openPill("RSI");
    fireEvent.click(screen.getByText("Oversold (below 30)"));
    openPill("Market cap");
    fireEvent.click(screen.getByText("Small cap"));

    await waitFor(() =>
      expect(screen.getByTestId("condition-count").textContent).toMatch(
        /before fundamentals/,
      ),
    );
  });
});

describe("ConditionBuilder chips + universe", () => {
  it("chips name the pill, not just the option", () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    fireEvent.click(screen.getByTestId("condition-pill-P/E"));
    fireEvent.click(screen.getByText("Under 15"));
    // "Under 15" alone doesn't say under-15 WHAT.
    expect(screen.getByTestId("condition-chip").textContent).toMatch(/P\/E · Under 15/);
  });

  it("counts against the universe it was given", async () => {
    render(<ConditionBuilder onAppend={() => {}} universeId="russell3000" />);
    fireEvent.click(screen.getByTestId("condition-pill-RSI"));
    fireEvent.click(screen.getByText("Oversold (below 30)"));
    await waitFor(() => expect(countMock).toHaveBeenCalled());
    expect(countMock.mock.calls[0][0].universe_id).toBe("russell3000");
  });
});

describe("hand-off to the results page", () => {
  it('"See matches" carries the selected phrases as the query', () => {
    pushMock.mockClear();
    render(<ConditionBuilder onAppend={() => {}} universeId="russell3000" />);
    fireEvent.click(screen.getByTestId("condition-pill-RSI"));
    fireEvent.click(screen.getByText("Oversold (below 30)"));

    fireEvent.click(screen.getByTestId("condition-next"));

    // The builder's PHRASES are the query — that text is the source of truth
    // on submit, so the results page must receive the same string rather than
    // a second, parallel encoding of the same conditions.
    const url = pushMock.mock.calls[0][0] as string;
    expect(url).toContain("/screen?q=");
    expect(decodeURIComponent(url)).toContain("oversold");
    expect(url).toContain("universe=russell3000");
  });

  it("offers no next action until something is selected", () => {
    render(<ConditionBuilder onAppend={() => {}} />);
    expect(screen.queryByTestId("condition-next")).toBeNull();
  });
});
