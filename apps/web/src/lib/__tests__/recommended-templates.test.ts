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

  it("ships a gallery of at least 10 recommended templates", () => {
    expect(RECOMMENDED_TEMPLATES.length).toBeGreaterThanOrEqual(10);
  });

  it("every composer preset obeys the fold contract and references no degenerate primitive", () => {
    const composers = RECOMMENDED_TEMPLATES.filter(
      (t): t is ComposerTemplate => t.kind === "composer",
    );
    expect(composers.length).toBeGreaterThanOrEqual(5);
    for (const c of composers) {
      expect(c.universe_id).toBe("sp500");
      expect(c.rules.length).toBeGreaterThan(0);
      c.rules.forEach((r, i) => {
        expect(typeof r.primitive_id).toBe("string");
        expect(r.primitive_id).toBeTruthy();
        expect(r.operator).toBeTruthy();
        // First rule's fold must be null; every later one must be set.
        if (i === 0) expect(r.logic_with_prior ?? null).toBeNull();
        else expect(r.logic_with_prior).toBe("AND");
      });
      // No live preset may reference the known all-zero primitive (PR #234/#240).
      expect(c.rules.some((r) => r.primitive_id === "rank_composite_score")).toBe(
        false,
      );
    }
  });

  it("exposes the four added sentiment toolkits, each routing to its toolkit_id", () => {
    for (const id of [
      "positive_catalyst",
      "news_community_confirmed",
      "sentiment_reversal",
      "community_hype",
    ]) {
      const t = getRecommendedTemplate(id);
      expect(t?.kind).toBe("sentiment");
      if (t?.kind === "sentiment") expect(t.toolkit_id).toBe(id);
    }
    // The display override is present where the shown name differs from the toolkit.
    const mb = getRecommendedTemplate("news_community_confirmed");
    if (mb?.kind === "sentiment") expect(mb.display_label).toBe("Mainstream Buyers");
  });
});
