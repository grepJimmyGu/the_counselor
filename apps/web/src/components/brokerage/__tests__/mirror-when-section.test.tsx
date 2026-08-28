/** @vitest-environment jsdom */

/**
 * PRD-43b P0 — the WHEN section's deep view.
 *
 * The claims under test are almost all about what this section REFUSES to
 * say. It has real numbers for the first time, and the ways it can be wrong
 * are quiet ones: a diagnosis read out of medians that are noise, an MAE gap
 * that silently dropped the same-day trades, a coverage figure that implies
 * the whole record when it measured half.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const getMirrorTiming = vi.fn();
const createRule = vi.fn();
vi.mock("@/lib/api", () => ({
  getMirrorTiming: (...a: unknown[]) => getMirrorTiming(...(a as [])),
  createRule: (...a: unknown[]) => createRule(...(a as [])),
}));

import { MirrorWhenSection } from "../mirror-when-section";
import type { MarkoutProfile, TimingView } from "@/lib/contracts";

const FLAT: MarkoutProfile = {
  horizons: [],
  excluded_beyond_window: 0,
  has_consistent_pattern: false,
};

/** Quartiles that cross zero at every horizon — the first live account. */
const NOISE: MarkoutProfile = {
  horizons: [1, 3, 5, 10, 20].map((h) => ({
    horizon: h,
    n: 33,
    median: -0.014,
    q1: -0.06,
    q3: 0.04,
    straddles_zero: true,
  })),
  excluded_beyond_window: 0,
  has_consistent_pattern: false,
};

/** A profile where the sign actually survives the spread. */
const SIGNAL: MarkoutProfile = {
  horizons: [1, 3, 5, 10, 20].map((h) => ({
    horizon: h,
    n: 40,
    median: -0.03,
    q1: -0.05,
    q3: -0.01,
    straddles_zero: false,
  })),
  excluded_beyond_window: 0,
  has_consistent_pattern: true,
};

const BASE: TimingView = {
  opening_entry_profile: NOISE,
  add_on_profile: FLAT,
  final_exit_profile: FLAT,
  partial_exit_profile: FLAT,
  excursions: {
    winner_mae: -0.0288, winner_n: 6,
    loser_mae: -0.067, loser_n: 26,
    median_capture: 0.506, capture_n: 6,
    same_day_excluded: 1, approximate_boundary: 26,
  },
  setups: [
    { setup: "trend_continuation", n: 7, wins: 1, win_rate: 0.143, median_return: -0.0359, median_mae: -0.0667, median_capture: null },
    { setup: "oversold", n: 4, wins: 0, win_rate: 0, median_return: -0.0411, median_mae: -0.0976, median_capture: null },
    { setup: "unclassified", n: 16, wins: 5, win_rate: 0.312, median_return: -0.0215, median_mae: -0.0546, median_capture: null },
  ],
  outcomes: { giveback: 4, panic_exit: 4 },
  leaks: [
    { key: "giveback", n: 4, dollars: 4349.33 },
    { key: "panic_exit", n: 4, dollars: 3310.23 },
  ],
  coverage: {
    episodes_total: 57, episodes_analysed: 33, symbols_measured: 23,
    excluded: [["UVXY", "no_price_history"]],
    unclassified_entries: 16, classified_entries: 17, unclassified_share: 0.485,
    window_start: "2024-08-27", window_end: "2026-08-28",
  },
};

function render_(over: Partial<TimingView> = {}) {
  getMirrorTiming.mockResolvedValue({ ...BASE, ...over });
  render(<MirrorWhenSection backendToken="t" />);
}

beforeEach(() => vi.clearAllMocks());

describe("a noise profile", () => {
  it("says there is no pattern instead of narrating the medians", async () => {
    /* THE ONE THAT MATTERS MOST. The first real account produced medians of
       −0.03/−1.45/−1.32/−0.45/+1.01% with quartiles of ±5–10% — not
       distinguishable from noise. Letting a story be read out of those
       medians was the v1 script's worst defect, and it is the default path
       here, not an edge case. */
    render_();
    const noise = await screen.findByTestId("when-entry-profile-noise");
    expect(noise.textContent).toMatch(/No consistent timing pattern/);
    expect(noise.textContent).toMatch(/crosses zero at every horizon/);
  });

  it("still shows the numbers, so the claim is checkable", async () => {
    render_();
    const row = await screen.findByTestId("when-markout-3");
    expect(row.textContent).toMatch(/n=33/);
    expect(row.textContent).toMatch(/−1\.4%/);
  });
});

describe("a real pattern", () => {
  it("describes it rather than refusing", async () => {
    render_({ opening_entry_profile: SIGNAL });
    await screen.findByTestId("when-entry-profile");
    expect(screen.queryByTestId("when-entry-profile-noise")).toBeNull();
  });
});

describe("the drawdown gap", () => {
  it("renders winners and losers together, each with its sample size", async () => {
    /* A stop set between these two can still kill a quarter of the winners.
       The numbers are only safe to read next to their Ns. */
    render_();
    const box = await screen.findByTestId("when-excursions");
    expect(box.textContent).toMatch(/−2\.9%/);
    expect(box.textContent).toMatch(/n=6/);
    expect(box.textContent).toMatch(/−6\.7%/);
    expect(box.textContent).toMatch(/n=26/);
  });

  it("states the same-day trades it had to leave out", async () => {
    /* We know the day's range, not where in it the user was. A reader who
       doesn't know these were dropped reads the gap as covering everything. */
    render_();
    const note = await screen.findByTestId("when-sameday-note");
    expect(note.textContent).toMatch(/opened and closed the same day/);
  });

  it("says nothing about same-day exclusions when there were none", async () => {
    render_({ excursions: { ...BASE.excursions, same_day_excluded: 0 } });
    await screen.findByTestId("when-excursions");
    expect(screen.queryByTestId("when-sameday-note")).toBeNull();
  });
});

describe("the setup breakdown", () => {
  it("carries N on every row", async () => {
    render_();
    const row = await screen.findByTestId("when-setup-oversold");
    expect(row.textContent).toMatch(/4/);
  });

  it("shows the unmatched entries as unmatched, never as an 'other' bucket", async () => {
    /* ~40% of a real record matches no category by design, and on the first
       live account that bucket had a BETTER win rate than every named setup.
       That is a signal the taxonomy deserves review — and it is information
       only if it is visible. */
    render_();
    const note = await screen.findByTestId("when-unclassified");
    expect(note.textContent).toMatch(/49% of your entries matched none/);
    expect(screen.queryByText(/\bOther\b/)).toBeNull();
  });
});

describe("coverage", () => {
  it("states the share it measured rather than implying the whole record", async () => {
    /* `price_bars` holds no ETFs or ADRs. On the first live account this was
       33 of 57 episodes and omitted the single most-traded symbol. Saying
       "your trades" here would be a quiet overreach. */
    render_();
    const line = await screen.findByTestId("when-coverage");
    expect(line.textContent).toMatch(/33 of 57 closed positions/);
    expect(line.textContent).toMatch(/no price history/);
  });

  it("drops the caveat when everything was measured", async () => {
    render_({
      coverage: { ...BASE.coverage, episodes_analysed: 57, episodes_total: 57 },
    });
    const line = await screen.findByTestId("when-coverage");
    expect(line.textContent).not.toMatch(/no price history/);
  });
});

describe("the costliest habit", () => {
  it("names the biggest leak in dollars, with its count", async () => {
    render_();
    const leak = await screen.findByTestId("when-leak");
    expect(leak.textContent).toMatch(/\$4,349/);
    expect(leak.textContent).toMatch(/across 4 trades/);
    expect(leak.textContent).toMatch(/letting a gain come back/);
  });
});

describe("failure", () => {
  it("renders nothing rather than taking the summary above it down", async () => {
    /* This is the DEEP view of a section whose summary came from a different
       endpoint. Losing the depth must not lose the summary. */
    getMirrorTiming.mockRejectedValue(new Error("502"));
    const { container } = render(<MirrorWhenSection backendToken="t" />);
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("renders nothing when there are no analysed episodes", async () => {
    render_({ coverage: { ...BASE.coverage, episodes_analysed: 0 } });
    await waitFor(() =>
      expect(screen.queryByTestId("when-deep")).toBeNull(),
    );
  });
});


describe("saving a finding as a rule", () => {
  /* PRD-43e §3.2 — the step that closes the loop. Without it a finding is a
     sentence you read once, and the Rules object has nothing to hold. */

  it("saves a losing setup as a BEHAVIOURAL rule, carrying its provenance", async () => {
    createRule.mockResolvedValue({ id: "r9" });
    render_();
    fireEvent.click(await screen.findByTestId("when-save-setup-oversold"));

    await waitFor(() => expect(createRule).toHaveBeenCalledTimes(1));
    const [token, payload] = createRule.mock.calls[0];
    expect(token).toBe("t");
    expect(payload.scope).toBe("behavioural");
    expect(payload.source).toBe("trade_analysis");
    expect(payload.sample_size).toBe(4);
    expect(payload.historical_effect).toMatch(/0 of 4 worked/);
    /* A behavioural rule enters a Playbook as an EXCLUSION, never as an edge
       — so what is stored is the setup to avoid, not a market condition it
       never earned the right to assert. */
    expect(payload.conditions).toEqual({ exclude_setup: "oversold" });
  });

  it("never labels a P0 finding as a market claim", async () => {
    /* 43b P0 is measurement. The counterfactual rules that could honestly be
       `mechanical` arrive with P1; calling these that now would claim a market
       edge from a description of one person's record. */
    createRule.mockResolvedValue({ id: "r9" });
    render_();
    fireEvent.click(await screen.findByTestId("when-save-setup-oversold"));
    await waitFor(() => expect(createRule).toHaveBeenCalled());
    expect(createRule.mock.calls[0][1].scope).not.toBe("mechanical");
  });

  it("offers no rule for the unclassified bucket", async () => {
    /* "Matched no setup" is not a category, so there is nothing to make a rule
       about — offering one would invent the category the taxonomy withholds. */
    render_();
    await screen.findByTestId("when-setups");
    expect(screen.queryByTestId("when-save-setup-unclassified")).toBeNull();
  });

  it("offers a rule with NO sample floor, because behavioural rules have none", async () => {
    /* §3.1.1 and the §7 DoD: a fact about one's own trades needs no
       significance test. The floor is a `mechanical` concept. The N renders
       beside it either way, so the user decides. */
    createRule.mockResolvedValue({ id: "r9" });
    render_({
      setups: [{ setup: "breakout", n: 2, wins: 0, win_rate: 0,
                 median_return: -0.05, median_mae: -0.08, median_capture: null }],
    });
    expect(await screen.findByTestId("when-save-setup-breakout")).toBeTruthy();
  });

  it("confirms the save rather than leaving the button ambiguous", async () => {
    createRule.mockResolvedValue({ id: "r9" });
    render_();
    fireEvent.click(await screen.findByTestId("when-save-setup-oversold"));
    expect(await screen.findByTestId("when-save-setup-oversold-saved")).toBeTruthy();
  });

  it("does not claim success when the save failed", async () => {
    /* A failed save that looks successful is worse than a visible failure —
       the user walks away believing a rule exists that does not. */
    createRule.mockRejectedValue(new Error("500"));
    render_();
    const btn = await screen.findByTestId("when-save-setup-oversold");
    fireEvent.click(btn);
    await waitFor(() => expect(btn.textContent).toMatch(/try again/));
    expect(screen.queryByTestId("when-save-setup-oversold-saved")).toBeNull();
  });

  it("saves the costliest habit as an exit-side rule", async () => {
    createRule.mockResolvedValue({ id: "r9" });
    render_();
    fireEvent.click(await screen.findByTestId("when-save-leak"));
    await waitFor(() => expect(createRule).toHaveBeenCalled());
    const payload = createRule.mock.calls[0][1];
    expect(payload.rule_type).toBe("exit");
    expect(payload.conditions).toEqual({ avoid_outcome: "giveback" });
    expect(payload.historical_effect).toMatch(/\$4,349/);
  });
});
