/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

// next/navigation isn't wired in tests — give it the surface area the brick
// uses. `prefetch` is fire-and-forget so we just need a no-op spy.
const prefetchSpy = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ prefetch: prefetchSpy }),
}));

import { EntryModePicker } from "../entry-mode-picker";
import { __resetRegistryForTests, registerFlow, getFlow } from "../../registry";
import { PortfolioModeFlow } from "../../portfolio-mode";
import { OneAssetModeFlow } from "../../one-asset-mode";

const STORAGE_KEY = (id: string) => `livermore_flow_${id}`;

// NOTE: we intentionally do NOT call `__resetCopyForTests()` here. The
// brick registers its `home_picker` mode-copy as a side-effect at module
// load (`registerModeCopy(...)` at the top of entry-mode-picker.tsx).
// Wiping the copy registry between tests would strip those labels and the
// brick would render raw keys. Other tests that need copy isolation can
// still reset; this file is scoped to one brick + the two flows it can
// launch (portfolio_mode + one_asset_mode).
beforeEach(() => {
  window.sessionStorage.clear();
  __resetRegistryForTests();
  // The brick side-effect-imports portfolio-mode + one-asset-mode, but
  // the modules have already been evaluated; re-registering manually
  // mirrors the pattern in portfolio-mode.flow.test.tsx.
  registerFlow(PortfolioModeFlow);
  registerFlow(OneAssetModeFlow);
  prefetchSpy.mockReset();
});

afterEach(() => {
  window.sessionStorage.clear();
});

describe("EntryModePicker", () => {
  it("renders all three CTAs with their labels and surface attribute", () => {
    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);

    const pick = screen.getByTestId("entry-mode-pick-asset");
    const upload = screen.getByTestId("entry-mode-upload-portfolio");
    const chat = screen.getByTestId("entry-mode-chat-builder");

    expect(pick.textContent).toContain("Pick an asset");
    expect(upload.textContent).toContain("Upload portfolio");
    expect(chat.textContent).toContain("Chat builder");

    expect(pick.getAttribute("data-from")).toBe("home");
    expect(upload.getAttribute("data-from")).toBe("home");
    expect(chat.getAttribute("data-from")).toBe("home");
  });

  it("renders the Pick-an-asset CTA as a button (Sprint 2 — launches one_asset_mode)", () => {
    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);
    const pick = screen.getByTestId("entry-mode-pick-asset");
    expect(pick.tagName).toBe("BUTTON");
  });

  it("launches the one_asset_mode flow when Pick an asset is clicked", () => {
    expect(getFlow("one_asset_mode")).toBeDefined();

    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);
    fireEvent.click(screen.getByTestId("entry-mode-pick-asset"));

    const raw = window.sessionStorage.getItem(STORAGE_KEY("one_asset_mode"));
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("one_asset_mode");
    expect(parsed.currentStepId).toBe("ticker");
    expect(parsed.context.fromTrigger).toBe("home/pick_asset");
    // No ticker on this entry path — the ticker step prompts for one.
    expect(parsed.context.ticker).toBeUndefined();
  });

  it("launches the portfolio flow when Upload portfolio is clicked", () => {
    expect(getFlow("portfolio_mode")).toBeDefined();

    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);
    fireEvent.click(screen.getByTestId("entry-mode-upload-portfolio"));

    const raw = window.sessionStorage.getItem(STORAGE_KEY("portfolio_mode"));
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed.flowId).toBe("portfolio_mode");
    expect(parsed.currentStepId).toBe("upload");
    expect(parsed.context.fromTrigger).toBe("home/upload_portfolio");
  });

  it("composes the fromTrigger from the surface prop", () => {
    render(
      <EntryModePicker from="reengagement_modal" onChatBuilderOpen={() => {}} />
    );

    fireEvent.click(screen.getByTestId("entry-mode-pick-asset"));
    expect(
      JSON.parse(
        window.sessionStorage.getItem(STORAGE_KEY("one_asset_mode"))!,
      ).context.fromTrigger,
    ).toBe("reengagement_modal/pick_asset");

    fireEvent.click(screen.getByTestId("entry-mode-upload-portfolio"));
    expect(
      JSON.parse(
        window.sessionStorage.getItem(STORAGE_KEY("portfolio_mode"))!,
      ).context.fromTrigger,
    ).toBe("reengagement_modal/upload_portfolio");
  });

  it("prefetches the portfolio flow route on hover and focus", () => {
    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);
    const btn = screen.getByTestId("entry-mode-upload-portfolio");

    fireEvent.mouseEnter(btn);
    expect(prefetchSpy).toHaveBeenCalledWith("/flow/portfolio_mode");

    prefetchSpy.mockReset();
    fireEvent.focus(btn);
    expect(prefetchSpy).toHaveBeenCalledWith("/flow/portfolio_mode");
  });

  it("prefetches the one-asset flow route on hover and focus", () => {
    render(<EntryModePicker from="home" onChatBuilderOpen={() => {}} />);
    const btn = screen.getByTestId("entry-mode-pick-asset");

    fireEvent.mouseEnter(btn);
    expect(prefetchSpy).toHaveBeenCalledWith("/flow/one_asset_mode");

    prefetchSpy.mockReset();
    fireEvent.focus(btn);
    expect(prefetchSpy).toHaveBeenCalledWith("/flow/one_asset_mode");
  });

  it("calls onChatBuilderOpen exactly once when the chat CTA is clicked", () => {
    const onChatBuilderOpen = vi.fn();
    render(
      <EntryModePicker from="home" onChatBuilderOpen={onChatBuilderOpen} />
    );
    fireEvent.click(screen.getByTestId("entry-mode-chat-builder"));
    expect(onChatBuilderOpen).toHaveBeenCalledTimes(1);
  });
});
