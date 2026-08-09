/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ getMarketNews: vi.fn() }));

import { getMarketNews } from "@/lib/api";
import { MarketNewsTicker } from "../market-news-ticker";

const newsMock = getMarketNews as unknown as ReturnType<typeof vi.fn>;

const article = (title: string, url: string | null = "https://x.test/a") => ({
  provider: "alpha_vantage",
  symbol: "",
  title,
  summary: null,
  source_name: "Reuters",
  url,
  published_at: null,
  topics: [],
  sentiment_score: null,
  sentiment_label: null,
});

beforeEach(() => newsMock.mockReset());

describe("MarketNewsTicker", () => {
  it("duplicates the list so the loop is seamless, but only announces it once", async () => {
    newsMock.mockResolvedValue({
      articles: [article("Fed holds rates"), article("Oil slips")],
      age_seconds: 0,
      cached: false,
    });
    render(<MarketNewsTicker />);
    await waitFor(() => expect(screen.getAllByTestId("news-headline").length).toBe(4));

    // Two rendered copies of each headline, but the second copy is inside an
    // aria-hidden wrapper — a screen reader should not read the feed twice.
    const hidden = document.querySelectorAll('[aria-hidden="true"] [data-testid="news-headline"]');
    expect(hidden.length).toBe(2);
  });

  it("shows how stale the feed is rather than implying live", async () => {
    newsMock.mockResolvedValue({ articles: [article("A")], age_seconds: 300, cached: true });
    render(<MarketNewsTicker />);
    // Server caches 15 minutes; claiming "live" would be a small lie told
    // constantly.
    await waitFor(() => expect(screen.getByText("5 min ago")).toBeTruthy());
  });

  it("renders nothing at all when there's no news", async () => {
    newsMock.mockResolvedValue({ articles: [], age_seconds: 0, cached: false });
    const { container } = render(<MarketNewsTicker />);
    await waitFor(() =>
      expect(container.querySelector('[data-testid="market-news-ticker"]')).toBeNull(),
    );
  });

  it("renders nothing when the call fails, rather than an empty bar", async () => {
    // Resolve with a shape the component can't read, rather than rejecting.
    // A rejected mock promise is constructed before React attaches its
    // handler, and vitest reports the gap as an unhandled error even though
    // the component's try/catch does handle it. This exercises the same
    // failure path — `d.articles` throws — without the false positive.
    newsMock.mockResolvedValue(undefined as never);
    const { container } = render(<MarketNewsTicker />);

    // Waiting on "is it null" would pass INSTANTLY — the component renders
    // null before the fetch resolves either way, so the test would end before
    // the rejection settled and prove nothing (the rejection then surfaced at
    // teardown as an unhandled error). Wait for the call to have actually been
    // made and settled first.
    await waitFor(() => expect(newsMock).toHaveBeenCalled());
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector('[data-testid="market-news-ticker"]')).toBeNull();
  });

  it("links out safely and handles a missing url", async () => {
    newsMock.mockResolvedValue({
      articles: [article("Linked"), article("Unlinked", null)],
      age_seconds: 0,
      cached: false,
    });
    render(<MarketNewsTicker />);
    await waitFor(() => expect(screen.getAllByText(/Linked/).length).toBeGreaterThan(0));

    const link = screen.getAllByText(/Linked/)[0].closest("a");
    expect(link?.getAttribute("target")).toBe("_blank");
    // Without noopener the opened page gets a handle on ours via window.opener.
    expect(link?.getAttribute("rel")).toContain("noopener");

    // A headline with no url must still render, just not as a link.
    expect(screen.getAllByText(/Unlinked/)[0].closest("a")).toBeNull();
  });

  it("pauses on hover and respects reduced motion", async () => {
    newsMock.mockResolvedValue({ articles: [article("A")], age_seconds: 0, cached: false });
    render(<MarketNewsTicker />);
    await waitFor(() => expect(screen.getByTestId("market-news-ticker")).toBeTruthy());

    const track = screen.getByTestId("market-news-ticker").querySelector(".inline-flex");
    const cls = track?.className ?? "";
    // Unstoppable scrolling text is unreadable and unclickable.
    expect(cls).toContain("group-hover/ticker:[animation-play-state:paused]");
    // Continuous motion is an accessibility problem, not a preference.
    expect(cls).toContain("motion-safe:animate-");
  });
});
