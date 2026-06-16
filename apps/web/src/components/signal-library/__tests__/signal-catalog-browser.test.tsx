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
  getSignalPrimitives: vi.fn(),
}));

import { getSignalPrimitives } from "@/lib/api";
import type {
  SignalPrimitive,
  SignalPrimitivesResponse,
} from "@/lib/contracts";
import { SignalCatalogBrowser } from "../signal-catalog-browser";

function _p(
  id: string,
  category: SignalPrimitive["category"],
  overrides: Partial<SignalPrimitive> = {},
): SignalPrimitive {
  return {
    id,
    category,
    family: id.toUpperCase(),
    name: id,
    description: `Description for ${id} primitive — at least thirty chars`,
    long_description: null,
    parameters: [
      {
        name: "period",
        default: 14,
        min_value: 2,
        max_value: 100,
        description: "Period",
      },
    ],
    default_thresholds: {},
    asset_compat: ["equity"],
    evidence_tier: "B",
    provider_impl: id,
    data_source: "price",
    resolution: ["daily"],
    is_ranking: false,
    compute_strategy: "local",
    ...overrides,
  };
}

function _response(): SignalPrimitivesResponse {
  return {
    primitives: [
      _p("sma", "trend"),
      _p("ema", "trend"),
      _p("rsi", "mean_reversion"),
      _p("bbands", "mean_reversion"),
      _p("roc", "momentum"),
    ],
    categories: [
      "trend",
      "mean_reversion",
      "momentum",
      "volume",
      "volatility",
      "fundamental",
      "sentiment",
      "cross_sectional",
    ],
    version_hash: "test123",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (getSignalPrimitives as ReturnType<typeof vi.fn>).mockResolvedValue(_response());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SignalCatalogBrowser", () => {
  it("renders all primitives by default", async () => {
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText("sma")).toBeTruthy();
    });
    expect(screen.getByText("rsi")).toBeTruthy();
    expect(screen.getByText("roc")).toBeTruthy();
  });

  it("filters by category when a sidebar button is clicked", async () => {
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText("sma")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("category-trend"));
    // Trend-only after click — RSI is gone.
    expect(screen.queryByText("rsi")).toBeNull();
    expect(screen.getByText("sma")).toBeTruthy();
  });

  it("filters by search query", async () => {
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText("sma")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("catalog-search"), {
      target: { value: "RSI" },
    });
    expect(screen.getByText("rsi")).toBeTruthy();
    expect(screen.queryByText("sma")).toBeNull();
  });

  it("shows empty state when no primitives match", async () => {
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText("sma")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("catalog-search"), {
      target: { value: "definitely-not-in-the-catalog-xyzzy" },
    });
    expect(screen.getByTestId("catalog-empty")).toBeTruthy();
  });

  it("counts primitives per category in the sidebar", async () => {
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText("sma")).toBeTruthy();
    });
    // Trend has 2 (sma + ema), Mean Reversion has 2 (rsi + bbands),
    // Momentum has 1 (roc), all = 5.
    const trendBtn = screen.getByTestId("category-trend");
    expect(trendBtn.textContent).toContain("2");
    const allBtn = screen.getByTestId("category-all");
    expect(allBtn.textContent).toContain("5");
  });

  it("invokes onPick with the clicked primitive", async () => {
    const onPick = vi.fn();
    render(<SignalCatalogBrowser onPick={onPick} />);
    await waitFor(() => {
      expect(screen.getByText("rsi")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("primitive-card-rsi"));
    expect(onPick).toHaveBeenCalled();
    expect(onPick.mock.calls[0][0].id).toBe("rsi");
  });

  it("filters by output_kind (PRD-22c) — multi-select chips", async () => {
    (getSignalPrimitives as ReturnType<typeof vi.fn>).mockResolvedValue({
      primitives: [
        _p("rsi", "mean_reversion", { output_kind: "value" }),
        _p("ma_crossover", "trend", { output_kind: "cross" }),
        _p("donchian_breakout", "momentum", { output_kind: "event" }),
      ],
      categories: _response().categories,
      version_hash: "kindtest",
    });
    render(<SignalCatalogBrowser />);
    await waitFor(() => expect(screen.getByText("rsi")).toBeTruthy());

    // EVENT only → just donchian_breakout.
    fireEvent.click(screen.getByTestId("kind-chip-event"));
    expect(screen.getByText("donchian_breakout")).toBeTruthy();
    expect(screen.queryByText("rsi")).toBeNull();
    expect(screen.queryByText("ma_crossover")).toBeNull();

    // Add CROSS → event + cross; value still hidden.
    fireEvent.click(screen.getByTestId("kind-chip-cross"));
    expect(screen.getByText("ma_crossover")).toBeTruthy();
    expect(screen.queryByText("rsi")).toBeNull();

    // Toggle EVENT off → only cross remains.
    fireEvent.click(screen.getByTestId("kind-chip-event"));
    expect(screen.queryByText("donchian_breakout")).toBeNull();
    expect(screen.getByText("ma_crossover")).toBeTruthy();
  });

  it("surfaces an error message when the catalog fetch fails", async () => {
    (getSignalPrimitives as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Network down"),
    );
    render(<SignalCatalogBrowser />);
    await waitFor(() => {
      expect(screen.getByText(/Network down/)).toBeTruthy();
    });
  });
});
