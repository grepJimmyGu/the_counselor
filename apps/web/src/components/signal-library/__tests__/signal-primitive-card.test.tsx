/** @vitest-environment jsdom */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { SignalPrimitive } from "@/lib/contracts";
import { SignalPrimitiveCard } from "../signal-primitive-card";

function _primitive(overrides: Partial<SignalPrimitive> = {}): SignalPrimitive {
  return {
    id: "rsi",
    category: "mean_reversion",
    family: "RSI",
    name: "RSI (Relative Strength Index)",
    description:
      "Measures overbought (>70) and oversold (<30) extremes from recent gains vs losses.",
    long_description: null,
    parameters: [
      {
        name: "period",
        default: 14,
        min_value: 2,
        max_value: 100,
        description: "Look-back window in days",
      },
    ],
    default_thresholds: { upper: 70, lower: 30 },
    asset_compat: ["equity", "etf"],
    evidence_tier: "A",
    provider_impl: "rsi",
    data_source: "price",
    resolution: ["daily"],
    is_ranking: false,
    compute_strategy: "local",
    ...overrides,
  };
}

describe("SignalPrimitiveCard", () => {
  it("renders the primitive's name, family, description, category, and tier", () => {
    render(<SignalPrimitiveCard primitive={_primitive()} onClick={() => {}} />);
    expect(screen.getByText(/RSI \(Relative Strength Index\)/)).toBeTruthy();
    expect(screen.getByText("RSI")).toBeTruthy();
    expect(screen.getByText(/overbought/i)).toBeTruthy();
    expect(screen.getByText("Mean Reversion")).toBeTruthy();
    expect(screen.getByText(/Tier A/)).toBeTruthy();
  });

  it("fires onClick with the full primitive on click", () => {
    const onClick = vi.fn();
    render(<SignalPrimitiveCard primitive={_primitive()} onClick={onClick} />);
    fireEvent.click(screen.getByTestId("primitive-card-rsi"));
    expect(onClick).toHaveBeenCalledWith(_primitive());
  });

  it("renders the 'Selected' state when selected=true", () => {
    render(
      <SignalPrimitiveCard primitive={_primitive()} onClick={() => {}} selected />,
    );
    expect(screen.getByText(/Selected/)).toBeTruthy();
  });

  it("renders a 'Ranking' chip for cross-sectional ranking primitives", () => {
    render(
      <SignalPrimitiveCard
        primitive={_primitive({
          id: "rank_return_6m",
          name: "Rank by Trailing 6-Month Return",
          category: "cross_sectional",
          is_ranking: true,
        })}
        onClick={() => {}}
      />,
    );
    expect(screen.getByText(/Ranking/)).toBeTruthy();
  });

  it("disables the button when no onClick is provided", () => {
    render(<SignalPrimitiveCard primitive={_primitive()} />);
    const btn = screen.getByTestId("primitive-card-rsi") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
