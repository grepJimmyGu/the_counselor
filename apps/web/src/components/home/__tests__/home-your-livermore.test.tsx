/** @vitest-environment jsdom */
/**
 * Guards the regression that put this file here.
 *
 * `<SavedStrategiesTile>` was rendered only by `home-focus-sections.tsx`. That
 * file was deleted in #323 to remove two OTHER sections it happened to contain,
 * and the tile went with it — a signed-in user's saved strategies lost their
 * only home-page surface, and nothing failed, because nothing asserted the tile
 * was on the page.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/components/home/saved-strategies-tile", () => ({
  SavedStrategiesTile: () => <div data-testid="saved-strategies-tile" />,
}));

import { HomeYourLivermore } from "../home-your-livermore";

describe("HomeYourLivermore", () => {
  it("renders the saved-strategies tile — its only home-page surface", () => {
    render(<HomeYourLivermore />);
    expect(screen.getByTestId("saved-strategies-tile")).toBeTruthy();
  });

  it("keeps the community and account entries", () => {
    render(<HomeYourLivermore />);
    expect(screen.getByTestId("focus-community").getAttribute("href")).toBe("/community");
    expect(screen.getByTestId("focus-account").getAttribute("href")).toBe("/account");
  });
});
