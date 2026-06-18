import { describe, expect, it } from "vitest";
import {
  RECOMMENDED_TEMPLATES,
  getRecommendedTemplate,
  type ComposerTemplate,
} from "../recommended-templates";

describe("recommended-templates registry", () => {
  it("exposes best_momentum as a composer template on sp500", () => {
    const t = getRecommendedTemplate("best_momentum");
    expect(t?.kind).toBe("composer");
    const c = t as ComposerTemplate;
    expect(c.universe_id).toBe("sp500");
    expect(c.rules.length).toBe(6);
  });

  it("best_momentum rules 2+ carry logic_with_prior (omitting it 500s the scan)", () => {
    const c = getRecommendedTemplate("best_momentum") as ComposerTemplate;
    c.rules.slice(1).forEach((r) => {
      expect(r.logic_with_prior).toBe("AND");
    });
    // The first rule must NOT carry one.
    expect(c.rules[0].logic_with_prior ?? null).toBeNull();
  });

  it("uses rank_return_6m on its 0–1 scale (not 0–100)", () => {
    const c = getRecommendedTemplate("best_momentum") as ComposerTemplate;
    const rank = c.rules.find((r) => r.primitive_id === "rank_return_6m");
    expect(typeof rank?.threshold).toBe("number");
    expect(rank?.threshold as number).toBeLessThanOrEqual(1);
  });

  it("best_momentum rules all use primitive_id + an operator (the scan keys on primitive_id)", () => {
    const c = getRecommendedTemplate("best_momentum") as ComposerTemplate;
    for (const r of c.rules) {
      expect(typeof r.primitive_id).toBe("string");
      expect(r.primitive_id).toBeTruthy();
      expect(r.operator).toBeTruthy();
    }
  });

  it("best_momentum omits the unscannable primitives (f_score, supertrend) from its rules", () => {
    const c = getRecommendedTemplate("best_momentum") as ComposerTemplate;
    const ids = c.rules.map((r) => r.primitive_id);
    expect(ids).not.toContain("f_score");
    expect(ids).not.toContain("supertrend_above_price");
    // rank_composite_score is unpopulated in the snapshot — must not be a rule.
    expect(ids).not.toContain("rank_composite_score");
    // …but they're surfaced as deferred for transparency.
    expect(c.deferred?.some((d) => d.startsWith("f_score"))).toBe(true);
    expect(c.deferred?.some((d) => d.startsWith("rank_composite_score"))).toBe(true);
  });

  it("exposes rising_attention as a sentiment template routing to its toolkit", () => {
    const t = getRecommendedTemplate("rising_attention");
    expect(t?.kind).toBe("sentiment");
    if (t?.kind === "sentiment") {
      expect(t.toolkit_id).toBe("rising_attention");
    }
  });

  it("returns undefined for an unknown id", () => {
    expect(getRecommendedTemplate("nope")).toBeUndefined();
  });

  it("every template has a unique id, name, category, and tagline", () => {
    const ids = new Set<string>();
    for (const t of RECOMMENDED_TEMPLATES) {
      expect(t.id).toBeTruthy();
      expect(t.name).toBeTruthy();
      expect(t.category).toBeTruthy();
      expect(t.tagline).toBeTruthy();
      expect(ids.has(t.id)).toBe(false);
      ids.add(t.id);
    }
  });
});
