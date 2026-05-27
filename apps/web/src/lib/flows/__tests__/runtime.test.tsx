/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { FlowProvider, FlowShell, startFlow } from "../runtime";
import { __resetRegistryForTests, registerFlow } from "../registry";
import {
  MockFlow,
  clearOnCompleteForTests,
  setOnCompleteForTests,
} from "./fixtures/mock-flow";

const STORAGE_KEY = (id: string) => `livermore_flow_${id}`;

beforeEach(() => {
  __resetRegistryForTests();
  registerFlow(MockFlow);
});

afterEach(() => {
  clearOnCompleteForTests();
  vi.useRealTimers();
});

function renderMock(onEvent?: (e: unknown) => void) {
  return render(
    <FlowProvider flowId="mock_flow" onEvent={onEvent}>
      <FlowShell />
    </FlowProvider>
  );
}

describe("runtime — startFlow", () => {
  it("persists initial state to sessionStorage", () => {
    startFlow("mock_flow", {
      initialContext: { fromTrigger: "test/start" },
    });
    const raw = window.sessionStorage.getItem(STORAGE_KEY("mock_flow"));
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("mock_flow");
    expect(parsed.currentStepId).toBe("step1");
    expect(parsed.context.fromTrigger).toBe("test/start");
  });

  it("throws when the flowId is not registered", () => {
    expect(() =>
      startFlow("does_not_exist", { initialContext: { fromTrigger: "x" } })
    ).toThrow(/unknown flowId/i);
  });
});

describe("runtime — FlowProvider", () => {
  it("renders the initial step", () => {
    renderMock();
    expect(screen.getByTestId("step-title").textContent).toBe("Mock Step 1");
  });

  it("throws clearly when the flow is unknown", () => {
    // Suppress the React error boundary noise during the assertion.
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() =>
      render(
        <FlowProvider flowId="not_registered">
          <FlowShell />
        </FlowProvider>
      )
    ).toThrow(/unknown flowId/i);
    err.mockRestore();
  });
});

describe("runtime — navigation + context", () => {
  it("advance() moves to the next step", () => {
    renderMock();
    fireEvent.click(screen.getByTestId("advance"));
    expect(screen.getByTestId("step-title").textContent).toBe("Mock Step 2");
  });

  it("updateContext + back + advance preserves context across navigation", () => {
    renderMock();
    fireEvent.click(screen.getByTestId("set-x"));
    expect(screen.getByTestId("ctx-x").textContent).toBe("1");

    fireEvent.click(screen.getByTestId("advance"));
    expect(screen.getByTestId("step-title").textContent).toBe("Mock Step 2");
    expect(screen.getByTestId("ctx-x").textContent).toBe("1");

    fireEvent.click(screen.getByTestId("back"));
    expect(screen.getByTestId("step-title").textContent).toBe("Mock Step 1");
    expect(screen.getByTestId("ctx-x").textContent).toBe("1");

    fireEvent.click(screen.getByTestId("advance"));
    expect(screen.getByTestId("ctx-x").textContent).toBe("1");
  });

  it("advance on the terminal step fires onComplete and clears sessionStorage", () => {
    const completeSpy = vi.fn();
    setOnCompleteForTests(completeSpy);

    // Seed sessionStorage so the debounced persist has something to clear.
    window.sessionStorage.setItem(
      STORAGE_KEY("mock_flow"),
      JSON.stringify({
        flowId: "mock_flow",
        currentStepId: "step1",
        context: { fromTrigger: "test" },
      })
    );

    renderMock();
    fireEvent.click(screen.getByTestId("advance")); // → step2
    fireEvent.click(screen.getByTestId("advance")); // → step3
    fireEvent.click(screen.getByTestId("advance")); // → complete

    expect(completeSpy).toHaveBeenCalledOnce();
    expect(window.sessionStorage.getItem(STORAGE_KEY("mock_flow"))).toBeNull();
  });
});

describe("runtime — sessionStorage persistence", () => {
  it("writes state after the 250ms debounce", () => {
    vi.useFakeTimers();
    renderMock();
    act(() => {
      fireEvent.click(screen.getByTestId("set-x"));
      fireEvent.click(screen.getByTestId("advance"));
    });
    // Pre-debounce: nothing yet.
    expect(window.sessionStorage.getItem(STORAGE_KEY("mock_flow"))).toBeNull();
    act(() => {
      vi.advanceTimersByTime(260);
    });
    const raw = window.sessionStorage.getItem(STORAGE_KEY("mock_flow"));
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.currentStepId).toBe("step2");
    expect(parsed.context.x).toBe(1);
  });

  it("resumes the same step + context on remount", () => {
    window.sessionStorage.setItem(
      STORAGE_KEY("mock_flow"),
      JSON.stringify({
        flowId: "mock_flow",
        currentStepId: "step2",
        context: { fromTrigger: "test/resume", x: 1 },
      })
    );

    renderMock();
    expect(screen.getByTestId("step-title").textContent).toBe("Mock Step 2");
    expect(screen.getByTestId("ctx-x").textContent).toBe("1");
  });
});

describe("runtime — abort", () => {
  it("clears sessionStorage and fires flow_aborted", () => {
    const onEvent = vi.fn();
    window.sessionStorage.setItem(
      STORAGE_KEY("mock_flow"),
      JSON.stringify({
        flowId: "mock_flow",
        currentStepId: "step1",
        context: { fromTrigger: "test" },
      })
    );
    renderMock(onEvent);
    fireEvent.click(screen.getByTestId("abort"));
    expect(window.sessionStorage.getItem(STORAGE_KEY("mock_flow"))).toBeNull();
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "flow_aborted", flowId: "mock_flow" })
    );
  });
});
