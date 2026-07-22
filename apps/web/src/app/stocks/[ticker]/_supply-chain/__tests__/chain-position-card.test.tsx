/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type { ChainGraph, SupplyChainSummary } from "@/lib/contracts";

import { ChainDiagram } from "../_chain-diagram";
import { ChainPositionCard } from "../_chain-position-card";

function summary(overrides: Partial<SupplyChainSummary> = {}): SupplyChainSummary {
  return {
    symbol: "AXTI",
    verdict: "insufficient_evidence",
    layer_ambiguous: false,
    trailing_metrics_meaningful: true,
    confidence: "insufficient_evidence",
    tests: [],
    dropped_edge_count: 0,
    stage_figures: {},
    ...overrides,
  };
}

describe("ChainPositionCard", () => {
  it("renders no_chain_structure as a first-class state with a fallback role", () => {
    render(
      <ChainPositionCard
        summary={summary({
          verdict: "no_chain_structure",
          confidence: "high",
          fallback_role: "Financial Intermediary",
          message: "No supply-chain bottleneck structure detected.",
        })}
      />
    );
    expect(screen.getByText(/doesn.t apply here/i)).toBeTruthy();
    expect(screen.getByText(/Financial Intermediary/)).toBeTruthy();
  });

  it("renders a chokepoint verdict with the break statement + trailing-metrics flag", () => {
    render(
      <ChainPositionCard
        summary={summary({
          verdict: "chokepoint",
          confidence: "moderate",
          layer: "substrate",
          vertical: "photonics",
          stage: "pre_ramp",
          trailing_metrics_meaningful: false,
          break_statement: "If AXTI stops shipping InP, transceivers break.",
        })}
      />
    );
    expect(screen.getByText("Chokepoint")).toBeTruthy();
    expect(screen.getByText(/transceivers break/)).toBeTruthy();
    expect(screen.getByText(/trailing metrics not meaningful/)).toBeTruthy();
  });

  it("renders insufficient_evidence with its message", () => {
    render(
      <ChainPositionCard
        summary={summary({
          verdict: "insufficient_evidence",
          message: "Supply-chain evidence has not been extracted yet.",
          stage: "mature",
        })}
      />
    );
    expect(screen.getByText("Insufficient evidence")).toBeTruthy();
    expect(screen.getByText(/not been extracted/)).toBeTruthy();
  });
});

describe("ChainDiagram", () => {
  it("shows the being-mapped empty state when there are no edges", () => {
    const g: ChainGraph = { symbol: "AXTI", nodes: [], edges: [], dropped_edge_count: 0 };
    render(<ChainDiagram graph={g} symbol="AXTI" />);
    expect(screen.getByText(/being mapped/i)).toBeTruthy();
  });
});
