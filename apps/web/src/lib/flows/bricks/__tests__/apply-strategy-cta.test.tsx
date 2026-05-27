/** @vitest-environment jsdom */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ApplyStrategyCTA } from "../apply-strategy-cta";

describe("ApplyStrategyCTA", () => {
  it("renders the default label when compact is omitted", () => {
    render(
      <ApplyStrategyCTA ticker="AAPL" from="stock_page" onClick={() => {}} />
    );
    expect(screen.getByTestId("apply-strategy-cta").textContent).toBe(
      "⚡ Apply a strategy"
    );
  });

  it("renders the compact label and small size when compact is true", () => {
    render(
      <ApplyStrategyCTA
        ticker="AAPL"
        from="stock_page"
        compact
        onClick={() => {}}
      />
    );
    const button = screen.getByTestId("apply-strategy-cta");
    expect(button.textContent).toBe("Apply strategy");
    expect(button.getAttribute("data-size")).toBe("sm");
  });

  it("calls onClick exactly once when clicked", () => {
    const onClick = vi.fn();
    render(
      <ApplyStrategyCTA ticker="AAPL" from="stock_page" onClick={onClick} />
    );
    fireEvent.click(screen.getByTestId("apply-strategy-cta"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("forwards ticker and from props as data attributes", () => {
    render(
      <ApplyStrategyCTA
        ticker="NVDA"
        from="commodity_page"
        onClick={() => {}}
      />
    );
    const button = screen.getByTestId("apply-strategy-cta");
    expect(button.getAttribute("data-ticker")).toBe("NVDA");
    expect(button.getAttribute("data-from")).toBe("commodity_page");
  });

  it("uses the outline button variant when variant is secondary", () => {
    render(
      <ApplyStrategyCTA
        ticker="AAPL"
        from="stock_page"
        variant="secondary"
        onClick={() => {}}
      />
    );
    expect(
      screen.getByTestId("apply-strategy-cta").getAttribute("data-variant")
    ).toBe("outline");
  });

  it("derives a default aria-label from the ticker and label when ariaLabel is omitted", () => {
    render(
      <ApplyStrategyCTA ticker="AAPL" from="stock_page" onClick={() => {}} />
    );
    expect(
      screen.getByTestId("apply-strategy-cta").getAttribute("aria-label")
    ).toBe("⚡ Apply a strategy on AAPL (from stock_page)");
  });
});
