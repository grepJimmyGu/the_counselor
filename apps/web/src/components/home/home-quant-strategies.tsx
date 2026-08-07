"use client";

/**
 * Home block 3 — quant strategies.
 *
 * Classic templates plus a build-from-scratch entry, per Jimmy's six-block
 * spec. Reads `researchTemplates` (already in contracts) and opens the existing
 * strategy wizard — the page owns that modal's state, so both actions arrive as
 * callbacks.
 *
 * NO PERFORMANCE NUMBERS. Templates carry a `perfContext` field that reads like
 * backtested returns but is hand-written prose, and there is no store of real
 * per-template performance (checked: `strategy_live_performance` is slug-keyed
 * and lacks the columns; `BacktestRecord` has the metrics but never persists
 * `template_id`). Showing a return here would be inventing one.
 *
 * What IS shown instead is `evidenceTier` — A = strong academic support,
 * B = mixed, C = practitioner-only. That's a real, sourced claim about how well
 * the idea is supported, which is the honest version of "how good is this?".
 */

import { Plus } from "lucide-react";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";

/** Unavailable templates are hidden — a card you can't run is an advert. */
const SHOWN = researchTemplates.filter((t) => t.availability !== "unavailable").slice(0, 5);

const TIER_LABEL: Record<string, string> = {
  A: "Strong academic support",
  B: "Mixed evidence",
  C: "Practitioner convention",
};

function TierBadge({ tier }: { tier?: string }) {
  if (!tier) return null;
  const key = tier.trim().charAt(0).toUpperCase();
  const label = TIER_LABEL[key];
  if (!label) return null;
  return (
    <span
      title={label}
      className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
    >
      Evidence {key}
    </span>
  );
}

function TemplateCard({
  t,
  onOpen,
}: {
  t: ResearchTemplate;
  onOpen: (t: ResearchTemplate) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(t)}
      data-testid="quant-strategy"
      className="rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold">{t.name}</span>
        <TierBadge tier={t.evidenceTier} />
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {t.whatItCaptures || t.whatItTests || t.description}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground/80">
        <span>{t.category}</span>
        {t.horizonBadge && (
          <>
            <span aria-hidden="true">·</span>
            <span>{t.horizonBadge}</span>
          </>
        )}
        {t.availability === "proxy" && (
          <>
            <span aria-hidden="true">·</span>
            {/* Say it on the card, not in a modal after they've committed. */}
            <span className="text-amber-700">ETF proxy</span>
          </>
        )}
      </div>
    </button>
  );
}

export function HomeQuantStrategies({
  onOpenTemplate,
  onBuildFromScratch,
}: {
  onOpenTemplate: (t: ResearchTemplate) => void;
  onBuildFromScratch: () => void;
}) {
  return (
    <section
      className="rounded-xl border border-border bg-white p-5"
      data-testid="home-quant-strategies"
    >
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-heading text-base font-semibold">Quant strategies</h2>
        <span className="text-xs text-muted-foreground">Backtest before you commit</span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {SHOWN.map((t) => (
          <TemplateCard key={t.id} t={t} onOpen={onOpenTemplate} />
        ))}

        <button
          type="button"
          onClick={onBuildFromScratch}
          data-testid="quant-build-from-scratch"
          className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border p-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-muted/30 hover:text-foreground"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Build from scratch
        </button>
      </div>
    </section>
  );
}
