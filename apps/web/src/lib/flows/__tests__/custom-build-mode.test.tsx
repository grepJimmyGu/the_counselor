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
  matchSignalCombosToTemplates: vi.fn(),
}));

import { getSignalPrimitives } from "@/lib/api";
import type {
  SignalPrimitive,
  SignalPrimitivesResponse,
} from "@/lib/contracts";
import { CustomBuildCanvas } from "../bricks/custom-build-canvas";
import { CustomBuildActiveExecutionScaffold } from "../bricks/custom-build-active-execution-scaffold";
import { CustomBuildRuleCard } from "../bricks/custom-build-rule-card";
import { CustomBuildRuleComposer } from "../bricks/custom-build-rule-composer";
import type {
  BuildRule,
  CustomBuildModeContext,
} from "../custom-build-mode-context";
import { CustomBuildModeFlow } from "../custom-build-mode";
import { getFlow } from "../registry";

function _primitive(
  id: string,
  overrides: Partial<SignalPrimitive> = {},
): SignalPrimitive {
  return {
    id,
    category: "mean_reversion",
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
        description: "Look-back window",
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

function _catalog(): SignalPrimitivesResponse {
  return {
    primitives: [
      _primitive("sma", { category: "trend", family: "MA", name: "SMA" }),
      _primitive("rsi", { name: "RSI" }),
      _primitive("bbands", { name: "Bollinger" }),
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
    version_hash: "v1",
  };
}

function _rule(uid: string, primitiveId: string = "rsi"): BuildRule {
  return {
    uid,
    primitive_id: primitiveId,
    primitive: _primitive(primitiveId),
    primitive_params: {},
    operator: "gt",
    threshold: undefined,
    logic_with_prior: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (getSignalPrimitives as ReturnType<typeof vi.fn>).mockResolvedValue(_catalog());
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Flow registration ─────────────────────────────────────────────────────

describe("custom_build_mode flow registration", () => {
  it("is registered with the runtime under its id", () => {
    expect(getFlow("custom_build_mode")).toBeTruthy();
    expect(CustomBuildModeFlow.id).toBe("custom_build_mode");
    expect(CustomBuildModeFlow.triggers).toContain(
      "strategy_builders/custom_build_cta",
    );
  });

  it("has the compose_signals step as terminal v1 entry", () => {
    expect(CustomBuildModeFlow.initialStepId).toBe("compose_signals");
    const step = CustomBuildModeFlow.steps.find(
      (s) => s.id === "compose_signals",
    );
    expect(step).toBeTruthy();
    expect(step?.next?.({} as CustomBuildModeContext)).toBeNull();
  });

  it("validates that at least one rule has been picked", () => {
    const step = CustomBuildModeFlow.steps[0];
    const ctxEmpty = {
      fromTrigger: "test",
      rules: [],
      symbol: null,
      active_execution_enabled: false,
    } satisfies CustomBuildModeContext;
    expect(step.validate?.(ctxEmpty)).toBe("Add at least one rule.");

    const ctxFilled = { ...ctxEmpty, rules: [_rule("u1")] };
    expect(step.validate?.(ctxFilled)).toBe(true);
  });
});

// ── RuleComposer ──────────────────────────────────────────────────────────

describe("CustomBuildRuleComposer", () => {
  it("renders AND/OR toggle and fires onChange", () => {
    const onChange = vi.fn();
    render(<CustomBuildRuleComposer value="AND" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("composer-or"));
    expect(onChange).toHaveBeenCalledWith("OR");
  });
});

// ── ActiveExecutionScaffold ───────────────────────────────────────────────

describe("CustomBuildActiveExecutionScaffold", () => {
  it("renders disabled by default (PRD-16b pitfall B)", () => {
    render(
      <CustomBuildActiveExecutionScaffold value={false} onChange={() => {}} />,
    );
    const btn = screen.getByTestId("active-execution-toggle") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(screen.getByText(/Coming soon/i)).toBeTruthy();
  });

  it("flips when disabled=false (PRD-16c will set this)", () => {
    const onChange = vi.fn();
    render(
      <CustomBuildActiveExecutionScaffold
        value={false}
        onChange={onChange}
        disabled={false}
      />,
    );
    fireEvent.click(screen.getByTestId("active-execution-toggle"));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

// ── RuleCard ─────────────────────────────────────────────────────────────

describe("CustomBuildRuleCard", () => {
  it("renders the rule's primitive name + description", () => {
    render(
      <CustomBuildRuleCard
        rule={_rule("u1", "rsi")}
        index={0}
        onChange={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByText("rsi")).toBeTruthy();
  });

  it("calls onRemove when the Remove button is clicked", () => {
    const onRemove = vi.fn();
    render(
      <CustomBuildRuleCard
        rule={_rule("u1")}
        index={0}
        onChange={() => {}}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByTestId("rule-remove-u1"));
    expect(onRemove).toHaveBeenCalled();
  });

  it("updates primitive_params on input change", () => {
    const onChange = vi.fn();
    render(
      <CustomBuildRuleCard
        rule={_rule("u1")}
        index={0}
        onChange={onChange}
        onRemove={() => {}}
      />,
    );
    fireEvent.change(screen.getByTestId("rule-param-u1-period"), {
      target: { value: "21" },
    });
    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls[0][0];
    expect(next.primitive_params.period).toBe(21);
  });

  it("updates threshold on input change", () => {
    const onChange = vi.fn();
    render(
      <CustomBuildRuleCard
        rule={_rule("u1")}
        index={0}
        onChange={onChange}
        onRemove={() => {}}
      />,
    );
    fireEvent.change(screen.getByTestId("rule-threshold-u1"), {
      target: { value: "30" },
    });
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].threshold).toBe(30);
  });

  it("hides the threshold editor for binary primitives (donchian_breakout)", () => {
    render(
      <CustomBuildRuleCard
        rule={_rule("u1", "donchian_breakout")}
        index={0}
        onChange={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.queryByTestId("rule-threshold-u1")).toBeNull();
    expect(screen.getByText(/binary signal/i)).toBeTruthy();
  });
});

// ── Canvas — integrates rule cards + composer + catalog ──────────────────

function _renderCanvas(initial?: Partial<CustomBuildModeContext>) {
  let context: CustomBuildModeContext = {
    fromTrigger: "test",
    symbol: null,
    rules: [],
    active_execution_enabled: false,
    ...initial,
  };
  const updateContext = (patch: Partial<CustomBuildModeContext>) => {
    context = { ...context, ...patch };
    rerender();
  };
  const { rerender: rerenderFn, ...rest } = render(
    <CustomBuildCanvas
      context={context}
      updateContext={updateContext}
      advance={() => {}}
      back={() => {}}
      abort={() => {}}
    />,
  );
  const rerender = () =>
    rerenderFn(
      <CustomBuildCanvas
        context={context}
        updateContext={updateContext}
        advance={() => {}}
        back={() => {}}
        abort={() => {}}
      />,
    );
  return { rest, getContext: () => context };
}

describe("CustomBuildCanvas", () => {
  it("renders the empty-state hint when no rules are picked", () => {
    _renderCanvas();
    expect(screen.getByTestId("custom-build-empty")).toBeTruthy();
  });

  it("appends a rule when the user clicks a catalog card; first rule has logic_with_prior=null", async () => {
    const { getContext } = _renderCanvas();
    await waitFor(() => {
      expect(screen.getByTestId("primitive-card-rsi")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("primitive-card-rsi"));
    const ctx = getContext();
    expect(ctx.rules.length).toBe(1);
    expect(ctx.rules[0].primitive_id).toBe("rsi");
    expect(ctx.rules[0].logic_with_prior).toBeNull();
  });

  it("appends subsequent rules with logic_with_prior='AND'", async () => {
    const { getContext } = _renderCanvas();
    await waitFor(() => {
      expect(screen.getByTestId("primitive-card-rsi")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("primitive-card-rsi"));
    // Wait for re-render with the rule visible.
    await waitFor(() => {
      expect(screen.getByTestId("primitive-card-bbands")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("primitive-card-bbands"));
    const ctx = getContext();
    expect(ctx.rules.length).toBe(2);
    expect(ctx.rules[1].logic_with_prior).toBe("AND");
  });

  it("renders the active-execution scaffold", () => {
    _renderCanvas();
    expect(screen.getByTestId("active-execution-scaffold")).toBeTruthy();
  });
});
