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
  matchSignalCombosToTemplates: vi.fn(),
}));

import { matchSignalCombosToTemplates } from "@/lib/api";
import { TemplateMatchSuggestion } from "../template-match-suggestion";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TemplateMatchSuggestion", () => {
  it("renders an empty-state hint when no primitives are selected", () => {
    render(<TemplateMatchSuggestion primitiveIds={[]} />);
    expect(screen.getByText(/Pick primitives/i)).toBeTruthy();
    expect(matchSignalCombosToTemplates).not.toHaveBeenCalled();
  });

  it("debounces the request and renders matches", async () => {
    (matchSignalCombosToTemplates as ReturnType<typeof vi.fn>).mockResolvedValue({
      matches: [
        {
          template_id: "bollinger-mean-reversion",
          similarity: 0.667,
          shared_categories: ["mean_reversion"],
          thresholds_for_user_primitives: {
            bbands: { period: 20, std_dev: 2.0 },
          },
        },
      ],
    });
    render(<TemplateMatchSuggestion primitiveIds={["rsi", "bbands"]} />);

    await waitFor(
      () => expect(matchSignalCombosToTemplates).toHaveBeenCalledWith({
        primitive_ids: ["rsi", "bbands"],
        top_n: 3,
      }),
      { timeout: 1500 },
    );
    await waitFor(() => {
      expect(screen.getByText(/Bollinger Mean Reversion/i)).toBeTruthy();
    });
    expect(screen.getByText("67% match")).toBeTruthy();
  });

  it("fires onPickTemplate with the picked match", async () => {
    const onPick = vi.fn();
    (matchSignalCombosToTemplates as ReturnType<typeof vi.fn>).mockResolvedValue({
      matches: [
        {
          template_id: "bollinger-mean-reversion",
          similarity: 0.667,
          shared_categories: ["mean_reversion"],
          thresholds_for_user_primitives: {
            bbands: { period: 20 },
          },
        },
      ],
    });
    render(
      <TemplateMatchSuggestion
        primitiveIds={["rsi", "bbands"]}
        onPickTemplate={onPick}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/Use these defaults/)).toBeTruthy();
    });
    fireEvent.click(screen.getByText(/Use these defaults/));
    expect(onPick).toHaveBeenCalled();
    expect(onPick.mock.calls[0][0].template_id).toBe(
      "bollinger-mean-reversion",
    );
  });

  it("shows the no-match message when the matcher returns nothing", async () => {
    (matchSignalCombosToTemplates as ReturnType<typeof vi.fn>).mockResolvedValue({
      matches: [],
    });
    render(<TemplateMatchSuggestion primitiveIds={["analyst_rating_change"]} />);
    await waitFor(() => {
      expect(screen.getByText(/No template matches/)).toBeTruthy();
    });
  });
});
