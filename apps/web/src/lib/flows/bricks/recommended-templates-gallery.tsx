"use client";

/**
 * <RecommendedTemplatesGallery> — PRD-24a §5, the L2 template gallery.
 *
 * The FIRST step of custom_build_mode when entered via the Home "Screen the
 * market" callout: a browsable menu of the ~10 recommended starting points.
 * Picking one routes into the right surface, reusing existing wiring:
 *   - composer template → set `?template=<id>` + advance to the composer,
 *     which hydrates the preset via useTemplatePreload (#236). Full reuse.
 *   - sentiment template → leave the flow for /sentiment?toolkit=…&autorun=1
 *     (the deep link the hub now honors, #239).
 *   - "Start from a blank composer" → advance with no template.
 *
 * Auto-skips (renders nothing, advances on mount) for EVERY other entry: the
 * `show_template_gallery` flag is unset (Build-from-scratch, the /screens ·
 * /account · /signal-library links) OR a `?template=` deep link is already
 * present (the theme card / a shared composer link).
 */

import * as React from "react";
import { ArrowRight, Filter, Sparkles } from "lucide-react";
import type { FlowStepProps } from "@/lib/flows/types";
import type { CustomBuildModeContext } from "@/lib/flows/custom-build-mode-context";
import {
  RECOMMENDED_TEMPLATES,
  type RecommendedTemplate,
} from "@/lib/recommended-templates";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = {
  momentum: "Momentum",
  quality: "Quality",
  catalyst: "Catalyst",
  event: "Event",
};

function hasTemplateParam(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return new URLSearchParams(window.location.search).has("template");
  } catch {
    return false;
  }
}

function setTemplateParam(id: string): void {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    url.searchParams.set("template", id);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  } catch {
    // ignore — worst case the composer opens blank
  }
}

export function sentimentTemplateHref(
  t: Extract<RecommendedTemplate, { kind: "sentiment" }>,
): string {
  const params = new URLSearchParams({ toolkit: t.toolkit_id, autorun: "1" });
  if (t.display_label) params.set("display", t.display_label);
  return `/sentiment?${params.toString()}`;
}

function TemplateCard({
  t,
  onPick,
}: {
  t: RecommendedTemplate;
  onPick: (t: RecommendedTemplate) => void;
}) {
  const isSentiment = t.kind === "sentiment";
  return (
    <button
      type="button"
      data-testid={`gallery-template-${t.id}`}
      onClick={() => onPick(t)}
      className="group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "inline-flex h-8 w-8 items-center justify-center rounded-lg border",
            isSentiment
              ? "border-amber-200 bg-amber-50 text-amber-600"
              : "border-primary/20 bg-primary/5 text-primary",
          )}
        >
          {isSentiment ? (
            <Sparkles className="h-4 w-4" />
          ) : (
            <Filter className="h-4 w-4" />
          )}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {CATEGORY_LABEL[t.category] ?? t.category}
        </span>
      </div>
      <h3 className="font-heading text-base font-semibold">{t.name}</h3>
      <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">
        {t.tagline}
      </p>
      <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary">
        {isSentiment ? "View in News & Sentiment" : "Screen this"}
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </button>
  );
}

export function RecommendedTemplatesGallery({
  context,
  advance,
}: FlowStepProps<CustomBuildModeContext>) {
  const decided = React.useRef(false);
  // null = still deciding (render nothing); false = show gallery; true = skip.
  const [skip, setSkip] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    // Show ONLY for an explicit "Screen the market" launch without a deep
    // link; every other entry advances straight to the blank composer.
    if (!context.show_template_gallery || hasTemplateParam()) {
      setSkip(true);
      advance();
    } else {
      setSkip(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onPick = React.useCallback(
    (t: RecommendedTemplate) => {
      if (t.kind === "sentiment") {
        if (typeof window !== "undefined") {
          window.location.assign(sentimentTemplateHref(t));
        }
        return;
      }
      // Composer: stamp ?template=<id> so the canvas hydrates it (#236), advance.
      setTemplateParam(t.id);
      advance();
    },
    [advance],
  );

  if (skip !== false) return null; // deciding or skipping → the advance fires

  return (
    <div className="mx-auto max-w-5xl" data-testid="recommended-templates-gallery">
      <header className="mb-6 text-center">
        <h1 className="font-heading text-2xl font-bold">Pick a starting point</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Start from a ready-made screen or sentiment read — you can tweak every
          rule next. Or build your own from scratch.
        </p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {RECOMMENDED_TEMPLATES.map((t) => (
          <TemplateCard key={t.id} t={t} onPick={onPick} />
        ))}
      </div>
      <div className="mt-6 text-center">
        <button
          type="button"
          data-testid="gallery-start-blank"
          onClick={() => advance()}
          className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          Start from a blank composer instead
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
