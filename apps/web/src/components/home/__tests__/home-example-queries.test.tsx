/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { TradersAsk, EXAMPLE_QUERIES } from "../home-example-queries";
import { RUN_QUERY_EVENT } from "@/components/search/smart-search-box";

describe("TradersAsk — the strip inside Hot Market Picks", () => {
  it("dispatches the query text rather than navigating", () => {
    const seen: string[] = [];
    const onRun = (e: Event) => seen.push((e as CustomEvent<string>).detail);
    window.addEventListener(RUN_QUERY_EVENT, onRun);

    render(<TradersAsk />);
    const first = screen.getAllByTestId("example-query")[0];
    const text = first.textContent ?? "";
    fireEvent.click(first);

    window.removeEventListener(RUN_QUERY_EVENT, onRun);
    // The point of the block: the query lands in the box so the user sees it
    // as typed text and learns they can write their own.
    expect(seen).toEqual([text]);
  });

  it("switches the visible set when a tab is picked", () => {
    render(<TradersAsk />);
    const before = screen.getAllByTestId("example-query").map((e) => e.textContent);
    fireEvent.click(screen.getByTestId("query-tab-fundamentals"));
    const after = screen.getAllByTestId("example-query").map((e) => e.textContent);
    expect(after).not.toEqual(before);
    expect(after).toContain("p/e under 15");
  });

  it("marks the active tab for assistive tech", () => {
    render(<TradersAsk />);
    expect(screen.getByTestId("query-tab-trend").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByTestId("query-tab-reversal"));
    expect(screen.getByTestId("query-tab-reversal").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("query-tab-trend").getAttribute("aria-pressed")).toBe("false");
  });

  it("every tab has queries — an empty tab is why we didn't copy 問財's 3", () => {
    render(<TradersAsk />);
    for (const id of ["trend", "reversal", "fundamentals"]) {
      fireEvent.click(screen.getByTestId(`query-tab-${id}`));
      expect(screen.getAllByTestId("example-query").length).toBeGreaterThan(2);
    }
  });

  it("exports its queries for the backend contract test", () => {
    // `test_home_example_queries.py` re-parses the .tsx; this export is the
    // in-band copy so a refactor that breaks the regex is caught here too.
    expect(EXAMPLE_QUERIES.length).toBeGreaterThan(8);
    expect(new Set(EXAMPLE_QUERIES).size).toBe(EXAMPLE_QUERIES.length); // no dupes
  });
});
