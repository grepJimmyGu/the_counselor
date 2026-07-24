/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import type { BottleneckThesis } from "@/lib/contracts";

import { ThesisPanel } from "../_thesis-panel";

function thesis(overrides: Partial<BottleneckThesis> = {}): BottleneckThesis {
  return {
    symbol: "AXTI",
    verdict: "insufficient_evidence",
    fit_score: 5,
    max_score: 24,
    veto: false,
    band: "watch_item",
    architecture_transition: {
      from_state: "electrical interconnect",
      to_state: "optical interconnect",
      what_becomes_scarce: "InP substrates",
      transition_exists: true,
    },
    chain_map: [{ hop: 2, layer: "Substrate mfg", named_players: ["AXTI"], status: "constrained" }],
    chokepoint_argument: {
      if_stops: "AXT InP supply stops",
      downstream_breaks: "optical transceivers",
      mechanism: "leading InP producer",
      nearest_substitute: "GaAs",
      substitute_status: "limited",
    },
    evidence_table: [
      { claim: "AXTI is a customer of Casela", tier: "A", source: "8-K", date: "2026-06-17", falsifier: "agreement terminated" },
    ],
    forward_financials: {
      trailing_meaningful: false,
      trailing_note: "pre-ramp; trailing revenue near-meaningless",
      drivers: [{ driver: "Revenue", low: "-15%", base: "-5%", high: "10%", source: "trend" }],
      market_cap: "$2.45B",
      trailing_revenue: "$88M",
      gaap_gross_margin: "12.7%",
      contracted_forward_revenue: "unknown",
      capital_required: "unknown",
      funded_by: "unknown",
    },
    gates: [
      { n: 7, name: "Financing", score: "PASS", tier: "A", note: "cash runway >9y" },
      { n: 1, name: "Chokepoint", score: "0", tier: "F", note: "" },
    ],
    catalyst_calendar: [{ date: "2027", event: "Casela purchase commitment", confirms_or_breaks: "confirms ramp" }],
    invalidation_tests: ["Casela fails to purchase the committed InP quantity"],
    risk_profile: { binariness: "low", liquidity: "low", crowding: "unknown", factor_overlap: "low" },
    could_not_verify: ["market share"],
    ...overrides,
  };
}

describe("ThesisPanel", () => {
  it("renders the graded thesis with its sections, fit score, and disclaimer", () => {
    render(<ThesisPanel thesis={thesis()} />);
    expect(screen.getByText(/insufficient evidence/i)).toBeTruthy();
    expect(screen.getByText(/optical interconnect/i)).toBeTruthy(); // transition
    expect(screen.getByText(/Substrate mfg/)).toBeTruthy(); // chain hop
    expect(screen.getByText(/AXTI is a customer of Casela/)).toBeTruthy(); // evidence
    expect(screen.getByText(/Casela fails to purchase/)).toBeTruthy(); // invalidation
    expect(screen.getByText(/never a recommendation/i)).toBeTruthy(); // disclaimer
    expect(screen.getByText(/how this is built/i)).toBeTruthy(); // reader's guide
  });

  it("flags a veto in the band", () => {
    render(<ThesisPanel thesis={thesis({ veto: true, fit_score: 4 })} />);
    expect(screen.getByText(/watch item.*veto/i)).toBeTruthy();
  });

  it("shows an honest message when no thesis has been generated", () => {
    render(
      <ThesisPanel
        thesis={thesis({ message: "No bottleneck thesis has been generated for this company yet." })}
      />,
    );
    expect(screen.getByText(/No bottleneck thesis has been generated/i)).toBeTruthy();
  });
});
