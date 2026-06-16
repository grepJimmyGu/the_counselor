/**
 * PRD-22c slice (c) — kind-dispatch rule editor tests.
 *
 * Verifies the rule card dispatches on output_kind to the right widget, and
 * each widget serializes to the StrategyRule operator the engine learned in
 * slice (a).
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { RuleKindEditor } from "@/lib/flows/bricks/custom-build-rule-kind-editor";
import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import type { SignalOutputKind, SignalPrimitive } from "@/lib/contracts";

function mkRule(
  outputKind: SignalOutputKind,
  over: Partial<BuildRule> = {},
): BuildRule {
  return {
    uid: "u1",
    primitive_id: "x",
    primitive: {
      id: "x",
      name: "Test Primitive",
      output_kind: outputKind,
    } as SignalPrimitive,
    primitive_params: {},
    logic_with_prior: null,
    ...over,
  };
}

describe("RuleKindEditor — dispatch", () => {
  it.each([
    ["value", "value-rule"],
    ["event", "event-rule"],
    ["level", "level-rule"],
    ["cross", "cross-rule"],
    ["regime", "regime-rule"],
    ["distance", "distance-rule"],
    ["divergence", "divergence-rule"],
  ] as const)("renders %s primitive → <%s>", (kind, testid) => {
    render(<RuleKindEditor rule={mkRule(kind)} onChange={vi.fn()} />);
    expect(screen.getByTestId(testid)).toBeTruthy();
  });
});

describe("RuleKindEditor — serialization", () => {
  it("EVENT normalizes to operator 'fires'", () => {
    const onChange = vi.fn();
    render(<RuleKindEditor rule={mkRule("event")} onChange={onChange} />);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ operator: "fires", threshold: undefined }),
    );
  });

  it("LEVEL normalizes to operator 'is_true'", () => {
    const onChange = vi.fn();
    render(<RuleKindEditor rule={mkRule("level")} onChange={onChange} />);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ operator: "is_true" }),
    );
  });

  it("CROSS defaults to crosses_up; Down → crosses_down", () => {
    const onChange = vi.fn();
    render(
      <RuleKindEditor
        rule={mkRule("cross", { operator: "crosses_up" })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Down"));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ operator: "crosses_down" }),
    );
  });

  it("REGIME On/Off → equals 1 / 0", () => {
    const onChange = vi.fn();
    render(
      <RuleKindEditor
        rule={mkRule("regime", { operator: "equals", threshold: 1 })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Off"));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ operator: "equals", threshold: 0 }),
    );
  });

  it("DISTANCE serializes a {min,max} range", () => {
    const onChange = vi.fn();
    render(
      <RuleKindEditor
        rule={mkRule("distance", {
          operator: "in_range",
          threshold: { min: -25, max: -2 },
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("min"), { target: { value: "-30" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        operator: "in_range",
        threshold: { min: -30, max: -2 },
      }),
    );
  });

  it("DIVERGENCE Bearish → divergence_bearish", () => {
    const onChange = vi.fn();
    render(
      <RuleKindEditor
        rule={mkRule("divergence", { operator: "divergence_bullish" })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Bearish"));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ operator: "divergence_bearish" }),
    );
  });

  it("VALUE keeps the threshold operator + numeric value", () => {
    const onChange = vi.fn();
    render(
      <RuleKindEditor
        rule={mkRule("value", { operator: "gt", threshold: 30 })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByDisplayValue("30"), { target: { value: "40" } });
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ threshold: 40 }),
    );
  });
});
