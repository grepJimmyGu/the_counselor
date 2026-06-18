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
    expect(c.rules.length).toBe(9);
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
    // …but they're surfaced as deferred for transparency.
    expect(c.deferred?.some((d) => d.startsWith("f_score"))).toBe(true);
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
