/** @vitest-environment jsdom */
/**
 * The share control on "Moving today".
 *
 * The assertions here are about the two things that can hand a user a broken
 * card: offering a language the backend can't draw, and looking hung during a
 * generation that genuinely takes a while.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  createDailyCard: vi.fn(),
  getDailyCardLanguages: vi.fn(),
  dailyCardImageUrl: (lang: string, d?: string) => `http://api.test/card.png?lang=${lang}&d=${d}`,
}));

import { createDailyCard, getDailyCardLanguages } from "@/lib/api";
import { ShareCardButton } from "../share-card-button";

const createMock = createDailyCard as unknown as ReturnType<typeof vi.fn>;
const langsMock = getDailyCardLanguages as unknown as ReturnType<typeof vi.fn>;

const card = (lang = "en") => ({
  trading_date: "2026-08-11",
  lang,
  model: "gpt-5",
  payload: {},
  copy: {},
});

beforeEach(() => {
  vi.clearAllMocks();
  langsMock.mockResolvedValue({ languages: ["en"] });
  createMock.mockResolvedValue(card());
});

describe("ShareCardButton", () => {
  it("costs a home-page visitor nothing until the button is clicked", async () => {
    render(<ShareCardButton />);
    // This sits on the home page. The POST spends an LLM call and locks the
    // day's card; even the capability probe is a request every visitor would
    // pay for to support the few who actually share. Neither fires on mount.
    await Promise.resolve();
    expect(createMock).not.toHaveBeenCalled();
    expect(langsMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("share-card-button"));
    await waitFor(() => expect(langsMock).toHaveBeenCalled());
  });

  it("generates and shows the card when opened", async () => {
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    const img = await screen.findByTestId("share-card-image");
    expect(img.getAttribute("src")).toContain("lang=en");
    expect(createMock).toHaveBeenCalledWith("en", "US");
  });

  it("hides the language picker when only one language can be drawn", async () => {
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    await screen.findByTestId("share-card-image");
    // Production has no CJK font, so Chinese isn't drawable — a picker with a
    // single dead option is worse than no picker.
    expect(screen.queryByTestId("share-card-langs")).toBeNull();
  });

  it("offers Chinese only when the backend says it can draw it", async () => {
    langsMock.mockResolvedValue({ languages: ["en", "zh"] });
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    await screen.findByTestId("share-card-image");
    const picker = await screen.findByTestId("share-card-langs");
    expect(picker.textContent).toContain("中文");

    fireEvent.click(screen.getByText("中文"));
    await waitFor(() => expect(createMock).toHaveBeenCalledWith("zh", "US"));
  });

  it("falls back to a drawable language if the current pick is not offered", async () => {
    // Defensive: the backend is the authority on what it can draw, so a stale
    // default must not survive the probe.
    langsMock.mockResolvedValue({ languages: ["zh"] });
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    await waitFor(() => expect(createMock).toHaveBeenCalledWith("zh", "US"));
  });

  it("degrades to English when the capability probe fails", async () => {
    langsMock.mockRejectedValue(new Error("offline"));
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    await screen.findByTestId("share-card-image");
    expect(createMock).toHaveBeenCalledWith("en", "US");
  });

  it("says the first card of the day is slow rather than looking hung", async () => {
    let release: (v: unknown) => void = () => {};
    createMock.mockReturnValue(new Promise((r) => (release = r)));
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    expect((await screen.findByTestId("share-card-loading")).textContent).toContain("takes a moment");
    release(card());
    await screen.findByTestId("share-card-image");
  });

  it("translates a bare network failure into something actionable", async () => {
    // `fetch` rejects with `TypeError: Failed to fetch` for offline, DNS, CORS
    // and unreachable-server alike. Shown verbatim it tells a reader nothing;
    // it was on screen in the browser before this was fixed.
    createMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    const err = await screen.findByTestId("share-card-error");
    expect(err.textContent).not.toContain("Failed to fetch");
    expect(err.textContent).toContain("connection");
  });

  it("surfaces the reason when generation fails, and can retry", async () => {
    createMock.mockRejectedValueOnce(new Error("No settled close yet."));
    render(<ShareCardButton />);
    fireEvent.click(screen.getByTestId("share-card-button"));
    const err = await screen.findByTestId("share-card-error");
    expect(err.textContent).toContain("No settled close yet.");

    createMock.mockResolvedValue(card());
    fireEvent.click(screen.getByText("Try again"));
    await screen.findByTestId("share-card-image");
  });
});
