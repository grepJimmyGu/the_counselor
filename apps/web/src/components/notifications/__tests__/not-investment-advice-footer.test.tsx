/** @vitest-environment jsdom */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { NotInvestmentAdviceFooter } from "../not-investment-advice-footer";

describe("NotInvestmentAdviceFooter", () => {
  it("renders the full compliance text by default", () => {
    render(<NotInvestmentAdviceFooter />);
    const node = screen.getByTestId("not-investment-advice-footer");
    expect(node.textContent).toMatch(/Not investment advice/);
    expect(node.textContent).toMatch(/Past performance/);
    expect(node.textContent).toMatch(/does not place trades on your behalf/);
  });

  it("renders a shortened version when compact=true", () => {
    render(<NotInvestmentAdviceFooter compact />);
    const node = screen.getByTestId("not-investment-advice-footer");
    expect(node.textContent).toMatch(/Not investment advice/);
    // Compact omits the "Past performance" sentence to stay 2-line.
    expect(node.textContent).not.toMatch(/Past performance/);
  });

  it("accepts a custom className without losing the disclaimer text", () => {
    render(<NotInvestmentAdviceFooter className="custom-class" />);
    const node = screen.getByTestId("not-investment-advice-footer");
    expect(node.className).toContain("custom-class");
    // The wording is INTENTIONALLY identical across surfaces — if this
    // test fails because the copy drifted, mirror the change in the
    // server-side email footers (signal_change.py + daily_digest.py).
    expect(node.textContent).toMatch(/Livermore does not place trades/);
  });
});
