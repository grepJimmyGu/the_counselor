/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  INITIAL_CUSTOM_BUILD_CONTEXT,
  type CustomBuildModeContext,
} from "@/lib/flows/custom-build-mode-context";
import {
  RecommendedTemplatesGallery,
  sentimentTemplateHref,
} from "../recommended-templates-gallery";

function makeProps(overrides: Partial<CustomBuildModeContext> = {}) {
  const advance = vi.fn();
  const context = {
    ...INITIAL_CUSTOM_BUILD_CONTEXT,
    fromTrigger: "test",
    ...overrides,
  } as CustomBuildModeContext;
  return {
    advance,
    props: {
      context,
      advance,
      updateContext: vi.fn(),
      back: vi.fn(),
      abort: vi.fn(),
    },
  };
}

function setUrl(search: string) {
  window.history.replaceState({}, "", `/flow/custom_build_mode${search}`);
}

describe("RecommendedTemplatesGallery (PRD-24a §5)", () => {
  beforeEach(() => setUrl(""));

  it("renders the gallery when show_template_gallery is set and no ?template", () => {
    const { advance, props } = makeProps({ show_template_gallery: true });
    render(<RecommendedTemplatesGallery {...props} />);
    expect(screen.getByTestId("recommended-templates-gallery")).toBeTruthy();
    // The registry's templates render as cards (composer + sentiment).
    expect(screen.getByTestId("gallery-template-best_momentum")).toBeTruthy();
    expect(screen.getByTestId("gallery-template-positive_catalyst")).toBeTruthy();
    expect(advance).not.toHaveBeenCalled();
  });

  it("auto-advances (skips the gallery) when the flag is not set", () => {
    const { advance, props } = makeProps({ show_template_gallery: false });
    render(<RecommendedTemplatesGallery {...props} />);
    expect(advance).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("recommended-templates-gallery")).toBeNull();
  });

  it("auto-advances when a ?template= deep link is already present", () => {
    setUrl("?template=best_momentum");
    const { advance, props } = makeProps({ show_template_gallery: true });
    render(<RecommendedTemplatesGallery {...props} />);
    expect(advance).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("recommended-templates-gallery")).toBeNull();
  });

  it("a composer pick stamps ?template= and advances (the canvas then hydrates)", () => {
    const { advance, props } = makeProps({ show_template_gallery: true });
    render(<RecommendedTemplatesGallery {...props} />);
    fireEvent.click(screen.getByTestId("gallery-template-breakout"));
    expect(new URLSearchParams(window.location.search).get("template")).toBe(
      "breakout",
    );
    expect(advance).toHaveBeenCalledTimes(1);
  });

  it("a sentiment pick navigates to the /sentiment deep link (no advance)", () => {
    // jsdom's location.assign is non-configurable; swap the whole location.
    const assignMock = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: {
        search: "",
        href: "http://localhost/flow/custom_build_mode",
        pathname: "/flow/custom_build_mode",
        assign: assignMock,
      },
    });
    try {
      const { advance, props } = makeProps({ show_template_gallery: true });
      render(<RecommendedTemplatesGallery {...props} />);
      fireEvent.click(
        screen.getByTestId("gallery-template-news_community_confirmed"),
      );
      expect(assignMock).toHaveBeenCalledWith(
        "/sentiment?toolkit=news_community_confirmed&autorun=1&display=Mainstream+Buyers",
      );
      expect(advance).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        writable: true,
        value: original,
      });
    }
  });

  it('"start from a blank composer" advances with no template param', () => {
    const { advance, props } = makeProps({ show_template_gallery: true });
    render(<RecommendedTemplatesGallery {...props} />);
    fireEvent.click(screen.getByTestId("gallery-start-blank"));
    expect(advance).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe("");
  });

  it("sentimentTemplateHref builds toolkit + autorun (+ optional display)", () => {
    expect(
      sentimentTemplateHref({
        kind: "sentiment",
        id: "rising_attention",
        name: "Rising Attention",
        category: "catalyst",
        tagline: "t",
        toolkit_id: "rising_attention",
      }),
    ).toBe("/sentiment?toolkit=rising_attention&autorun=1");
  });
});
