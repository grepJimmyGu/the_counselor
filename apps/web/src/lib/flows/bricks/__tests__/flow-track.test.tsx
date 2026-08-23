/** @vitest-environment jsdom */

/**
 * <FlowTrack> — the shared terminal step, and the save-strategy sign-off.
 *
 * The rules under test are the ones a user would be hurt by if they broke:
 * a ladder is never saved without a press that named the strategy, the tiers
 * sent are exactly the tiers shown, and the step never claims a volatility
 * scaling it could not compute.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const attachExitLadder = vi.fn(async () => ({}) as never);
const declarePosition = vi.fn(async () => ({}) as never);
const subscribeSignalAlert = vi.fn(async () => ({}) as never);
const previewSignalPrimitive = vi.fn(async () => ({
  // natr 3% → stop -6%, targets +9% / +15% (in fractions).
  series: [{ value: 3.0 }],
}) as never);

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { backendToken: "tok" },
    status: "authenticated" as const,
  }),
}));

vi.mock("@/lib/api", () => ({
  attachExitLadder: (...a: unknown[]) => attachExitLadder(...(a as [])),
  declarePosition: (...a: unknown[]) => declarePosition(...(a as [])),
  subscribeSignalAlert: (...a: unknown[]) => subscribeSignalAlert(...(a as [])),
  previewSignalPrimitive: (...a: unknown[]) => previewSignalPrimitive(...(a as [])),
  matchSignalCombosToTemplates: async () => ({ matches: [] }),
}));

vi.mock("../../runtime", () => ({
  useFlowState: () => ({ flow: { id: "one_asset_mode" } }),
}));

import { FlowTrack, describeLadder, existingLadder, ladderSymbol } from "../flow-track";
import type { FlowTrackContext } from "../flow-track";
import type { ExitTier, StrategyJson } from "@/lib/contracts";

const LADDER: ExitTier[] = [
  { trigger_pct: -0.08, action: "sell_all", label: "Stop" },
  { trigger_pct: 0.15, action: "sell_fraction", fraction: 0.5, label: "TP1" },
  { trigger_pct: 0.3, action: "sell_all", label: "TP2" },
];

function sj(extra: Partial<StrategyJson> = {}): StrategyJson {
  return {
    strategy_name: "Momentum runner",
    universe: ["NVDA"],
    ...extra,
  } as StrategyJson;
}

function mount(ctx: Partial<FlowTrackContext> = {}) {
  const advance = vi.fn();
  const utils = render(
    <FlowTrack
      context={{
        fromTrigger: "test",
        strategyJson: sj(),
        savedSlug: "momentum-runner-ab12",
        savedStrategyId: "strat_1",
        ticker: "NVDA",
        ...ctx,
      }}
      updateContext={vi.fn()}
      advance={advance}
      back={vi.fn()}
      abort={vi.fn()}
    />,
  );
  return { ...utils, advance };
}

beforeEach(() => vi.clearAllMocks());

// ── pure helpers ────────────────────────────────────────────────────────────

describe("describeLadder", () => {
  it("reads the tiers rather than restating the intent", () => {
    expect(describeLadder(LADDER)).toBe(
      "stop at -8.0%, targets at +15.0% and +30.0%",
    );
  });

  it("handles a stop-only ladder", () => {
    expect(describeLadder([LADDER[0]])).toBe("stop at -8.0%");
  });
});

describe("ladderSymbol", () => {
  it("takes whichever field the mode uses", () => {
    expect(ladderSymbol({ fromTrigger: "t", ticker: "nvda" })).toBe("NVDA");
    expect(ladderSymbol({ fromTrigger: "t", symbol: "msft" })).toBe("MSFT");
  });

  it("falls back to a single-name universe", () => {
    expect(ladderSymbol({ fromTrigger: "t", strategyJson: sj() })).toBe("NVDA");
  });

  it("refuses to pick one name out of a basket", () => {
    /* A ladder scaled to one member of a multi-name strategy would be
     * presented as "scaled to your strategy" and be nothing of the kind. */
    const multi = sj({ universe: ["NVDA", "MSFT", "AMD"] });
    expect(ladderSymbol({ fromTrigger: "t", strategyJson: multi })).toBeNull();
  });
});

describe("existingLadder", () => {
  it("treats an empty list as no ladder", () => {
    const empty = sj({ risk_management: { exit_ladder: [] } } as Partial<StrategyJson>);
    expect(existingLadder(empty)).toBeNull();
  });
});

// ── the doors ───────────────────────────────────────────────────────────────

describe("the three doors", () => {
  it("offers all three, and 'just save it' carries no penalty copy", () => {
    mount();
    expect(screen.getByTestId("track-door-watch")).toBeTruthy();
    expect(screen.getByTestId("track-door-hold")).toBeTruthy();
    const skip = screen.getByTestId("track-door-skip");
    expect(skip.textContent).toMatch(/done for now/i);
  });

  it("'just save it' finishes without touching the network", async () => {
    /* Most users stop here. A backtest is a legitimate end in itself, and
     * this door must not quietly subscribe them or price an exit rule they
     * never asked about. */
    mount();
    fireEvent.click(screen.getByTestId("track-door-skip"));
    await waitFor(() => expect(screen.getByTestId("flow-track-done")).toBeTruthy());
    expect(attachExitLadder).not.toHaveBeenCalled();
    expect(subscribeSignalAlert).not.toHaveBeenCalled();
    expect(previewSignalPrimitive).not.toHaveBeenCalled();
  });

  it("'watch it' subscribes, then asks about exits", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    await waitFor(() => expect(subscribeSignalAlert).toHaveBeenCalledWith("strat_1", "tok"));
    await waitFor(() => expect(screen.getByTestId("flow-track-ladder")).toBeTruthy());
  });
});

// ── the sign-off ────────────────────────────────────────────────────────────

describe("the exit-ladder sign-off", () => {
  it("names the strategy being changed", async () => {
    /* PRD-28 §2.2 — this MUTATES a strategy the user already saved. It must
     * never read as a side effect of having clicked "Watch it". */
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    const signoff = await screen.findByTestId("track-ladder-signoff");
    expect(signoff.textContent).toMatch(/Momentum runner/);
    expect(signoff.textContent).toMatch(/updates/i);
  });

  it("saves nothing until the confirm is pressed", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    await screen.findByTestId("track-ladder-confirm");
    // Seeded and rendered — but not saved.
    expect(attachExitLadder).not.toHaveBeenCalled();
  });

  it("sends exactly the tiers it displayed, in fractions", async () => {
    /* The server has no default-applier, so what lands on the strategy is
     * whatever this component sends. natr 3% → -6% stop, +9% / +15%. */
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    const confirm = await screen.findByTestId("track-ladder-confirm");
    fireEvent.click(confirm);

    await waitFor(() => expect(attachExitLadder).toHaveBeenCalledOnce());
    const [id, tiers, token] = attachExitLadder.mock.calls[0] as unknown as [
      string, ExitTier[], string,
    ];
    expect(id).toBe("strat_1");
    expect(token).toBe("tok");
    expect(tiers.map((t) => t.trigger_pct)).toEqual([-0.06, 0.09, 0.15]);
    // The unit that made every promoted ladder inert.
    for (const t of tiers) expect(Math.abs(t.trigger_pct)).toBeLessThan(1);
  });

  it("lets the user decline without saving anything", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    const decline = await screen.findByTestId("track-ladder-decline");
    fireEvent.click(decline);
    await waitFor(() => expect(screen.getByTestId("flow-track-done")).toBeTruthy());
    expect(attachExitLadder).not.toHaveBeenCalled();
  });

  it("skips the ladder step entirely when the strategy already has one", async () => {
    /* A user who built exits in the composer has already made this decision.
     * Asking again would be re-confirming something they signed off on one
     * step ago. */
    mount({ strategyJson: sj({ risk_management: { exit_ladder: LADDER } } as Partial<StrategyJson>) });
    fireEvent.click(screen.getByTestId("track-door-watch"));
    await waitFor(() => expect(screen.getByTestId("flow-track-done")).toBeTruthy());
    expect(screen.queryByTestId("flow-track-ladder")).toBeNull();
  });
});

// ── honesty about where the numbers came from ───────────────────────────────

describe("what it claims about the seeded numbers", () => {
  it("says 'scaled to' only when it actually read the volatility", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    const panel = await screen.findByTestId("flow-track-ladder");
    expect(panel.textContent).toMatch(/scaled to NVDA/i);
    expect(panel.textContent).toMatch(/not optimised/i);
  });

  it("admits it when the volatility read failed", async () => {
    /* `promote-to-strategy` returns null rather than guessing, and this step
     * must not paper over that with a confident sentence. Generic tiers are
     * fine — describing them as volatility-scaled is not. */
    previewSignalPrimitive.mockRejectedValueOnce(new Error("no data"));
    mount();
    fireEvent.click(screen.getByTestId("track-door-watch"));
    const panel = await screen.findByTestId("flow-track-ladder");
    expect(panel.textContent).toMatch(/starting points/i);
    expect(panel.textContent).not.toMatch(/scaled to/i);
  });
});

// ── declaring a real position ───────────────────────────────────────────────

describe("'I already hold this'", () => {
  it("takes the ladder first, because tracking is impossible without one", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-hold"));
    const panel = await screen.findByTestId("flow-track-ladder");
    // The reason is stated, not just enforced.
    expect(panel.textContent).toMatch(/nothing to monitor it against/i);

    fireEvent.click(screen.getByTestId("track-ladder-confirm"));
    await waitFor(() => expect(screen.getByTestId("flow-track-declare")).toBeTruthy());
  });

  it("sends the user's real numbers", async () => {
    mount({ strategyJson: sj({ risk_management: { exit_ladder: LADDER } } as Partial<StrategyJson>) });
    fireEvent.click(screen.getByTestId("track-door-hold"));
    await screen.findByTestId("flow-track-declare");

    fireEvent.change(screen.getByTestId("track-shares"), { target: { value: "120" } });
    fireEvent.change(screen.getByTestId("track-cost"), { target: { value: "118.40" } });
    fireEvent.click(screen.getByTestId("track-declare-submit"));

    await waitFor(() => expect(declarePosition).toHaveBeenCalledOnce());
    const [id, payload] = declarePosition.mock.calls[0] as unknown as [
      string, { symbol: string; shares: number; entry_price: number },
    ];
    expect(id).toBe("strat_1");
    expect(payload).toEqual({ symbol: "NVDA", shares: 120, entry_price: 118.4 });
  });

  it("refuses a position with no entry price, and says why it matters", async () => {
    /* Every tier is measured from the entry price, so a missing or wrong one
     * moves every stop and target on the position. */
    mount({ strategyJson: sj({ risk_management: { exit_ladder: LADDER } } as Partial<StrategyJson>) });
    fireEvent.click(screen.getByTestId("track-door-hold"));
    await screen.findByTestId("flow-track-declare");

    fireEvent.change(screen.getByTestId("track-shares"), { target: { value: "120" } });
    fireEvent.click(screen.getByTestId("track-declare-submit"));

    const err = await screen.findByTestId("track-error");
    expect(err.textContent).toMatch(/price/i);
    expect(declarePosition).not.toHaveBeenCalled();
  });
});

// ── the strategy that never got a row ───────────────────────────────────────

describe("when the save produced no strategy id", () => {
  it("offers an honest confirmation instead of doors that would 404", () => {
    /* `saved_strategy_id` is null when the backend's best-effort link failed.
     * Every door needs that id, so showing three of them would give the user
     * three ways to hit an error. */
    mount({ savedStrategyId: null });
    expect(screen.getByTestId("flow-track-unlinked")).toBeTruthy();
    expect(screen.queryByTestId("track-door-watch")).toBeNull();
    expect(screen.getByTestId("track-finish")).toBeTruthy();
  });
});

// ── finishing ───────────────────────────────────────────────────────────────

describe("the confirmation", () => {
  it("reports what is actually on, and nothing that isn't", async () => {
    mount();
    fireEvent.click(screen.getByTestId("track-door-skip"));
    const done = await screen.findByTestId("flow-track-done");
    expect(done.textContent).toMatch(/My strategies/);
    // Nothing was switched on, so nothing is claimed.
    expect(screen.queryByTestId("track-watching")).toBeNull();
    expect(screen.queryByTestId("track-ladder-on")).toBeNull();
    expect(screen.queryByTestId("track-position-on")).toBeNull();
  });

  it("never implies Livermore will do the selling", async () => {
    mount({ strategyJson: sj({ risk_management: { exit_ladder: LADDER } } as Partial<StrategyJson>) });
    fireEvent.click(screen.getByTestId("track-door-hold"));
    await screen.findByTestId("flow-track-declare");
    fireEvent.change(screen.getByTestId("track-shares"), { target: { value: "10" } });
    fireEvent.change(screen.getByTestId("track-cost"), { target: { value: "100" } });
    fireEvent.click(screen.getByTestId("track-declare-submit"));

    const on = await screen.findByTestId("track-position-on");
    expect(on.textContent).toMatch(/never sells/i);
  });

  it("fires the flow's onComplete only from the finish button", async () => {
    const { advance } = mount();
    fireEvent.click(screen.getByTestId("track-door-skip"));
    await screen.findByTestId("flow-track-done");
    expect(advance).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("track-finish"));
    expect(advance).toHaveBeenCalledOnce();
  });
});
