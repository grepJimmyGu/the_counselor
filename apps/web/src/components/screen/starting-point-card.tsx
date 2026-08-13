"use client";

/**
 * <StartingPointCard> — the card for one `RECOMMENDED_TEMPLATES` entry.
 *
 * Extracted from `recommended-templates-gallery.tsx` so the three surfaces that
 * show a starting point render the SAME component rather than three copies of
 * the markup:
 *
 *   - "Screen the market" gallery  (`/flow/custom_build_mode`) — `comfortable`
 *   - Hot Market Picks on Home                                  — `compact`
 *   - Catalysts on Home                                         — `compact`
 *
 * The two kinds look deliberately different, and that difference carries
 * meaning rather than decoration: a `composer` template has real `rules` and
 * ends in a stock list, so it gets the filter mark and "Screen this". A
 * `sentiment` template is LLM-mediated and ends in the sentiment hub, so it
 * gets the sparkle and "View in News & Sentiment". A reader should be able to
 * tell where a card lands before clicking it.
 *
 * Renders as a `<button>` or an `<a>` depending on which the caller needs — the
 * gallery advances a flow (button), Home navigates (link). Same visual either
 * way; a link that isn't a link breaks middle-click and "open in new tab".
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Filter, Sparkles } from "lucide-react";

import type { RecommendedTemplate } from "@/lib/recommended-templates";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = {
  momentum: "Momentum",
  quality: "Quality",
  catalyst: "Catalyst",
  event: "Event",
};

export type CardDensity = "comfortable" | "compact";

/** Padding, type and gaps per density. The home blocks sit in a ~568px column
 *  beside three siblings, so they take the tighter scale; the gallery has a
 *  full page and keeps the roomier one. */
const DENSITY = {
  comfortable: {
    root: "rounded-2xl p-5",
    mark: "h-8 w-8 rounded-lg",
    icon: "h-4 w-4",
    title: "text-base",
    body: "mt-1 text-sm leading-relaxed",
    cta: "mt-3 text-sm",
    clamp: "",
  },
  compact: {
    root: "rounded-xl p-3",
    mark: "h-7 w-7 rounded-md",
    icon: "h-3.5 w-3.5",
    title: "text-sm",
    body: "mt-0.5 text-xs leading-snug",
    cta: "mt-2 text-xs",
    clamp: "line-clamp-2",
  },
} as const;

function Inner({
  t,
  density,
  count,
}: {
  t: RecommendedTemplate;
  density: CardDensity;
  count?: number;
}) {
  const isSentiment = t.kind === "sentiment";
  const d = DENSITY[density];
  return (
    <>
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center justify-center border",
            d.mark,
            isSentiment
              ? "border-amber-200 bg-amber-50 text-amber-600"
              : "border-primary/20 bg-primary/5 text-primary",
          )}
        >
          {isSentiment ? (
            <Sparkles className={d.icon} />
          ) : (
            <Filter className={d.icon} />
          )}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {CATEGORY_LABEL[t.category] ?? t.category}
        </span>
        {/* The live match count is the whole value of the card on Home — it is
            the difference between "here is an idea" and "here are 41 names". */}
        {count !== undefined && (
          <span className="ml-auto font-mono text-[11px] tabular-nums text-muted-foreground">
            {count}
          </span>
        )}
      </div>
      <h3 className={cn("font-heading font-semibold", d.title)}>{t.name}</h3>
      <p className={cn("flex-1 text-muted-foreground", d.body, d.clamp)}>
        {t.tagline}
      </p>
      <span
        className={cn(
          "inline-flex items-center gap-1 font-medium text-primary",
          d.cta,
        )}
      >
        {isSentiment ? "View in News & Sentiment" : "Screen this"}
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </>
  );
}

const SHELL =
  "group flex h-full cursor-pointer flex-col border border-slate-200 bg-white text-left shadow-sm " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Hover differs by density, deliberately.
 *
 * `comfortable` keeps the gallery's original lift — extracting this component
 * must not change a pixel on the surface it came from, or the extraction stops
 * being reviewable at a glance.
 *
 * `compact` drops to colour only. The lift rule exists BECAUSE of dense grids:
 * a translate on a card packed against three siblings nudges the row and reads
 * as the layout twitching under the pointer. The gallery is a full page with
 * air around each card, so it doesn't have that problem. */
const HOVER = {
  comfortable:
    "transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg",
  compact:
    "transition-colors duration-200 hover:border-primary/40 hover:bg-slate-50/60",
} as const;

export function StartingPointCard({
  t,
  density = "comfortable",
  count,
  href,
  onPick,
  testId,
}: {
  t: RecommendedTemplate;
  density?: CardDensity;
  /** Live match count, right-aligned on the category row. Home only. */
  count?: number;
  /** Render as a link. Mutually exclusive with `onPick`. */
  href?: string;
  onPick?: (t: RecommendedTemplate) => void;
  testId?: string;
}) {
  const cls = cn(SHELL, HOVER[density], DENSITY[density].root);
  const body = <Inner t={t} density={density} count={count} />;

  if (href) {
    return (
      <Link href={href as Route} data-testid={testId ?? `starting-point-${t.id}`} className={cls}>
        {body}
      </Link>
    );
  }
  return (
    <button
      type="button"
      data-testid={testId ?? `starting-point-${t.id}`}
      onClick={() => onPick?.(t)}
      className={cls}
    >
      {body}
    </button>
  );
}
