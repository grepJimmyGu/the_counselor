/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { ExitLadderDefaults } from "@/lib/contracts";
import {
  FALLBACK_LADDER_DEFAULTS,
  ladderFromNatr,
  type PromoteDraft,
} from "@/lib/flows/promote-to-strategy";
import { StrategyDraftSheet } from "../strategy-draft-sheet";

// ── ladder arithmetic (pure) ──────────────────────────────────────────────

describe("ladderFromNatr", () => {
  it("scales the ladder to volatility", () => {
    // natr 3% → stop -2x = -6%, targets 3x/5x = +9% / +15%.
    const tiers = ladderFromNatr(3.0)!;
    expect(tiers.map((t) => t.trigger_pct)).toEqual([-0.06, 0.09, 0.15]);
    expect(tiers[0].action).toBe("sell_all");
    expect(tiers[1]).toMatchObject({ action: "sell_fraction", fraction: 0.5 });
    expect(tiers[2].action).toBe("sell_all"); // final tier closes the position
  });

  it("REGRESSION: emits fractions, because that is what fires the tier", () => {
    /* Shipped inverted. This function returned the percent number
     * unconverted, so a 3%-ATR name got a stop at `-6.0` — and
     * `exit_ladder.py` compares `trigger_pct` against
     * `(close - entry) / entry`, a fraction. -6.0 means -600%.
     *
     * From a $100 entry that stop needed the stock at -$500. Every tier of
     * every promoted screen was unreachable: no stop, no target, and a
     * backtest that quietly ran with no exits at all. Nothing errored.
     *
     * The magnitude assertion is the point — a ladder whose |trigger| is
     * over 1.0 is not a slightly-wrong ladder, it is an inert one. */
    for (const natr of [0.5, 3.0, 7.5, 12.0]) {
      for (const tier of ladderFromNatr(natr)!) {
        expect(Math.abs(tier.trigger_pct)).toBeLessThan(1);
      }
    }

    // Spelled out once, in the evaluator's own arithmetic.
    const stop = ladderFromNatr(3.0)![0].trigger_pct;
    const entry = 100;
    expect((94 - entry) / entry).toBeLessThanOrEqual(stop); // -6% closes it
    expect((95 - entry) / entry).toBeGreaterThan(stop); //     -5% does not
  });

  it("clamps a quiet name up to the minimum stop", () => {
    // natr 0.5% → raw stop -1%, below the -4% floor.
    const tiers = ladderFromNatr(0.5)!;
    expect(tiers[0].trigger_pct).toBe(-0.04);
    expect(tiers[1].trigger_pct).toBe(0.06); // target floor
  });

  it("clamps a volatile name down to the maximum stop", () => {
    // natr 12% → raw stop -24%, beyond the -15% cap.
    const tiers = ladderFromNatr(12.0)!;
    expect(tiers[0].trigger_pct).toBe(-0.15);
    expect(tiers[2].trigger_pct).toBe(0.6); // target cap
  });

  it("refuses to invent a ladder from a non-positive or bad reading", () => {
    expect(ladderFromNatr(0)).toBeNull();
    expect(ladderFromNatr(-1)).toBeNull();
    expect(ladderFromNatr(Number.NaN)).toBeNull();
  });

  it("honours backend-supplied defaults over the local fallback", () => {
    const custom: ExitLadderDefaults = {
      ...FALLBACK_LADDER_DEFAULTS,
      stop_atr_multiple: 1.0,
      target_atr_multiples: [2.0],
      target_fractions: [1.0],
    };
    const tiers = ladderFromNatr(5.0, custom)!;
    expect(tiers).toHaveLength(2);
    expect(tiers[0].trigger_pct).toBe(-0.05);
    expect(tiers[1].trigger_pct).toBe(0.1);
  });

  it("satisfies the backend's own ladder validator", () => {
    /* `RiskManagement.validate_exit_ladder` requires tiers ascending by
     * trigger_pct and at least one negative `sell_all` stop. A ladder that
     * fails it is rejected at save — so pin the shape here rather than
     * discovering it on a user's save. */
    const tiers = ladderFromNatr(3.0)!;
    const triggers = tiers.map((t) => t.trigger_pct);
    expect(triggers).toEqual([...triggers].sort((a, b) => a - b));
    expect(
      tiers.some((t) => t.trigger_pct < 0 && t.action === "sell_all"),
    ).toBe(true);
    // sell_all tiers must not carry a fraction; sell_fraction must.
    for (const t of tiers) {
      if (t.action === "sell_all") expect(t.fraction).toBeUndefined();
      else expect(t.fraction).toBeGreaterThan(0);
    }
  });
});

// ── the sheet's honesty guarantees ────────────────────────────────────────

function draft(over: Partial<PromoteDraft> = {}): PromoteDraft {
  return {
    symbol: "AVGO",
    strategyJson: { strategy_name: "x" } as PromoteDraft["strategyJson"],
    rules: [],
    seededFromTemplate: "bollinger-mean-reversion",
    similarity: 0.5,
    seededThresholds: { rsi: { enter_lt: 30, exit_gte: 55 } },
    entryOnlyPrimitives: [],
    exitLadder: ladderFromNatr(3.0),
    natrPct: 3.0,
    ...over,
  };
}

describe("StrategyDraftSheet", () => {
  const noop = () => {};

  it("shows the seeding provenance and the calculated ladder", () => {
    render(
      <StrategyDraftSheet
        draft={draft()}
        candidates={["AVGO", "ANET"]}
        onSymbolChange={noop}
        onRunBacktest={noop}
        onClose={noop}
      />,
    );
    expect(screen.getByText("bollinger-mean-reversion")).toBeTruthy();
    expect(screen.getByText(/50% category match/)).toBeTruthy();
    expect(screen.getByTestId("draft-exit-ladder")).toBeTruthy();
    // The reading behind the numbers is disclosed, and framed as derived.
    expect(screen.getByText(/ATR 3.00% of price/)).toBeTruthy();
    expect(screen.getByText(/derived, not optimised/)).toBeTruthy();
  });

  it("says there is NO calculated exit instead of showing a fabricated one", () => {
    render(
      <StrategyDraftSheet
        draft={draft({ exitLadder: null, natrPct: null })}
        candidates={["AVGO"]}
        onSymbolChange={noop}
        onRunBacktest={noop}
        onClose={noop}
      />,
    );
    expect(screen.queryByTestId("draft-exit-ladder")).toBeNull();
    const notice = screen.getByTestId("draft-no-exit");
    expect(notice.textContent).toMatch(/No calculated exit/);
    expect(notice.textContent).toMatch(/set an exit yourself/);
  });

  it("names the primitives that have no exit at all", () => {
    render(
      <StrategyDraftSheet
        draft={draft({ entryOnlyPrimitives: ["rvol"] })}
        candidates={["AVGO"]}
        onSymbolChange={noop}
        onRunBacktest={noop}
        onClose={noop}
      />,
    );
    const note = screen.getByTestId("draft-entry-only");
    expect(note.textContent).toMatch(/rvol/);
    expect(note.textContent).toMatch(/entry condition only/);
  });

  it("is explicit when no template matched (never implies a seed)", () => {
    render(
      <StrategyDraftSheet
        draft={draft({
          seededFromTemplate: null,
          similarity: null,
          seededThresholds: {},
        })}
        candidates={["AVGO"]}
        onSymbolChange={noop}
        onRunBacktest={noop}
        onClose={noop}
      />,
    );
    expect(screen.getByTestId("draft-no-template").textContent).toMatch(
      /No template matched/,
    );
    expect(screen.queryByTestId("draft-seeded-thresholds")).toBeNull();
  });

  it("re-derives when the user picks a different name", () => {
    const onSymbolChange = vi.fn();
    render(
      <StrategyDraftSheet
        draft={draft()}
        candidates={["AVGO", "ANET"]}
        onSymbolChange={onSymbolChange}
        onRunBacktest={noop}
        onClose={noop}
      />,
    );
    fireEvent.change(screen.getByTestId("draft-symbol-select"), {
      target: { value: "ANET" },
    });
    expect(onSymbolChange).toHaveBeenCalledWith("ANET");
  });

  it("hands the draft on when the user runs the backtest", () => {
    const onRunBacktest = vi.fn();
    render(
      <StrategyDraftSheet
        draft={draft()}
        candidates={["AVGO"]}
        onSymbolChange={noop}
        onRunBacktest={onRunBacktest}
        onClose={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("draft-run-backtest"));
    expect(onRunBacktest).toHaveBeenCalledTimes(1);
  });
});
