/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { Route } from "next";

import type { SignalCard as SignalCardType } from "@/lib/contracts";

import { SignalCard } from "../signal-card";
import { SignalGlanceChip } from "../signal-glance-chip";

function card(over: Partial<SignalCardType> = {}): SignalCardType {
  return {
    saved_strategy_id: "s1",
    strategy_title: "Daily MA",
    strategy_type: "moving_average_filter",
    symbol: "NVDA",
    state: "in_signal",
    display: "LONG NVDA",
    reason: "“Daily MA” is currently in signal on NVDA.",
    fired_primitives: ["rsi lt 30", "sma 200"],
    backtest_id: "bt1",
    as_of: "2026-07-28",
    ...over,
  };
}

describe("SignalGlanceChip", () => {
  it("renders a descriptive label + data-state per state", () => {
    const { rerender } = render(<SignalGlanceChip state="in_signal" />);
    expect(screen.getByTestId("signal-glance-chip").getAttribute("data-state")).toBe("in_signal");
    expect(screen.getByText("In signal")).toBeTruthy();

    rerender(<SignalGlanceChip state="flat" />);
    expect(screen.getByText("Flat")).toBeTruthy();

    rerender(<SignalGlanceChip state="pending" />);
    expect(screen.getByText("Pending")).toBeTruthy();
  });

  it("never uses prescriptive wording", () => {
    for (const s of ["in_signal", "basket", "flat", "pending"] as const) {
      const { unmount } = render(<SignalGlanceChip state={s} />);
      const txt = screen.getByTestId("signal-glance-chip").textContent?.toLowerCase() ?? "";
      expect(txt).not.toMatch(/buy|sell/);
      unmount();
    }
  });
});

describe("SignalCard", () => {
  it("renders L1 (display + reason + as-of) collapsed by default", () => {
    render(<SignalCard card={card()} />);
    expect(screen.getByTestId("signal-card").getAttribute("data-state")).toBe("in_signal");
    expect(screen.getByText("LONG NVDA")).toBeTruthy();
    expect(screen.getByText(/currently in signal on NVDA/)).toBeTruthy();
    expect(screen.getByText(/As of 2026-07-28/)).toBeTruthy();
    // L2/L3 stay hidden until the user drills in.
    expect(screen.queryByTestId("signal-card-detail")).toBeNull();
  });

  it("expands to L2 fired primitives + L3 backtest link", () => {
    render(<SignalCard card={card()} />);
    fireEvent.click(screen.getByTestId("signal-card-toggle"));
    expect(screen.getByTestId("signal-card-detail")).toBeTruthy();
    expect(screen.getByText("rsi lt 30")).toBeTruthy();
    expect(screen.getByText("sma 200")).toBeTruthy();
    expect(screen.getByTestId("signal-card-backtest").getAttribute("href")).toBe(
      "/account/strategies/s1",
    );
  });

  it("renders a pending card without inventing a signal", () => {
    render(
      <SignalCard
        card={card({
          state: "pending",
          display: "Signal pending",
          fired_primitives: [],
          backtest_id: null,
          as_of: null,
          reason: "This strategy's signal hasn't been computed yet.",
        })}
      />,
    );
    expect(screen.getByTestId("signal-card").getAttribute("data-state")).toBe("pending");
    expect(screen.getByText("Signal pending")).toBeTruthy();
  });

  it("makes the heading a navigation link when href is set", () => {
    render(<SignalCard card={card()} href={"/account/strategies/s1" as Route} />);
    expect(screen.getByTestId("signal-card-heading").getAttribute("href")).toBe(
      "/account/strategies/s1",
    );
  });
});
