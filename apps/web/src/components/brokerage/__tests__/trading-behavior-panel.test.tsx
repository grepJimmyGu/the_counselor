/** @vitest-environment jsdom */

/**
 * "How you trade" — the record read back to the person who made it.
 *
 * The claims under test are all about what the panel REFUSES to say: no win
 * rate without the ratio beside it, no behavioural pattern from a one-sided
 * history, and no realised P/L that quietly omits the sales it couldn't
 * price.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const getTradingBehavior = vi.fn();

vi.mock("@/lib/api", () => ({
  getTradingBehavior: (...a: unknown[]) => getTradingBehavior(...(a as [])),
}));

import { TradingBehaviorPanel } from "../trading-behavior-panel";
import type { TradingBehavior } from "@/lib/contracts";

const BASE: TradingBehavior = {
  window_start: "2025-08-26", window_end: "2026-08-26",
  total_buys: 8, total_sells: 6, symbols_traded: 4,
  round_trips: 6, realised_pnl: 1240.5, fees_paid: 18,
  wins: 4, losses: 2, win_rate: 4 / 6,
  avg_win: 500, avg_loss: 250, win_loss_ratio: 2,
  largest_win: 900, largest_loss: 300,
  avg_holding_days: 40, median_holding_days: 31,
  avg_holding_days_winners: 20, avg_holding_days_losers: 80,
  holds_losers_longer: true,
  top_symbols_by_trades: [
    { symbol: "NVDA", trades: 6, buys: 3, sells: 3, realised_pnl: 1400,
      win_rate: 1, avg_holding_days: 25, gross_bought: 30000 },
  ],
  top_symbols_by_pnl: [
    { symbol: "NVDA", trades: 6, buys: 3, sells: 3, realised_pnl: 1400,
      win_rate: 1, avg_holding_days: 25, gross_bought: 30000 },
  ],
  worst_symbols_by_pnl: [
    { symbol: "KO", trades: 2, buys: 1, sells: 1, realised_pnl: -160,
      win_rate: 0, avg_holding_days: 90, gross_bought: 5000 },
  ],
  unmatched_sells: 0, unmatched_sell_symbols: [], open_lots: 2,
  symbols_total: 4, symbols_included: 4, excluded: [],
  splits_seen: 0, splits_adjusted: 0,
};

const render_ = (over: Partial<TradingBehavior> = {}) => {
  getTradingBehavior.mockResolvedValue({ ...BASE, ...over });
  return render(<TradingBehaviorPanel backendToken="tok" startDate="2025-08-26" />);
};

beforeEach(() => vi.clearAllMocks());

describe("the headline numbers", () => {
  it("reports realised P/L, closed trades and the win-loss record", async () => {
    render_();
    expect((await screen.findByTestId("behavior-realised")).textContent).toBe("$1,240.50");
    expect(screen.getByTestId("behavior-round-trips").textContent).toBe("6");
    expect(screen.getByTestId("behavior-win-rate").textContent).toBe("67% (4W/2L)");
  });

  it("asks for the same window the trade list is showing", async () => {
    render_();
    await screen.findByTestId("behavior-panel");
    expect(getTradingBehavior).toHaveBeenCalledWith("tok", { startDate: "2025-08-26" });
  });
});

describe("the win rate never stands alone", () => {
  it("puts the win/loss ratio next to it", async () => {
    /* A win rate on its own reads as praise. What you make when right over
     * what you lose when wrong is the number that decides the outcome. */
    render_();
    const line = await screen.findByTestId("behavior-ratio");
    expect(line.textContent).toMatch(/average win.*2\.0×.*average loss/);
  });

  it("names the contradiction when a winning record still lost money", async () => {
    render_({
      realised_pnl: -2000, wins: 7, losses: 3, win_rate: 0.7,
      avg_win: 100, avg_loss: 900, win_loss_ratio: 100 / 900,
    });
    const line = await screen.findByTestId("behavior-ratio");
    expect(line.textContent).toMatch(/average loss.*9\.0×.*average win/);
    expect(line.textContent).toMatch(/right more often than not and still lost money/);
  });
});

describe("the disposition effect", () => {
  it("shows both holding periods and says what the gap means", async () => {
    render_();
    const box = await screen.findByTestId("behavior-holding");
    expect(box.textContent).toMatch(/Winners held\s*20 days/);
    expect(box.textContent).toMatch(/Losers held\s*80 days/);
    expect(box.textContent).toMatch(/sell winners sooner than losers/i);
  });

  it("credits the opposite pattern rather than assuming the common one", async () => {
    render_({
      avg_holding_days_winners: 120, avg_holding_days_losers: 15,
      holds_losers_longer: false,
    });
    const box = await screen.findByTestId("behavior-holding");
    expect(box.textContent).toMatch(/sit with winners longer/i);
  });

  it("says nothing at all when the history has only one side", async () => {
    /* THE HONESTY TEST. With no losses there is no comparison to make, and
     * "you hold your losers longer" from a two-trade record is a fabrication
     * dressed as an insight. */
    render_({
      losses: 0, wins: 6, win_rate: 1, avg_loss: null, win_loss_ratio: null,
      avg_holding_days_losers: null, holds_losers_longer: null,
    });
    await screen.findByTestId("behavior-panel");
    expect(screen.queryByTestId("behavior-holding")).toBeNull();
    expect(screen.queryByTestId("behavior-ratio")).toBeNull();
  });
});

describe("what the numbers leave out", () => {
  it("names the sales it could not price", async () => {
    /* Pull a year of history and you will see sells of positions opened
     * before it. A realised P/L that silently omits your biggest sale is
     * worse than no number — so it is stated, with the tickers. */
    render_({ unmatched_sells: 2, unmatched_sell_symbols: ["AAPL", "TSLA"] });
    const note = await screen.findByTestId("behavior-unmatched");
    expect(note.textContent).toMatch(/2 sales/);
    expect(note.textContent).toMatch(/AAPL, TSLA/);
    expect(note.textContent).toMatch(/left out of the P\/L rather than guessed/i);
  });

  it("says fees are already deducted", async () => {
    render_();
    const panel = await screen.findByTestId("behavior-panel");
    expect(panel.textContent).toMatch(/Fees are deducted: \$18\.00/);
  });
});

describe("coverage", () => {
  it("names a symbol it dropped, and says why, before any other footnote", async () => {
    /* THE HONESTY TEST for this slice. A position held through a 10:1 split
     * matched on raw units reports a ~90% loss that never happened — and a
     * fabricated loss reads exactly like a real finding. Dropping the symbol
     * is only defensible if the user is told which one and why. */
    render_({
      symbols_total: 4, symbols_included: 3,
      excluded: [["NVDA", "split_unreconciled"]],
      splits_seen: 1, splits_adjusted: 0,
    });
    const note = await screen.findByTestId("behavior-excluded");
    expect(note.textContent).toMatch(/NVDA is left out/);
    expect(note.textContent).toMatch(/split during this window/);
    expect(note.textContent).toMatch(/invented rather than measured/);
  });

  it("says what fraction of your symbols the numbers cover", async () => {
    render_({ symbols_total: 4, symbols_included: 3,
              excluded: [["NVDA", "split_unreconciled"]] });
    expect((await screen.findByTestId("behavior-coverage")).textContent)
      .toMatch(/3 of 4 symbols/);
  });

  it("stays quiet about coverage when nothing was left out", async () => {
    /* "4 of 4 symbols" is noise. The absence of an exclusion is not news. */
    render_();
    await screen.findByTestId("behavior-panel");
    expect(screen.queryByTestId("behavior-coverage")).toBeNull();
    expect(screen.queryByTestId("behavior-excluded")).toBeNull();
  });

  it("mentions an adjusted split and says it moved no dollars", async () => {
    /* A user comparing this to their broker's own P/L deserves to know why
     * the share counts differ — and to know the money didn't change. */
    render_({ splits_seen: 1, splits_adjusted: 1 });
    const note = await screen.findByTestId("behavior-splits");
    expect(note.textContent).toMatch(/One stock split was accounted for/);
    expect(note.textContent).toMatch(/changes no dollars/);
  });

  it("says nothing about splits when there were none", async () => {
    render_();
    await screen.findByTestId("behavior-panel");
    expect(screen.queryByTestId("behavior-splits")).toBeNull();
  });

  it("ignores an exclusion reason it doesn't have copy for", async () => {
    /* Only `split_unreconciled` exists today. A future reason rendered with
     * the split sentence would be a confident lie about a different problem. */
    render_({ symbols_total: 4, symbols_included: 3,
              excluded: [["KO", "some_future_reason"]] });
    await screen.findByTestId("behavior-panel");
    expect(screen.queryByTestId("behavior-excluded")).toBeNull();
  });
});

describe("symbols", () => {
  it("lists what was traded most and what made or lost the most", async () => {
    render_();
    expect((await screen.findByTestId("behavior-most-traded")).textContent).toMatch(/NVDA/);
    const pnl = screen.getByTestId("behavior-by-pnl");
    expect(pnl.textContent).toMatch(/NVDA/);
    expect(pnl.textContent).toMatch(/KO/);
  });

  it("shows a symbol once when it is both the best and the most traded", async () => {
    render_();
    await screen.findByTestId("behavior-by-pnl");
    expect(screen.getAllByTestId("behavior-symbol-NVDA")).toHaveLength(2); // one per table
  });
});

describe("nothing to say", () => {
  it("distinguishes 'no trades' from 'nothing closed yet'", async () => {
    /* A user who has bought and not sold has no measurable behaviour, and
     * telling them "no trades" would be false. */
    render_({ round_trips: 0, total_buys: 3, total_sells: 0 });
    expect((await screen.findByTestId("behavior-empty")).textContent).toMatch(
      /haven.t closed a position/i,
    );
  });

  it("costs its own section when the read fails, not the page", async () => {
    getTradingBehavior.mockRejectedValue(new Error("upstream 502"));
    const { container } = render(
      <TradingBehaviorPanel backendToken="tok" startDate="2025-08-26" />,
    );
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
