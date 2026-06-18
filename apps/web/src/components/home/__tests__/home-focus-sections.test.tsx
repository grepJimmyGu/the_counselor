/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const startFlowMock = vi.fn();
vi.mock("@/lib/flows/runtime", () => ({
  startFlow: (...a: unknown[]) => startFlowMock(...a),
}));
// Mock the seed context to {} so the launcher payloads assert cleanly.
vi.mock("@/lib/flows/custom-build-mode-context", () => ({
  INITIAL_CUSTOM_BUILD_CONTEXT: {},
}));
// Side-effect flow registrations are no-ops under test.
vi.mock("@/lib/flows/one-asset-mode", () => ({}));
vi.mock("@/lib/flows/portfolio-mode", () => ({}));
vi.mock("@/lib/flows/custom-build-mode", () => ({}));
// Stub the two reused child tiles (they self-fetch / use live quotes).
vi.mock("@/components/home/home-themes-firing-today", () => ({
  HomeThemesFiringToday: () => <div data-testid="themes-firing-today" />,
}));
vi.mock("@/components/home/saved-strategies-tile", () => ({
  SavedStrategiesTile: () => <div data-testid="saved-strategies-tile" />,
}));

import { HomeFocusSections } from "../home-focus-sections";

describe("HomeFocusSections", () => {
  beforeEach(() => startFlowMock.mockClear());

  it("renders the three intent-grouped focus sections", () => {
    render(<HomeFocusSections />);
    expect(screen.getByTestId("focus-discover")).toBeTruthy();
    expect(screen.getByTestId("focus-build")).toBeTruthy();
    expect(screen.getByTestId("focus-continuity")).toBeTruthy();
  });

  it("Focus 1 embeds the themes-firing-today cards and a screen-the-market launcher", () => {
    render(<HomeFocusSections />);
    // Discovery cards are reused, not re-implemented.
    expect(screen.getByTestId("themes-firing-today")).toBeTruthy();

    fireEvent.click(screen.getByTestId("focus-screen-market"));
    expect(startFlowMock).toHaveBeenCalledWith("custom_build_mode", {
      initialContext: {
        universe_id: "sp500",
        // PRD-24a §5 — only this entry opens on the gallery step.
        show_template_gallery: true,
        fromTrigger: "home/screen_market",
      },
    });
  });

  it("Focus 2 launches all three build flows (template wizard, portfolio, custom build)", () => {
    render(<HomeFocusSections />);

    // Try a template → the guided 5-step single-asset wizard (one_asset_mode),
    // NOT the static /templates gallery.
    fireEvent.click(screen.getByTestId("focus-try-template"));
    expect(startFlowMock).toHaveBeenCalledWith("one_asset_mode", {
      initialContext: { fromTrigger: "home/pick_asset" },
    });

    fireEvent.click(screen.getByTestId("focus-upload-portfolio"));
    expect(startFlowMock).toHaveBeenCalledWith("portfolio_mode", {
      initialContext: { fromTrigger: "home/upload_portfolio" },
    });

    fireEvent.click(screen.getByTestId("focus-build-scratch"));
    expect(startFlowMock).toHaveBeenCalledWith("custom_build_mode", {
      initialContext: { fromTrigger: "home/custom_build" },
    });
  });

  it("Focus 3 embeds the saved-strategies tile and links to community + account", () => {
    render(<HomeFocusSections />);
    expect(screen.getByTestId("saved-strategies-tile")).toBeTruthy();
    expect(
      (screen.getByTestId("focus-community") as HTMLAnchorElement).getAttribute(
        "href",
      ),
    ).toBe("/community");
    expect(
      (screen.getByTestId("focus-account") as HTMLAnchorElement).getAttribute(
        "href",
      ),
    ).toBe("/account");
  });
});
