/** @vitest-environment jsdom */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  searchSymbols: vi.fn(async () => [{ symbol: "NVDA", name: "NVIDIA Corp" }]),
}));

import { PortfolioUpload } from "../portfolio-upload";

function renderUpload(overrides: { context?: Partial<{ holdings: any[] }> } = {}) {
  const advance = vi.fn();
  const updateContext = vi.fn();
  const ctx = {
    fromTrigger: "test/start",
    ...overrides.context,
  } as any;
  render(
    <PortfolioUpload
      context={ctx}
      updateContext={updateContext}
      advance={advance}
      back={() => {}}
      abort={() => {}}
    />,
  );
  return { advance, updateContext };
}

describe("PortfolioUpload", () => {
  it("renders the upload title from useFlowCopy", () => {
    renderUpload();
    expect(screen.getByText("Upload your portfolio")).toBeTruthy();
  });

  it("disables Continue when no tickers are entered", () => {
    renderUpload();
    const continueBtn = screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(true);
  });

  it("allows continuing once a ticker is typed", () => {
    const { advance, updateContext } = renderUpload();
    const tickerInput = screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement;
    fireEvent.change(tickerInput, { target: { value: "AAPL" } });
    const continueBtn = screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement;
    expect(continueBtn.disabled).toBe(false);
    fireEvent.click(continueBtn);
    expect(advance).toHaveBeenCalledTimes(1);
    expect(updateContext).toHaveBeenCalledTimes(1);
    const patch = updateContext.mock.calls[0][0];
    expect(patch.holdings).toHaveLength(1);
    expect(patch.holdings[0].ticker).toBe("AAPL");
  });

  it("parses CSV paste into rows", () => {
    renderUpload();
    const paste = screen.getByTestId("portfolio-upload-paste") as HTMLTextAreaElement;
    fireEvent.change(paste, {
      target: { value: "AAPL,0.4\nMSFT,0.3\nNVDA,0.3" },
    });
    fireEvent.click(screen.getByTestId("portfolio-upload-paste-apply"));
    // Three rows should now be in the table.
    expect((screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement).value).toBe("AAPL");
    expect((screen.getByTestId("portfolio-upload-ticker-1") as HTMLInputElement).value).toBe("MSFT");
    expect((screen.getByTestId("portfolio-upload-ticker-2") as HTMLInputElement).value).toBe("NVDA");
  });

  it("normalizes lowercase tickers to upper-case", () => {
    const { updateContext } = renderUpload();
    const input = screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "aapl" } });
    fireEvent.click(screen.getByTestId("portfolio-upload-continue"));
    const patch = updateContext.mock.calls[0][0];
    expect(patch.holdings[0].ticker).toBe("AAPL");
  });

  it("adds a holding from the search typeahead", async () => {
    renderUpload();
    fireEvent.change(screen.getByTestId("portfolio-upload-search"), {
      target: { value: "NVDA" },
    });
    fireEvent.click(await screen.findByTestId("portfolio-upload-suggestion-NVDA"));
    // The first (empty) row is filled with the picked ticker.
    expect(
      (screen.getByTestId("portfolio-upload-ticker-0") as HTMLInputElement).value,
    ).toBe("NVDA");
  });

  it("does not add a duplicate ticker from search", async () => {
    renderUpload({ context: { holdings: [{ ticker: "NVDA", shares: 1 }] } });
    fireEvent.change(screen.getByTestId("portfolio-upload-search"), {
      target: { value: "NVDA" },
    });
    fireEvent.click(await screen.findByTestId("portfolio-upload-suggestion-NVDA"));
    // Already held → no second row appended.
    expect(screen.queryByTestId("portfolio-upload-ticker-1")).toBeNull();
  });

  it("warns (does not block) when weights don't sum to 1.0", () => {
    renderUpload();
    fireEvent.change(screen.getByTestId("portfolio-upload-ticker-0"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("portfolio-upload-weight-0"), { target: { value: "0.4" } });
    fireEvent.click(screen.getByTestId("portfolio-upload-add"));
    fireEvent.change(screen.getByTestId("portfolio-upload-ticker-1"), { target: { value: "MSFT" } });
    fireEvent.change(screen.getByTestId("portfolio-upload-weight-1"), { target: { value: "0.3" } });
    // Total weight = 0.7. Should show the warning string.
    expect(screen.getByText(/Weights sum to 70%/)).toBeTruthy();
    // Continue button is still enabled (warning, not block).
    expect((screen.getByTestId("portfolio-upload-continue") as HTMLButtonElement).disabled).toBe(false);
  });
});
