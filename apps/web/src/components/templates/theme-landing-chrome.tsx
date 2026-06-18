"use client";

/**
 * PRD-24a §3.10 — theme-landing chrome.
 *
 * Two registry-driven pieces that dress a theme destination (the /sentiment
 * hub, the scan-results brick) as a proper landing page:
 *   - <ThemeBanner>     — which theme you're viewing + "What this finds"
 *                         (auto-derived from the template's tagline).
 *   - <TryOtherThemes>  — lateral nav to the sibling recommended templates.
 *
 * Both read RECOMMENDED_TEMPLATES, so adding a template later surfaces it here
 * for free (the lego-brick rule).
 */

import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Filter, Sparkles } from "lucide-react";
import {
  RECOMMENDED_TEMPLATES,
  type RecommendedTemplate,
} from "@/lib/recommended-templates";

/** Where a recommended template routes: the composer (preload via #236) for a
 *  composer template, or the sentiment hub deep link (#239) for a sentiment one. */
export function recommendedTemplateHref(t: RecommendedTemplate): Route {
  if (t.kind === "sentiment") {
    const p = new URLSearchParams({ toolkit: t.toolkit_id, autorun: "1" });
    if (t.display_label) p.set("display", t.display_label);
    return `/sentiment?${p.toString()}` as Route;
  }
  return `/flow/custom_build_mode?template=${t.id}` as Route;
}

export function ThemeBanner({ template }: { template: RecommendedTemplate }) {
  const isSentiment = template.kind === "sentiment";
  return (
    <section
      data-testid="theme-landing-banner"
      className="rounded-2xl border border-primary/20 bg-primary/5 p-5"
    >
      <div className="flex items-start gap-3">
        <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
          {isSentiment ? (
            <Sparkles className="h-5 w-5" />
          ) : (
            <Filter className="h-5 w-5" />
          )}
        </span>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Theme
          </p>
          <h2 className="font-heading text-lg font-semibold">{template.name}</h2>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">What this finds: </span>
            {template.tagline}
          </p>
        </div>
      </div>
    </section>
  );
}

export function TryOtherThemes({ currentId }: { currentId: string }) {
  const others = RECOMMENDED_TEMPLATES.filter((t) => t.id !== currentId);
  if (others.length === 0) return null;
  return (
    <section
      data-testid="try-other-themes"
      className="border-t border-border/60 pt-5"
    >
      <p className="mb-3 text-sm font-semibold">Try other themes</p>
      <div className="flex flex-wrap gap-2">
        {others.map((t) => (
          <Link
            key={t.id}
            href={recommendedTemplateHref(t)}
            data-testid={`try-theme-${t.id}`}
            className="group inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-white px-3 py-1.5 text-xs font-medium shadow-sm transition-all hover:border-primary/40 hover:shadow"
          >
            {t.name}
            <ArrowRight className="h-3 w-3 text-primary transition-transform group-hover:translate-x-0.5" />
          </Link>
        ))}
      </div>
    </section>
  );
}
