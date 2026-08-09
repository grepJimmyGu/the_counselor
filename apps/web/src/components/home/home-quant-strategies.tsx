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
import { researchTemplates, type OverlayKind, type ResearchTemplate } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { startFlow } from "@/lib/flows/runtime";

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

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 mt-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground first:mt-0">
      {children}
    </div>
  );
}

/**
 * An overlay card. Clicking starts Portfolio Mode with this overlay ALREADY
 * chosen, so the user's path is: pick here -> upload -> results.
 *
 * The overlay step can't literally move before upload — `OverlayPicker` reads
 * `context.holdings` to validate `minHoldings` and to build the backtest JSON,
 * so it has nothing to work with until the portfolio exists. But the picker
 * already seeds its selection from `context.selectedOverlay`, so passing it
 * through `initialContext` gives the same effect: the choice happens first
 * from the user's point of view, and the picker step becomes a confirm (with
 * the date range and the track record against their actual holdings) rather
 * than a decision.
 */
function OverlayCard({ kind }: { kind: OverlayKind }) {
  const meta = OVERLAY_METADATA[kind];
  return (
    <button
      type="button"
      data-testid="quant-overlay"
      data-overlay={kind}
      onClick={() =>
        startFlow("portfolio_mode", {
          initialContext: {
            selectedOverlay: kind,
            fromTrigger: "home/quant_overlay",
          },
        })
      }
      className="rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold">{meta.label}</span>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
          {meta.tier === "basic" ? "Basic" : "Advanced"}
        </span>
      </div>
      {/* `idea` (the thesis), NOT `tagline`. Taglines carry hard performance
          numbers — "worst loss −28% vs −55%" — with no source in
          `overlay-metadata.ts`. Same call as the template cards: we don't put
          an unsourced return on the home page.

          `fitLabel` is omitted for a simpler reason: it is documented as
          "from diagnosis — shown as a badge when holdings match", and on the
          home page there is no portfolio yet. "Good fit for your portfolio"
          would be a claim about a portfolio we have not seen. */}
      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {meta.idea}
      </p>
      <div className="mt-2 truncate text-[11px] text-muted-foreground/80">
        Needs {meta.minHoldings}+ holding{meta.minHoldings === 1 ? "" : "s"}
      </div>
    </button>
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

      {/* The three offerings are easy to confuse — they differ by WHAT they
          decide for you, and that distinction is invisible from the cards
          alone. Jimmy's framing, 2026-08-09. */}
      <dl className="mb-3 grid grid-cols-1 gap-x-4 gap-y-1.5 rounded-lg bg-muted/30 px-3 py-2.5 text-xs sm:grid-cols-3">
        <div>
          <dt className="font-medium text-foreground">Templates</dt>
          <dd className="text-muted-foreground">Complete strategies — they pick the names for you.</dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Overlays</dt>
          <dd className="text-muted-foreground">
            Rules applied to a portfolio you already hold — they decide when to be
            in or out, not what to own.
          </dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Build your own</dt>
          <dd className="text-muted-foreground">Compose raw signals yourself.</dd>
        </div>
      </dl>

      <GroupLabel>Templates</GroupLabel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {SHOWN.map((t) => (
          <TemplateCard key={t.id} t={t} onOpen={onOpenTemplate} />
        ))}
      </div>

      <GroupLabel>Overlays — for a portfolio you already hold</GroupLabel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {OVERLAY_DISPLAY_ORDER.map((kind) => (
          <OverlayCard key={kind} kind={kind} />
        ))}
      </div>

      <GroupLabel>Or start from nothing</GroupLabel>
      <div className="grid grid-cols-1 gap-2">
        <button
          type="button"
          onClick={onBuildFromScratch}
          data-testid="quant-build-from-scratch"
          className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border p-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-muted/30 hover:text-foreground"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Build your own signals
        </button>
      </div>
    </section>
  );
}
