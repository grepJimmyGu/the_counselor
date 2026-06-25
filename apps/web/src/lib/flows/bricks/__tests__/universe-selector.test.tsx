/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import {
  UniverseSelector,
  isStandingUniverse,
} from "@/lib/flows/bricks/universe-selector";

describe("isStandingUniverse", () => {
  it("is true for sp500 / russell3000 / sector_*, false for client tiers", () => {
    expect(isStandingUniverse("sp500")).toBe(true);
    expect(isStandingUniverse("russell3000")).toBe(true);
    expect(isStandingUniverse("sector_Technology")).toBe(true);
    expect(isStandingUniverse("symbols")).toBe(false);
    expect(isStandingUniverse("watchlist")).toBe(false);
    expect(isStandingUniverse("portfolio")).toBe(false);
  });
});

function setup(over: Partial<React.ComponentProps<typeof UniverseSelector>> = {}) {
  const onChange = vi.fn();
  render(
    <UniverseSelector
      universeId={over.universeId ?? "symbols"}
      enteredSymbols={over.enteredSymbols ?? []}
      onChange={over.onChange ?? onChange}
      {...over}
    />,
  );
  return { onChange: over.onChange ?? onChange };
}

describe("UniverseSelector", () => {
  it("defaults to the entered-symbols tier with a symbol input", () => {
    setup({ universeId: "symbols" });
    expect(screen.getByTestId("universe-tier-symbols").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("universe-entry")).toBeTruthy();
  });

  it("selecting S&P 500 emits the standing universe with no symbols", () => {
    const { onChange } = setup({ universeId: "symbols", enteredSymbols: ["AAPL"] });
    fireEvent.click(screen.getByTestId("universe-tier-sp500"));
    expect(onChange).toHaveBeenCalledWith({ universe_id: "sp500", entered_symbols: [] });
  });

  it("selecting Russell 3000 emits its own standing universe id", () => {
    const { onChange } = setup({ universeId: "symbols", enteredSymbols: ["AAPL"] });
    fireEvent.click(screen.getByTestId("universe-tier-russell3000"));
    expect(onChange).toHaveBeenCalledWith({ universe_id: "russell3000", entered_symbols: [] });
  });

  it("sector tier emits sector_<label> and the sub-picker switches it", () => {
    const { onChange } = setup({ universeId: "symbols" });
    fireEvent.click(screen.getByTestId("universe-tier-sector"));
    expect(onChange).toHaveBeenCalledWith({
      universe_id: "sector_Technology",
      entered_symbols: [],
    });
  });

  it("renders the sector sub-picker when a sector universe is active", () => {
    setup({ universeId: "sector_Energy" });
    const select = screen.getByTestId("universe-sector-select") as HTMLSelectElement;
    expect(select.value).toBe("Energy");
  });

  it("a locked tier fires onLockedSelect instead of switching", () => {
    const onChange = vi.fn();
    const onLockedSelect = vi.fn();
    render(
      <UniverseSelector
        universeId="symbols"
        enteredSymbols={[]}
        onChange={onChange}
        lockedTiers={["portfolio"]}
        onLockedSelect={onLockedSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("universe-tier-portfolio"));
    expect(onLockedSelect).toHaveBeenCalledWith("portfolio");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("watchlist + portfolio are coming-soon (locked) by default", () => {
    const onChange = vi.fn();
    render(
      <UniverseSelector universeId="symbols" enteredSymbols={[]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId("universe-tier-watchlist"));
    fireEvent.click(screen.getByTestId("universe-tier-portfolio"));
    // Locked tiers don't switch the universe.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("the entered tier takes a SINGLE symbol (no silent multi-symbol truncation)", () => {
    const { onChange } = setup({ universeId: "symbols", enteredSymbols: [] });
    fireEvent.change(screen.getByTestId("universe-symbol-input"), {
      target: { value: "nvda" },
    });
    expect(onChange).toHaveBeenCalledWith({
      universe_id: "symbols",
      entered_symbols: ["NVDA"],
    });
    // The old multi-symbol comma input is gone.
    expect(screen.queryByPlaceholderText(/AAPL, MSFT/)).toBeNull();
  });

  it("does not crash when universe_id is undefined (resumed pre-PRD-23b context)", () => {
    const onChange = vi.fn();
    render(
      <UniverseSelector
        universeId={undefined as unknown as string}
        enteredSymbols={[]}
        onChange={onChange}
      />,
    );
    // Falls back to the entered-symbols tier instead of throwing.
    expect(screen.getByTestId("universe-selector")).toBeTruthy();
    expect(screen.getByTestId("universe-tier-symbols").getAttribute("aria-pressed")).toBe("true");
  });
});
