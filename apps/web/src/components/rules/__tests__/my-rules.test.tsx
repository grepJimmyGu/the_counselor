/** @vitest-environment jsdom */

/**
 * PRD-43e §3.3 — My Rules.
 *
 * Nearly every claim here is about what the surface REFUSES to do. A rules
 * list is easy to build as a checklist of things the user hasn't finished;
 * the whole point of the object is that some rules ARE finished, and saying
 * otherwise turns the packet's best output into a deficiency notice.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const listRules = vi.fn();
const deleteRule = vi.fn();
const promoteRule = vi.fn();
vi.mock("@/lib/api", () => ({
  listRules: (...a: unknown[]) => listRules(...(a as [])),
  deleteRule: (...a: unknown[]) => deleteRule(...(a as [])),
  promoteRule: (...a: unknown[]) => promoteRule(...(a as [])),
}));

import { MyRules } from "../my-rules";
import type { Rule } from "@/lib/contracts";

const BEHAVIOURAL: Rule = {
  id: "r1",
  rule_type: "entry",
  scope: "behavioural",
  name: "Stop entering oversold",
  conditions: {},
  source: "trade_analysis",
  source_analysis_id: "timing-1",
  sample_size: 8,
  historical_effect: "0 winners in 8, −11.8% median drawdown",
  confidence: "low",
  status: "saved",
  evidence: null,
  included_in_validated_playbook: [],
  created_at: "2026-08-28T00:00:00",
  is_terminal: true,
  can_be_tested: false,
};

const MECHANICAL: Rule = {
  ...BEHAVIOURAL,
  id: "r2",
  rule_type: "exit",
  scope: "mechanical",
  name: "Exit below the 20-day",
  source: "user",
  sample_size: null,
  historical_effect: null,
  is_terminal: false,
  can_be_tested: true,
};

function render_(rules: Rule[]) {
  listRules.mockResolvedValue(rules);
  render(<MyRules backendToken="t" />);
}

beforeEach(() => vi.clearAllMocks());

describe("a behavioural rule", () => {
  it("reads as finished, not as missing a validation", async () => {
    /* THE ONE THAT MATTERS. "Stop entering oversold" — 0 winners in 8 — will
       never pass a walk-forward and is still the most actionable thing the
       product has said. An empty validated chip would turn that into a
       deficiency notice. */
    render_([BEHAVIOURAL]);
    const card = await screen.findByTestId("rule-r1");
    expect(card.textContent).toMatch(/Finished/);
    expect(card.textContent).not.toMatch(/validated/i);
    expect(card.textContent).not.toMatch(/pending/i);
  });

  it("offers promotion without requiring it", async () => {
    /* Constraint 6 — every surface is complete at its level, and the next
       level is offered, never demanded. */
    render_([BEHAVIOURAL]);
    const cta = await screen.findByTestId("rule-promote-r1");
    expect(cta.textContent).toMatch(/Think this works as a market rule too/);
  });

  it("carries its provenance so 'why is this here' has an answer", async () => {
    render_([BEHAVIOURAL]);
    const card = await screen.findByTestId("rule-r1");
    expect(card.textContent).toMatch(/From your trade timing/);
    expect(card.textContent).toMatch(/8 trades/);
    expect(card.textContent).toMatch(/0 winners in 8/);
  });
});

describe("a mechanical rule", () => {
  it("is not offered the promotion path — it is already a market claim", async () => {
    render_([MECHANICAL]);
    await screen.findByTestId("rule-r2");
    expect(screen.queryByTestId("rule-promote-r2")).toBeNull();
  });

  it("shows 'tested on your record' rather than anything stronger", async () => {
    /* The record generates the hypothesis; market history tests it. The two
       claims must never appear as one. */
    render_([{ ...MECHANICAL, status: "tested", evidence: "tested_on_personal_record" }]);
    const card = await screen.findByTestId("rule-r2");
    expect(card.textContent).toMatch(/Tested on your record/);
    expect(card.textContent).not.toMatch(/\bvalidated\b/i);
  });
});

describe("playbook provenance", () => {
  it("says where a rule has been without claiming the rule is proven", async () => {
    render_([{ ...MECHANICAL, included_in_validated_playbook: ["pb-1"] }]);
    const note = await screen.findByTestId("rule-playbooks-r2");
    expect(note.textContent).toMatch(/where this rule has been, not that this rule is proven/);
  });
});

describe("grouping", () => {
  it("groups by the sequence of a decision, not alphabetically", async () => {
    render_([MECHANICAL, BEHAVIOURAL]);
    await screen.findByTestId("my-rules");
    const groups = screen.getAllByTestId(/^rules-group-/).map((g) => g.dataset.testid);
    expect(groups).toEqual(["rules-group-entry", "rules-group-exit"]);
  });

  it("renders no empty category slots", async () => {
    /* Five empty slots would turn a complete set of one rule into a checklist
       someone feels behind on. */
    render_([BEHAVIOURAL]);
    await screen.findByTestId("my-rules");
    expect(screen.queryByTestId("rules-group-sizing")).toBeNull();
    expect(screen.queryByTestId("rules-group-portfolio")).toBeNull();
  });
});

describe("empty and failure", () => {
  it("says nothing is saved yet without implying that is a problem", async () => {
    render_([]);
    const empty = await screen.findByTestId("rules-empty");
    expect(empty.textContent).toMatch(/worth stopping/);
  });

  it("reports a load failure rather than rendering an empty list", async () => {
    /* An empty list and a failed load look identical to a user, and one of
       them is a lie about their data. */
    listRules.mockRejectedValue(new Error("500"));
    render(<MyRules backendToken="t" />);
    await screen.findByTestId("rules-failed");
    expect(screen.queryByTestId("rules-empty")).toBeNull();
  });
});

describe("deleting", () => {
  it("removes the card immediately and tells the server", async () => {
    deleteRule.mockResolvedValue(undefined);
    render_([BEHAVIOURAL]);
    fireEvent.click(await screen.findByTestId("rule-delete-r1"));
    await waitFor(() => expect(screen.queryByTestId("rule-r1")).toBeNull());
    expect(deleteRule).toHaveBeenCalledWith("t", "r1");
  });
});
