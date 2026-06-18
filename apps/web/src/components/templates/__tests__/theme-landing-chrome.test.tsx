/** @vitest-environment jsdom */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ThemeBanner,
  TryOtherThemes,
  recommendedTemplateHref,
} from "../theme-landing-chrome";
import { getRecommendedTemplate } from "@/lib/recommended-templates";

describe("theme-landing-chrome (PRD-24a §3.10)", () => {
  it("ThemeBanner shows the template name + the 'what this finds' tagline", () => {
    const t = getRecommendedTemplate("best_momentum")!;
    render(<ThemeBanner template={t} />);
    expect(screen.getByTestId("theme-landing-banner")).toBeTruthy();
    expect(screen.getByText(t.name)).toBeTruthy();
    expect(screen.getByText(/What this finds:/)).toBeTruthy();
    expect(screen.getByText(new RegExp(t.tagline.slice(0, 20)))).toBeTruthy();
  });

  it("TryOtherThemes lists the siblings, excluding the current template", () => {
    render(<TryOtherThemes currentId="best_momentum" />);
    expect(screen.getByTestId("try-other-themes")).toBeTruthy();
    // The current one is excluded; a composer + a sentiment sibling are present.
    expect(screen.queryByTestId("try-theme-best_momentum")).toBeNull();
    expect(screen.getByTestId("try-theme-breakout")).toBeTruthy();
    expect(screen.getByTestId("try-theme-rising_attention")).toBeTruthy();
  });

  it("routes composer → /flow?template= and sentiment → /sentiment deep link", () => {
    expect(recommendedTemplateHref(getRecommendedTemplate("breakout")!)).toBe(
      "/flow/custom_build_mode?template=breakout",
    );
    expect(
      recommendedTemplateHref(getRecommendedTemplate("news_community_confirmed")!),
    ).toBe(
      "/sentiment?toolkit=news_community_confirmed&autorun=1&display=Mainstream+Buyers",
    );
  });

  it("a sibling chip links to the right destination", () => {
    render(<TryOtherThemes currentId="best_momentum" />);
    const composerLink = screen.getByTestId(
      "try-theme-breakout",
    ) as HTMLAnchorElement;
    expect(composerLink.getAttribute("href")).toBe(
      "/flow/custom_build_mode?template=breakout",
    );
    const sentimentLink = screen.getByTestId(
      "try-theme-rising_attention",
    ) as HTMLAnchorElement;
    expect(sentimentLink.getAttribute("href")).toBe(
      "/sentiment?toolkit=rising_attention&autorun=1",
    );
  });
});
