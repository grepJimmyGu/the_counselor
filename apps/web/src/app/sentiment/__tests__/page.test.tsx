/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

const runSentimentAnalyzeMock = vi.fn();
vi.mock("@/lib/api", () => ({
  getProvidersStatus: vi.fn(async () => ({})),
  getSentimentToolkits: vi.fn(async () => [
    { id: "positive_catalyst", name: "Positive Catalyst", description: "x" },
    { id: "news_community_confirmed", name: "News + Community Confirmed", description: "y" },
  ]),
  runSentimentAnalyze: (...a: unknown[]) => runSentimentAnalyzeMock(...a),
}));

import SentimentHubPage from "../page";

function setSearch(s: string) {
  window.history.replaceState({}, "", `/sentiment${s}`);
}

describe("SentimentHubPage — theme deep-link (PRD-24a §3.10 B1)", () => {
  beforeEach(() => {
    runSentimentAnalyzeMock.mockReset();
    runSentimentAnalyzeMock.mockResolvedValue({
      candidates: [],
      provider_status: {},
      warnings: [],
    });
    // jsdom doesn't implement scrollIntoView.
    Element.prototype.scrollIntoView = vi.fn();
    setSearch("");
  });

  it("auto-runs the deep-linked toolkit and labels the header via ?display=", async () => {
    setSearch("?toolkit=news_community_confirmed&autorun=1&display=mainstream_buyers");
    render(<SentimentHubPage />);

    await waitFor(() =>
      expect(runSentimentAnalyzeMock).toHaveBeenCalledWith(
        expect.anything(),
        "news_community_confirmed",
      ),
    );
    // §3.10 — news_community_confirmed is a recommended template, so the theme
    // landing chrome (banner + "try other themes" footer) renders.
    await waitFor(() => screen.getByTestId("theme-landing-banner"));
    expect(screen.getByTestId("try-other-themes")).toBeTruthy();
    // "Mainstream Buyers" shows in BOTH the banner (template name) and the
    // results header (the ?display= override) — at least one, ≥1.
    expect(screen.getAllByText("Mainstream Buyers").length).toBeGreaterThan(0);
  });

  it("does NOT auto-run without ?autorun=1", async () => {
    setSearch("?toolkit=positive_catalyst");
    render(<SentimentHubPage />);
    await waitFor(() => screen.getByText("Pre-built Toolkits"));
    expect(runSentimentAnalyzeMock).not.toHaveBeenCalled();
  });

  it("ignores an unknown toolkit id", async () => {
    setSearch("?toolkit=does_not_exist&autorun=1");
    render(<SentimentHubPage />);
    await waitFor(() => screen.getByText("Pre-built Toolkits"));
    expect(runSentimentAnalyzeMock).not.toHaveBeenCalled();
  });
});
