/** @vitest-environment jsdom */

/**
 * PRD-13b — flow definition smoke tests.
 *
 * Mocks the brick implementations so the test drives the runtime
 * directly: register portfolio-mode → render <FlowProvider> →
 * verify each step renders + advances + context propagates.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";

// Force the bricks to mock-able placeholders BEFORE importing portfolio-mode.
vi.mock("../bricks/portfolio-upload", () => ({
  PortfolioUpload: (props: {
    updateContext: (patch: unknown) => void;
    advance: () => void;
  }) => (
    <div data-testid="step-upload">
      <button
        data-testid="upload-advance"
        onClick={() => {
          props.updateContext({ holdings: [{ ticker: "AAPL", weight: 1.0 }] });
          props.advance();
        }}
      >
        upload-advance
      </button>
    </div>
  ),
}));

vi.mock("../bricks/portfolio-diagnosis", () => ({
  PortfolioDiagnosis: (props: { advance: () => void }) => (
    <div data-testid="step-diagnose">
      <button data-testid="diagnose-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

vi.mock("../bricks/overlay-picker", () => ({
  OverlayPicker: (props: { advance: () => void }) => (
    <div data-testid="step-overlay">
      <button data-testid="overlay-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

vi.mock("../bricks/portfolio-summary", () => ({
  PortfolioSummary: (props: { advance: () => void }) => (
    <div data-testid="step-summary">
      <button data-testid="summary-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

// Sprint 2 (Mode 1 refactor) consolidated the per-mode backtest /
// review / save bricks into mode-agnostic <FlowBacktest> / <FlowReview>
// / <FlowSave>. The mocks below intercept those modules.
vi.mock("../bricks/flow-backtest", () => ({
  FlowBacktest: (props: { advance: () => void }) => (
    <div data-testid="step-backtest">
      <button data-testid="backtest-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

vi.mock("../bricks/flow-review", () => ({
  FlowReview: (props: { advance: () => void }) => (
    <div data-testid="step-review">
      <button data-testid="review-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

vi.mock("../bricks/flow-save", () => ({
  FlowSave: (props: { advance: () => void }) => (
    <div data-testid="step-save">
      <button data-testid="save-advance" onClick={props.advance}>advance</button>
    </div>
  ),
}));

// Bricks are now mocked. Import the flow definition + runtime APIs.
// Note: the static import below evaluates portfolio-mode.ts ONCE, which
// calls registerFlow as a side-effect. beforeEach wipes the registry
// then re-registers `PortfolioModeFlow` directly — this matches the
// pattern PRD-13a's runtime.test.tsx uses for MockFlow.
import { PortfolioModeFlow } from "../portfolio-mode";
import { FlowProvider, FlowShell, startFlow } from "../runtime";
import { __resetRegistryForTests, getFlow, registerFlow } from "../registry";
import { __resetCopyForTests } from "../copy";

beforeEach(() => {
  window.sessionStorage.clear();
  __resetRegistryForTests();
  __resetCopyForTests();
  registerFlow(PortfolioModeFlow);
});

afterEach(() => {
  window.sessionStorage.clear();
});

function renderShell() {
  return render(
    <FlowProvider flowId="portfolio_mode">
      <FlowShell />
    </FlowProvider>,
  );
}

describe("portfolio-mode FlowDefinition", () => {
  it("is registered in the flow registry on import", () => {
    expect(getFlow("portfolio_mode")).toBeDefined();
    expect(getFlow("portfolio_mode")?.steps.map((s) => s.id)).toEqual([
      "upload",
      "diagnose",
      "overlay",
      "summary",
      "backtest",
      "review",
      "save",
    ]);
  });

  it("advertises both documented triggers", () => {
    const triggers = getFlow("portfolio_mode")?.triggers ?? [];
    expect(triggers).toContain("home/upload_portfolio");
    expect(triggers).toContain("builders/multi_ticker_use_my_portfolio");
  });

  it("renders the upload step first", () => {
    renderShell();
    expect(screen.getByTestId("step-upload")).toBeTruthy();
  });

  it("walks through every step in order when advance fires", () => {
    renderShell();
    fireEvent.click(screen.getByTestId("upload-advance"));
    expect(screen.getByTestId("step-diagnose")).toBeTruthy();
    fireEvent.click(screen.getByTestId("diagnose-advance"));
    expect(screen.getByTestId("step-overlay")).toBeTruthy();
    fireEvent.click(screen.getByTestId("overlay-advance"));
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
      fireEvent.click(screen.getByTestId("upload-advance"));
    });
    // Runtime debounces persistence by 250ms — advance the timer
    // to flush the write to sessionStorage.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    const raw = window.sessionStorage.getItem("livermore_flow_portfolio_mode");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.context.holdings).toEqual([{ ticker: "AAPL", weight: 1.0 }]);
    expect(parsed.currentStepId).toBe("diagnose");
    vi.useRealTimers();
  });

  it("startFlow seeds sessionStorage for /flow/portfolio_mode", () => {
    startFlow("portfolio_mode", { initialContext: { fromTrigger: "test/start" } });
    const raw = window.sessionStorage.getItem("livermore_flow_portfolio_mode");
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("portfolio_mode");
    expect(parsed.currentStepId).toBe("upload");
    expect(parsed.context.fromTrigger).toBe("test/start");
  });
});
