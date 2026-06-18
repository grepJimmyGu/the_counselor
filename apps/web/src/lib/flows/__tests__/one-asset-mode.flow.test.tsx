/** @vitest-environment jsdom */

/**
 * Sprint 2 / Mode 1 refactor — flow definition smoke tests.
 *
 * Mirrors `portfolio-mode.flow.test.tsx`: mock the brick implementations
 * so the test drives the runtime directly, then verify each step
 * renders + advances + context propagates correctly.
 *
 * What this covers:
 *   - Registry side-effect on import
 *   - Both documented triggers advertised
 *   - Initial step renders
 *   - Full happy-path walk (template-pick → summary → backtest → review
 *     → save) when each step's advance fires
 *   - Context patches survive transitions (the persistence guarantee)
 *   - startFlow seeds sessionStorage with the right initialContext for
 *     both trigger shapes (stock-page with ticker, home picker without)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";

// Mock the bricks BEFORE importing one-asset-mode so the import-time
// side effect picks up the mocked components. There is no ticker step —
// the flow opens on the template picker (the single ticker is set in the
// summary step).
vi.mock("../bricks/one-asset-template-pick", () => ({
  OneAssetTemplatePick: (props: {
    updateContext: (patch: unknown) => void;
    advance: () => void;
  }) => (
    <div data-testid="step-template-pick">
      <button
        data-testid="template-pick-advance"
        onClick={() => {
          // Real brick sets template + riskPreset from the wizard.
          props.updateContext({
            template: {
              id: "time-series-momentum",
              name: "Time-series momentum",
              defaultTickers: ["SPY"],
            },
            riskPreset: "medium",
          });
          props.advance();
        }}
      >
        template-pick-advance
      </button>
    </div>
  ),
}));

vi.mock("../bricks/one-asset-summary", () => ({
  OneAssetSummary: (props: {
    updateContext: (patch: unknown) => void;
    advance: () => void;
  }) => (
    <div data-testid="step-summary">
      <button
        data-testid="summary-advance"
        onClick={() => {
          // Real brick builds the full StrategyJson from the summary
          // step config + applyRiskLevel. Test stub stores a marker.
          props.updateContext({
            strategyJson: {
              strategy_name: "test-strategy",
              strategy_type: "time_series_momentum",
              universe: ["AAPL"],
            },
          });
          props.advance();
        }}
      >
        summary-advance
      </button>
    </div>
  ),
}));

vi.mock("../bricks/flow-backtest", () => ({
  FlowBacktest: (props: { advance: () => void }) => (
    <div data-testid="step-backtest">
      <button data-testid="backtest-advance" onClick={props.advance}>
        backtest-advance
      </button>
    </div>
  ),
}));

vi.mock("../bricks/flow-review", () => ({
  FlowReview: (props: { advance: () => void }) => (
    <div data-testid="step-review">
      <button data-testid="review-advance" onClick={props.advance}>
        review-advance
      </button>
    </div>
  ),
}));

vi.mock("../bricks/flow-save", () => ({
  FlowSave: (props: { advance: () => void }) => (
    <div data-testid="step-save">
      <button data-testid="save-advance" onClick={props.advance}>
        save-advance
      </button>
    </div>
  ),
}));

// Bricks mocked. Import the flow definition + runtime APIs. The static
// import below evaluates one-asset-mode.ts ONCE, which calls registerFlow
// as a side-effect. beforeEach wipes the registry then re-registers
// `OneAssetModeFlow` directly — matches PRD-13a's runtime.test.tsx pattern.
import { OneAssetModeFlow } from "../one-asset-mode";
import { FlowProvider, FlowShell, startFlow } from "../runtime";
import { __resetRegistryForTests, getFlow, registerFlow } from "../registry";
import { __resetCopyForTests } from "../copy";

beforeEach(() => {
  window.sessionStorage.clear();
  __resetRegistryForTests();
  __resetCopyForTests();
  registerFlow(OneAssetModeFlow);
});

afterEach(() => {
  window.sessionStorage.clear();
});

function renderShell() {
  return render(
    <FlowProvider flowId="one_asset_mode">
      <FlowShell />
    </FlowProvider>,
  );
}

describe("one-asset-mode FlowDefinition", () => {
  it("is registered in the flow registry on import", () => {
    expect(getFlow("one_asset_mode")).toBeDefined();
    expect(getFlow("one_asset_mode")?.steps.map((s) => s.id)).toEqual([
      "template-pick",
      "summary",
      "backtest",
      "review",
      "save",
    ]);
  });

  it("advertises both documented triggers", () => {
    const triggers = getFlow("one_asset_mode")?.triggers ?? [];
    expect(triggers).toContain("stock_page/apply_strategy");
    expect(triggers).toContain("home/pick_asset");
  });

  it("renders the template-pick step first", () => {
    renderShell();
    expect(screen.getByTestId("step-template-pick")).toBeTruthy();
  });

  it("walks through every step in order when advance fires", () => {
    renderShell();
    expect(screen.getByTestId("step-template-pick")).toBeTruthy();
    fireEvent.click(screen.getByTestId("template-pick-advance"));
    expect(screen.getByTestId("step-summary")).toBeTruthy();
    fireEvent.click(screen.getByTestId("summary-advance"));
    expect(screen.getByTestId("step-backtest")).toBeTruthy();
    fireEvent.click(screen.getByTestId("backtest-advance"));
    expect(screen.getByTestId("step-review")).toBeTruthy();
    fireEvent.click(screen.getByTestId("review-advance"));
    expect(screen.getByTestId("step-save")).toBeTruthy();
  });

  it("persists context patches across step transitions", () => {
    vi.useFakeTimers();
    renderShell();
    act(() => {
      fireEvent.click(screen.getByTestId("template-pick-advance"));
    });
    // Runtime debounces persistence by 250ms — advance the timer
    // to flush the write to sessionStorage.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    const raw = window.sessionStorage.getItem("livermore_flow_one_asset_mode");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.context.template?.id).toBe("time-series-momentum");
    expect(parsed.currentStepId).toBe("summary");
    vi.useRealTimers();
  });

  it("startFlow seeds sessionStorage for the stock-page entry path (with ticker)", () => {
    startFlow("one_asset_mode", {
      initialContext: {
        fromTrigger: "stock_page/apply_strategy",
        ticker: "NVDA",
      },
    });
    const raw = window.sessionStorage.getItem("livermore_flow_one_asset_mode");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("one_asset_mode");
    expect(parsed.currentStepId).toBe("template-pick");
    expect(parsed.context.fromTrigger).toBe("stock_page/apply_strategy");
    expect(parsed.context.ticker).toBe("NVDA");
  });

  it("startFlow seeds sessionStorage for the home picker entry path (no ticker)", () => {
    startFlow("one_asset_mode", {
      initialContext: { fromTrigger: "home/pick_asset" },
    });
    const raw = window.sessionStorage.getItem("livermore_flow_one_asset_mode");
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("one_asset_mode");
    expect(parsed.currentStepId).toBe("template-pick");
    expect(parsed.context.fromTrigger).toBe("home/pick_asset");
    expect(parsed.context.ticker).toBeUndefined();
  });

  it("carries a stock-page seeded ticker through to context (no ticker step)", () => {
    startFlow("one_asset_mode", {
      initialContext: {
        fromTrigger: "stock_page/apply_strategy",
        ticker: "TSLA",
      },
    });
    renderShell();
    // The flow opens on template-pick (the dedicated ticker step was
    // dropped), but the seeded ticker stays in context so the summary
    // step can prefill its single-ticker field.
    expect(screen.getByTestId("step-template-pick")).toBeTruthy();
    const parsed = JSON.parse(
      window.sessionStorage.getItem("livermore_flow_one_asset_mode")!,
    );
    expect(parsed.context.ticker).toBe("TSLA");
  });
});
