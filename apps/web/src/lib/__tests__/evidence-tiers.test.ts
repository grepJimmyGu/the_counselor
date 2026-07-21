import { describe, it, expect } from "vitest";
import {
  EVIDENCE_TIERS,
  TIER_ORDER,
  tierMeta,
  inferTierFromSource,
} from "../evidence-tiers";

describe("evidence ladder definitions", () => {
  it("defines all six tiers, strongest-first", () => {
    expect(TIER_ORDER).toEqual(["A", "B", "C", "D", "E", "F"]);
    expect(Object.keys(EVIDENCE_TIERS)).toHaveLength(6);
    for (const t of TIER_ORDER) {
      expect(tierMeta(t).tier).toBe(t);
      expect(tierMeta(t).meaning.length).toBeGreaterThan(0);
      expect(tierMeta(t).badgeClass.length).toBeGreaterThan(0);
    }
  });
});

describe("inferTierFromSource", () => {
  it("grades primary disclosure as Tier A", () => {
    expect(inferTierFromSource("10-K · Item 1 Business")).toBe("A");
    expect(inferTierFromSource("20-F annual report")).toBe("A");
    expect(inferTierFromSource("Q3 earnings call transcript")).toBe("A");
    expect(inferTierFromSource("8-K official release")).toBe("A");
  });

  it("grades named commercial commitments as Tier B", () => {
    expect(inferTierFromSource("Named design win with a hyperscaler")).toBe("B");
    expect(inferTierFromSource("Disclosed multi-year agreement")).toBe("B");
  });

  it("grades reference-design signals as Tier C", () => {
    expect(inferTierFromSource("Reference design inclusion")).toBe("C");
    expect(inferTierFromSource("Foundry platform listing")).toBe("C");
  });

  it("grades context/incentive sources as Tier E — a peer transcript is not Tier A", () => {
    expect(inferTierFromSource("Peer transcript from a competitor")).toBe("E");
    expect(inferTierFromSource("Sell-side note")).toBe("E");
    expect(inferTierFromSource("Analyst estimate")).toBe("E");
  });

  it("grades social / LLM leads as Tier F", () => {
    expect(inferTierFromSource("Reddit thread")).toBe("F");
    expect(inferTierFromSource("LLM output")).toBe("F");
  });

  it("never launders an unknown source above Tier D", () => {
    expect(inferTierFromSource("Partner page listing")).toBe("D");
    expect(inferTierFromSource("Supply chain and competitor data auto-extracted")).toBe("D");
    expect(inferTierFromSource("some vague provenance note")).toBe("D");
  });
});
