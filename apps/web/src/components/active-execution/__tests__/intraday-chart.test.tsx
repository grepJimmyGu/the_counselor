/**
 * IntradayChart tests.
 *
 * recharts is mocked to passthroughs — jsdom can't size an SVG, and the
 * component exposes a text legend (entry + tier levels + fired-trigger
 * count) that's the accessible, test-stable surface. We assert on that
 * plus the empty / cold-cache / error / trap-#19 states.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  getIntradayChart: vi.fn(),
}));

const useSessionMock = vi.fn(() => ({
  data: { backendToken: "tok_abc" },
  status: "authenticated" as const,
}));
vi.mock("next-auth/react", () => ({
  useSession: () => useSessionMock(),
}));

vi.mock("recharts", () => {
  const Pass = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const Null = () => null;
  return {
    ResponsiveContainer: Pass,
    LineChart: Pass,
    Line: Null,
    XAxis: Null,
    YAxis: Null,
    CartesianGrid: Null,
    Tooltip: Null,
    ReferenceLine: Null,
    ReferenceDot: Null,
  };
});

import { getIntradayChart } from "@/lib/api";
import { IntradayChart } from "../intraday-chart";

const POLL = 9_999_999;

function resp(over: Record<string, unknown> = {}) {
  return {
    strategy_id: "s1",
    bar_resolution: "15min",
    generated_at: new Date().toISOString(),
    series: [],
    ...over,
  };
}

function series(over: Record<string, unknown> = {}) {
  return {
    position_id: "p1",
    symbol: "MSFT",
    is_open: true,
    entry_at: new Date().toISOString(),
    entry_price: 391,
    bars: [
      { t: "2026-06-11T14:00:00", close: 388 },
      { t: "2026-06-11T14:15:00", close: 389.5 },
    ],
    tiers: [
      { label: "Stop", trigger_pct: -0.1, price_level: 351.9 },
      { label: "TP1", trigger_pct: 0.05, price_level: 410.55 },
    ],
    events: [{ event: "entry", t: "2026-06-11T13:30:00", price: 391, tier_label: null }],
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

describe("IntradayChart", () => {
  it("renders a per-position chart with entry + tier legend", async () => {
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      resp({ series: [series()] }),
    );
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    await waitFor(() => screen.getByTestId("intraday-chart-series-MSFT"));

    const legend = screen.getByTestId("intraday-chart-legend-MSFT");
    expect(legend.textContent).toContain("Entry");
    expect(legend.textContent).toContain("Stop");
    expect(legend.textContent).toContain("$351.90");
    expect(legend.textContent).toContain("TP1");
    expect(legend.textContent).toContain("$410.55");
  });

  it("shows a fired-trigger count when a tier event is present", async () => {
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      resp({
        series: [
          series({
            events: [
              { event: "entry", t: "2026-06-11T13:30:00", price: 391, tier_label: null },
              { event: "tp1_hit", t: "2026-06-11T14:10:00", price: 411, tier_label: "TP1" },
            ],
          }),
        ],
      }),
    );
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    await waitFor(() => screen.getByTestId("intraday-chart-legend-MSFT"));
    expect(screen.getByText("1 fired")).toBeTruthy();
  });

  it("renders the empty state when there are no open positions", async () => {
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      resp({ series: [] }),
    );
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    await waitFor(() => screen.getByTestId("intraday-chart-empty"));
  });

  it("shows a cold-cache note (but keeps the tier legend) when bars are empty", async () => {
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      resp({ series: [series({ bars: [] })] }),
    );
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    await waitFor(() => screen.getByTestId("intraday-chart-nobars-MSFT"));
    // Tier legend still present — it doesn't depend on bars.
    expect(screen.getByTestId("intraday-chart-legend-MSFT").textContent).toContain("Stop");
  });

  it("renders an error state on api failure", async () => {
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("503 boom"),
    );
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    await waitFor(() => screen.getByTestId("intraday-chart-error"));
    expect(screen.getByTestId("intraday-chart-error").textContent).toContain("503");
  });

  it("waits for sessionStatus !== 'loading' before fetching (trap #19)", () => {
    useSessionMock.mockReturnValue({
      data: { backendToken: "tok_abc" },
      status: "loading" as unknown as "authenticated",
    });
    (getIntradayChart as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(resp());
    render(<IntradayChart strategyId="s1" pollIntervalMs={POLL} />);
    expect(getIntradayChart).not.toHaveBeenCalled();
  });
});
