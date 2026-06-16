/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import {
  UniverseSelector,
  isStandingUniverse,
} from "@/lib/flows/bricks/universe-selector";

describe("isStandingUniverse", () => {
  it("is true for sp500 and sector_*, false for client tiers", () => {
    expect(isStandingUniverse("sp500")).toBe(true);
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
});
