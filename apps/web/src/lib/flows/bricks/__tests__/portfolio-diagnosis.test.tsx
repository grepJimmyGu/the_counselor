/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  diagnosePortfolio: vi.fn(),
  UpgradeRequiredError: class UpgradeRequiredError extends Error {
    readonly status = 402;
    entitlement: { detail: string };
    constructor(entitlement: { detail: string }) {
      super(entitlement.detail);
      this.entitlement = entitlement;
    }
  },
}));

import { diagnosePortfolio } from "@/lib/api";
import { PortfolioDiagnosis } from "../portfolio-diagnosis";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function _diagnosis() {
  return {
    n_holdings: 3,
    style_mix: {
      growth: 0.6,
      value: 0.2,
      defensive: 0.1,
      commodity: 0.0,
      macro_sensitive: 0.1,
      unclassified_weight: 0.0,
    },
    factor_exposure: {
      size: 0.4,
      value: -0.1,
      momentum: 0.2,
      quality: 0.3,
      low_vol: 0.0,
      beta_to_spy: 1.1,
    },
    behavior: {
      trending_pct: 0.7,
      mean_reverting_pct: 0.1,
      mixed_pct: 0.2,
    },
    sectors: {
      sectors: { Technology: 0.6, Healthcare: 0.2, Financials: 0.2 },
      unknown_sector_weight: 0.0,
    },
    realized_vol_1y: 0.18,
    max_drawdown_5y: -0.22,
    caveats: [],
  };
}

function renderDiag(holdings: Array<{ ticker: string; weight?: number }> = [{ ticker: "AAPL", weight: 1.0 }]) {
  const advance = vi.fn();
  const updateContext = vi.fn();
  render(
    <PortfolioDiagnosis
      context={{ fromTrigger: "test/start", holdings } as any}
      updateContext={updateContext}
      advance={advance}
      back={() => {}}
      abort={() => {}}
    />,
  );
  return { advance, updateContext };
}

describe("PortfolioDiagnosis", () => {
  it("shows the skeleton initially then the diagnosis once loaded", async () => {
    (diagnosePortfolio as any).mockResolvedValueOnce({
      diagnosis: _diagnosis(),
      recommended_overlays: [],
      cache_hit: false,
    });
    renderDiag();
    expect(screen.getByTestId("portfolio-diagnosis-skeleton")).toBeTruthy();
    await waitFor(() => screen.getByTestId("portfolio-diagnosis"));
    expect(screen.getByTestId("portfolio-diagnosis-continue")).toBeTruthy();
  });

  it("renders the diagnose title from useFlowCopy", async () => {
    (diagnosePortfolio as any).mockResolvedValueOnce({
      diagnosis: _diagnosis(),
      recommended_overlays: [],
      cache_hit: false,
    });
    renderDiag();
    await waitFor(() => screen.getByText("Your portfolio at a glance"));
  });

  it("renders an error message when the API call fails", async () => {
    (diagnosePortfolio as any).mockRejectedValueOnce(new Error("boom"));
    renderDiag();
    await waitFor(() => screen.getByTestId("portfolio-diagnosis-error"));
  });

  it("falls back to error state when no holdings are passed", async () => {
    renderDiag([]);
    await waitFor(() => screen.getByTestId("portfolio-diagnosis-error"));
  });
});
