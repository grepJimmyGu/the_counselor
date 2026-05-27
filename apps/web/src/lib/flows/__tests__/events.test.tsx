/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { FlowProvider, FlowShell } from "../runtime";
import { __resetRegistryForTests, registerFlow } from "../registry";
import { MockFlow } from "./fixtures/mock-flow";
import type { FlowEvent } from "../types";

beforeEach(() => {
  __resetRegistryForTests();
  registerFlow(MockFlow);
});

afterEach(() => {
  vi.useRealTimers();
});

function eventTypes(calls: Array<[FlowEvent]>): string[] {
  return calls.map((c) => c[0].type);
}

describe("events — ordering across a full flow", () => {
  it("fires flow_started → step_entered on mount", () => {
    const onEvent = vi.fn();
    render(
      <FlowProvider flowId="mock_flow" onEvent={onEvent}>
        <FlowShell />
      </FlowProvider>
    );
    const types = eventTypes(onEvent.mock.calls as Array<[FlowEvent]>);
    expect(types[0]).toBe("flow_started");
    expect(types[1]).toBe("step_entered");
    expect((onEvent.mock.calls[1][0] as FlowEvent).type).toBe("step_entered");
    expect(
      (onEvent.mock.calls[1][0] as FlowEvent & { stepId: string }).stepId
    ).toBe("step1");
  });

  it("fires step_exited → step_entered on advance", () => {
    const onEvent = vi.fn();
    render(
      <FlowProvider flowId="mock_flow" onEvent={onEvent}>
        <FlowShell />
      </FlowProvider>
    );
    onEvent.mockClear();
    fireEvent.click(screen.getByTestId("advance"));
    const types = eventTypes(onEvent.mock.calls as Array<[FlowEvent]>);
    expect(types).toEqual(["step_exited", "step_entered"]);
  });

  it("fires step_exited → flow_completed on terminal advance", () => {
    const onEvent = vi.fn();
    render(
      <FlowProvider flowId="mock_flow" onEvent={onEvent}>
        <FlowShell />
      </FlowProvider>
    );
    fireEvent.click(screen.getByTestId("advance")); // step1 → step2
    fireEvent.click(screen.getByTestId("advance")); // step2 → step3
    onEvent.mockClear();
    fireEvent.click(screen.getByTestId("advance")); // step3 → complete
    const types = eventTypes(onEvent.mock.calls as Array<[FlowEvent]>);
    expect(types).toEqual(["step_exited", "flow_completed"]);
  });
});

describe("events — step_idle timing", () => {
  it("fires step_idle 300ms after step mount when no interaction", () => {
    vi.useFakeTimers();
    const onEvent = vi.fn();
    render(
      <FlowProvider flowId="mock_flow" onEvent={onEvent}>
        <FlowShell />
      </FlowProvider>
    );

    expect(
      eventTypes(onEvent.mock.calls as Array<[FlowEvent]>).includes("step_idle")
    ).toBe(false);

    act(() => {
      vi.advanceTimersByTime(310);
    });

    const idle = (onEvent.mock.calls as Array<[FlowEvent]>).find(
      (c) => c[0].type === "step_idle"
    );
    expect(idle).toBeDefined();
    expect((idle![0] as FlowEvent & { stepId: string }).stepId).toBe("step1");
  });

  it("does NOT fire step_idle when the user interacts before 300ms", () => {
    vi.useFakeTimers();
    const onEvent = vi.fn();
    render(
      <FlowProvider flowId="mock_flow" onEvent={onEvent}>
        <FlowShell />
      </FlowProvider>
    );
    act(() => {
      // Fire a keydown on window before the 300ms tick.
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
      vi.advanceTimersByTime(310);
    });
    const idle = (onEvent.mock.calls as Array<[FlowEvent]>).find(
      (c) => c[0].type === "step_idle"
    );
    expect(idle).toBeUndefined();
  });
});
