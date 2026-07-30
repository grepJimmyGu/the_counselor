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
    expect(tiers.map((t) => t.trigger_pct)).toEqual([-6, 9, 15]);
    expect(tiers[0].action).toBe("sell_all");
    expect(tiers[1]).toMatchObject({ action: "sell_fraction", fraction: 0.5 });
    expect(tiers[2].action).toBe("sell_all"); // final tier closes the position
  });

  it("clamps a quiet name up to the minimum stop", () => {
    // natr 0.5% → raw stop -1%, below the -4% floor.
    const tiers = ladderFromNatr(0.5)!;
    expect(tiers[0].trigger_pct).toBe(-4);
    expect(tiers[1].trigger_pct).toBe(6); // target floor
  });

  it("clamps a volatile name down to the maximum stop", () => {
    // natr 12% → raw stop -24%, beyond the -15% cap.
    const tiers = ladderFromNatr(12.0)!;
    expect(tiers[0].trigger_pct).toBe(-15);
    expect(tiers[2].trigger_pct).toBe(60); // target cap
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
    expect(tiers[0].trigger_pct).toBe(-5);
    expect(tiers[1].trigger_pct).toBe(10);
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
