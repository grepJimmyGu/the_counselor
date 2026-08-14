"use client";

/**
 * Home block 3 — **Quant Rules**.
 *
 * Three sections, each answering a different question:
 *   Templates    — a complete strategy that picks the names for you
 *   Overlays     — rules over a book you already hold
 *   Build your own
 *
 * "Try a Template", "Upload Portfolio" and the composer entry all moved here
 * from the old `home-focus-sections` block, which was deleted on 2026-08-14:
 * once the 2x2 carried this content, that section was a second copy of it
 * further down the page.
 *
 * OVERLAYS ARE READ-ONLY HERE. The picker chooses an overlay FOR a portfolio
 * already uploaded, so offering the choice with no holdings dead-ends. These
 * cards describe; the CTA beside them is Upload Portfolio, which is the real
 * next step. Rendered through the SAME `<StrategyCard>` the picker uses, so the
 * overview and the picker cannot drift apart.
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

import { useState } from "react";
import { Layers, Plus, Sparkles, Upload } from "lucide-react";
import { researchTemplates, type OverlayKind, type ResearchTemplate } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import { StrategyCard } from "@/components/strategy-picker/strategy-card";
import { startFlow } from "@/lib/flows/runtime";
import { INITIAL_CUSTOM_BUILD_CONTEXT } from "@/lib/flows/custom-build-mode-context";

/** Unavailable templates are hidden — a card you can't run is an advert. */
/** Three, not five: the row is "Try a Template" plus three, at four columns. */
const SHOWN = researchTemplates.filter((t) => t.availability !== "unavailable").slice(0, 3);

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
}: {
  onOpenTemplate: (t: ResearchTemplate) => void;
}) {
  // Collapsed by default: six overlay cards would dominate a block that has
  // two other sections to show.
  const [showOverlays, setShowOverlays] = useState(false);

  // These launch flows directly rather than arriving as props. The page owns
  // the template MODAL's state (hence `onOpenTemplate`), but a flow is
  // self-contained — `startFlow` navigates — so routing them through the page
  // would add a prop that only forwards.
  const onTryTemplate = () =>
    startFlow("one_asset_mode", { initialContext: { fromTrigger: "home/pick_asset" } });
  const onUploadPortfolio = () =>
    startFlow("portfolio_mode", { initialContext: { fromTrigger: "home/upload_portfolio" } });
  // Straight into the composer, the same landing the old "Build from scratch"
  // card used — a full-page universe picker + primitive catalog + rule canvas.
  // It previously opened the small builder MODAL, which is a different and much
  // narrower surface for the same intent.
  const onBuild = () =>
    startFlow("custom_build_mode", {
      initialContext: { ...INITIAL_CUSTOM_BUILD_CONTEXT, fromTrigger: "home/custom_build" },
    });

  return (
    <section
      className="rounded-xl border border-border bg-white p-4"
      data-testid="home-quant-strategies"
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-semibold">Quant Rules</h2>
        <span className="text-xs text-muted-foreground">Backtest before you commit</span>
      </div>

      {/* ── Templates — complete strategies that pick the names ───────────── */}
      <GroupLabel>Templates — they pick the names for you</GroupLabel>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <button
          type="button"
          onClick={onTryTemplate}
          data-testid="quant-try-template"
          className="flex cursor-pointer flex-col items-start justify-center rounded-lg border border-dashed border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            Try a Template
          </span>
          <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Guided, one stock at a time
          </span>
        </button>
        {SHOWN.map((t) => (
          <TemplateCard key={t.id} t={t} onOpen={onOpenTemplate} />
        ))}
      </div>

      {/* ── Overlays — rules over a book you already hold ─────────────────── */}
      <GroupLabel>Overlays — for a portfolio you already hold</GroupLabel>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => setShowOverlays((v) => !v)}
          aria-expanded={showOverlays}
          data-testid="quant-overlay-overview"
          className="flex cursor-pointer flex-col items-start rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <Layers className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            Overlay overview
          </span>
          <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
            {showOverlays ? "Hide the six" : "See all six, and what each is for"}
          </span>
        </button>
        <button
          type="button"
          onClick={onUploadPortfolio}
          data-testid="quant-upload-portfolio"
          className="flex cursor-pointer flex-col items-start rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
        >
          <span className="flex items-center gap-1.5 text-sm font-semibold">
            <Upload className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            Upload Portfolio
          </span>
          <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
            Then pick an overlay for it
          </span>
        </button>
      </div>

      {showOverlays && (
        <div
          className="mt-1.5 grid grid-cols-1 gap-1.5 sm:grid-cols-2"
          data-testid="quant-overlay-cards"
        >
          {OVERLAY_DISPLAY_ORDER.map((kind) => (
            <StrategyCard
              key={kind}
              meta={OVERLAY_METADATA[kind]}
              ticker="AAPL"
              examplePrice={180}
              // Read-only, so the qualifying badge is informational: it tells
              // the reader what the overlay will need BEFORE they upload.
              holdingsCount={0}
              isSelected={false}
              readOnly
            />
          ))}
        </div>
      )}

      {/* ── Build your own ────────────────────────────────────────────────── */}
      <GroupLabel>Or start from nothing</GroupLabel>
      <button
        type="button"
        onClick={onBuild}
        data-testid="quant-build-from-scratch"
        className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-border p-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-muted/30 hover:text-foreground"
      >
        <Plus className="h-4 w-4" aria-hidden="true" />
        Build your own signals
      </button>
    </section>
  );
}