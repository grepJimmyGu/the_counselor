/** @vitest-environment jsdom */

import { describe, expect, it } from "vitest";

import type { SignalPrimitive } from "@/lib/contracts";
import {
  applyTemplateThresholdsToRules,
  buildCustomBuildStrategyJson,
} from "../custom-build-strategy-json";
import type {
  BuildRule,
  CustomBuildModeContext,
} from "../custom-build-mode-context";

function _primitive(id: string): SignalPrimitive {
  return {
    id,
    category: "mean_reversion",
    family: id.toUpperCase(),
    name: id.toUpperCase(),
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
  };
}

function _rule(
  primitiveId: string,
  overrides: Partial<BuildRule> = {},
): BuildRule {
  return {
    uid: `${primitiveId}-uid`,
    primitive_id: primitiveId,
    primitive: _primitive(primitiveId),
    primitive_params: {},
    operator: "gt",
    threshold: undefined,
    logic_with_prior: null,
    ...overrides,
  };
}

function _ctx(rules: BuildRule[], symbol: string | null = "SPY"): CustomBuildModeContext {
  return {
    fromTrigger: "test",
    symbol,
    rules,
    active_execution_enabled: false,
  };
}

// ── buildCustomBuildStrategyJson ─────────────────────────────────────────


describe("buildCustomBuildStrategyJson", () => {
  it("produces a valid StrategyJson for one rule", () => {
    const result = buildCustomBuildStrategyJson(
      _ctx([_rule("rsi", { threshold: 30, operator: "lt" })]),
    );
    expect(result.strategy_type).toBe("custom_build");
    expect(result.universe).toEqual(["SPY"]);
    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].primitive_id).toBe("rsi");
    expect(result.rules[0].threshold).toBe(30);
    expect(result.rules[0].operator).toBe("lt");
    expect(result.rules[0].logic_with_prior).toBeNull();
  });

  it("uppercases the symbol", () => {
    const result = buildCustomBuildStrategyJson(
      _ctx([_rule("rsi")], "nvda"),
    );
    expect(result.universe).toEqual(["NVDA"]);
  });

  it("uses the symbol from opts when provided (overrides context)", () => {
    const result = buildCustomBuildStrategyJson(_ctx([_rule("rsi")], "SPY"), {
      symbol: "AAPL",
    });
    expect(result.universe).toEqual(["AAPL"]);
  });

  it("throws when no symbol is set", () => {
    expect(() =>
      buildCustomBuildStrategyJson(_ctx([_rule("rsi")], null)),
    ).toThrow(/symbol/);
  });

  it("throws when no rules are present", () => {
    expect(() => buildCustomBuildStrategyJson(_ctx([]))).toThrow(/rule/);
  });

  it("throws when first rule has a logic_with_prior set", () => {
    expect(() =>
      buildCustomBuildStrategyJson(
        _ctx([_rule("rsi", { logic_with_prior: "AND" })]),
      ),
    ).toThrow(/First rule/);
  });

  it("throws when a subsequent rule is missing logic_with_prior", () => {
    expect(() =>
      buildCustomBuildStrategyJson(
        _ctx([
          _rule("rsi"),
          _rule("bbands", { logic_with_prior: null }),
        ]),
      ),
    ).toThrow(/missing AND\/OR/);
  });

  it("preserves multi-rule order and operators", () => {
    const result = buildCustomBuildStrategyJson(
      _ctx([
        _rule("rsi", { threshold: 30, operator: "lt" }),
        _rule("bbands", {
          threshold: 0.2,
          operator: "lt",
          logic_with_prior: "AND",
        }),
        _rule("sma", {
          threshold: 100,
          operator: "gt",
          logic_with_prior: "OR",
        }),
      ]),
    );
    expect(result.rules).toHaveLength(3);
    expect(result.rules[0].logic_with_prior).toBeNull();
    expect(result.rules[1].logic_with_prior).toBe("AND");
    expect(result.rules[2].logic_with_prior).toBe("OR");
  });

  it("includes primitive_params only when non-empty (compact payload)", () => {
    const result = buildCustomBuildStrategyJson(
      _ctx([
        _rule("rsi", { primitive_params: { period: 21 } }),
        _rule("bbands", { primitive_params: {}, logic_with_prior: "AND" }),
      ]),
    );
    expect(result.rules[0].primitive_params).toEqual({ period: 21 });
    expect(result.rules[1].primitive_params).toBeUndefined();
  });

  it("uses sensible defaults for strategy_name, dates, capital", () => {
    const result = buildCustomBuildStrategyJson(_ctx([_rule("rsi")]));
    expect(result.strategy_name).toContain("Custom build");
    expect(result.strategy_name).toContain("RSI");
    expect(result.initial_capital).toBe(100_000);
    expect(result.rebalance_frequency).toBe("monthly");
    expect(result.benchmark).toBe("SPY");
    // Dates are ISO YYYY-MM-DD; just check they look right.
    expect(result.start_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result.end_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("forwards opts overrides for benchmark, capital, dates", () => {
    const result = buildCustomBuildStrategyJson(_ctx([_rule("rsi")]), {
      benchmark: "QQQ",
      initial_capital: 50_000,
      start_date: "2020-01-01",
      end_date: "2023-01-01",
      strategy_name: "Custom name",
    });
    expect(result.benchmark).toBe("QQQ");
    expect(result.initial_capital).toBe(50_000);
    expect(result.start_date).toBe("2020-01-01");
    expect(result.end_date).toBe("2023-01-01");
    expect(result.strategy_name).toBe("Custom name");
  });
});


// ── applyTemplateThresholdsToRules ───────────────────────────────────────

describe("applyTemplateThresholdsToRules", () => {
  it("returns rules unchanged when no template thresholds match", () => {
    const rules = [_rule("rsi")];
    const out = applyTemplateThresholdsToRules(rules, {});
    expect(out).toEqual(rules);
  });

  it("applies threshold-shaped keys (lower → lt operator) and parameter overrides separately", () => {
    const out = applyTemplateThresholdsToRules(
      [_rule("rsi")],
      {
        rsi: { period: 21, lower: 30 },
      },
    );
    expect(out[0].primitive_params.period).toBe(21);
    // `lower` → operator "lt" + threshold 30.
    expect(out[0].operator).toBe("lt");
    expect(out[0].threshold).toBe(30);
  });

  it("applies enter_lt and exit_gte threshold keys correctly", () => {
    const out = applyTemplateThresholdsToRules(
      [_rule("bbands")],
      {
        bbands: { period: 20, std_dev: 2.0, enter_lt: 0.0, exit_gte: 0.5 },
      },
    );
    expect(out[0].primitive_params.period).toBe(20);
    expect(out[0].primitive_params.std_dev).toBe(2.0);
    // First threshold-shaped key wins (enter_lt).
    expect(out[0].operator).toBe("lt");
    expect(out[0].threshold).toBe(0);
  });

  it("leaves non-matching rules untouched", () => {
    const rules = [_rule("rsi"), _rule("sma")];
    const out = applyTemplateThresholdsToRules(rules, {
      rsi: { lower: 30 },
    });
    expect(out[0].threshold).toBe(30);
    expect(out[1].threshold).toBeUndefined();
  });
});
