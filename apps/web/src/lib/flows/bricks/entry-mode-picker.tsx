"use client";

/**
 * <EntryModePicker> — PRD-11 home-page entry-mode picker.
 *
 * Three CTAs that replace the legacy "Describe Your Strategy" teaser on
 * the Home page (and, later, the re-engagement modal that will reuse this
 * brick from the shelf):
 *
 *   1. Pick an asset    → /stocks (Sprint 2 refactors to startFlow('one_asset_mode'))
 *   2. Upload portfolio → startFlow('portfolio_mode', { fromTrigger })
 *   3. Chat builder     → onChatBuilderOpen() — surface decides how to open
 *                         the floating ChatWidget (Home uses dispatchChatSeed)
 *
 * Lives under `lib/flows/bricks/` per the Sprint-1 architecture rule: any
 * launcher that fronts the flow runtime ships as a brick so re-engagement
 * modals can pick it off the shelf without duplicating layout / copy.
 *
 * Mirrors the `apply-strategy-cta.tsx` pattern: registerModeCopy at module
 * load, useFlowCopy for every visible label, `from` prop for surface-aware
 * analytics, no inline navigation logic for the flow-runtime CTA.
 */

import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, MessageSquare, Search, Upload } from "lucide-react";
import { startFlow } from "../runtime";
import { registerModeCopy, useFlowCopy } from "../copy";
// Side-effect import — guarantees `portfolio_mode` is in the registry by the
// time the Upload CTA can fire. Idempotent via the getFlow() guard inside
// portfolio-mode.ts, so the universal /flow/[flowId] shell can also import
// it without colliding.
import "../portfolio-mode";

registerModeCopy("home_picker", {
  section_eyebrow: "Get started",
  section_title: "How do you want to start?",
  section_subtitle:
    "Pick the entry point that fits where you are — a single asset, your portfolio, or a plain-English idea.",
  pick_asset_label: "Pick an asset",
  pick_asset_desc:
    "Look up a stock, ETF, or commodity to see price history and apply a backtested strategy.",
  pick_asset_cta: "Browse Market Pulse",
  upload_portfolio_label: "Upload portfolio",
  upload_portfolio_desc:
    "Bring your holdings — we diagnose style, factor exposure, and recommend an overlay.",
  upload_portfolio_cta: "Upload holdings",
  chat_builder_label: "Chat builder",
  chat_builder_desc:
    "Describe your idea in plain English. The AI parses it into a structured backtest.",
  chat_builder_cta: "Open chat",
});

export interface EntryModePickerProps {
  /**
   * Surface identifier for analytics + the `fromTrigger` passed into
   * `startFlow`. Format: `"home"`, `"reengagement_modal"`, …
   * Used to build per-CTA triggers like `"home/upload_portfolio"`.
   */
  from: string;
  /**
   * Called when the user clicks the Chat Builder CTA. The brick is
   * surface-agnostic: on the Home page this calls `dispatchChatSeed`
   * to open the floating ChatWidget; future surfaces may navigate
   * elsewhere or open a different overlay.
   */
  onChatBuilderOpen: () => void;
  /**
   * Optional. Destination for the "Pick an asset" CTA. Defaults to
   * `/stocks` (Market Pulse, the canonical asset-picker surface today).
   * Sprint 2's Mode 1 refactor will replace the link with
   * `startFlow('one_asset_mode', …)` and drop this prop.
   */
  pickAssetHref?: Route;
}

export function EntryModePicker({
  from,
  onChatBuilderOpen,
  pickAssetHref = "/stocks" as Route,
}: EntryModePickerProps) {
  const router = useRouter();

  const sectionEyebrow = useFlowCopy("home_picker", "section_eyebrow");
  const sectionTitle = useFlowCopy("home_picker", "section_title");
  const sectionSubtitle = useFlowCopy("home_picker", "section_subtitle");

  const pickAssetLabel = useFlowCopy("home_picker", "pick_asset_label");
  const pickAssetDesc = useFlowCopy("home_picker", "pick_asset_desc");
  const pickAssetCta = useFlowCopy("home_picker", "pick_asset_cta");

  const uploadPortfolioLabel = useFlowCopy("home_picker", "upload_portfolio_label");
  const uploadPortfolioDesc = useFlowCopy("home_picker", "upload_portfolio_desc");
  const uploadPortfolioCta = useFlowCopy("home_picker", "upload_portfolio_cta");

  const chatBuilderLabel = useFlowCopy("home_picker", "chat_builder_label");
  const chatBuilderDesc = useFlowCopy("home_picker", "chat_builder_desc");
  const chatBuilderCta = useFlowCopy("home_picker", "chat_builder_cta");

  function launchPortfolioFlow() {
    startFlow("portfolio_mode", {
      initialContext: { fromTrigger: `${from}/upload_portfolio` },
    });
  }

  // Hover-based prefetch — warms the destination route on intent so the
  // perceived load on click is <300ms. Next.js <Link prefetch> handles the
  // /stocks case; button CTAs we prefetch manually via router.prefetch.
  function prefetchPortfolio() {
    router.prefetch("/flow/portfolio_mode");
  }

  return (
    <section
      aria-labelledby="entry-mode-picker-title"
      data-testid="entry-mode-picker"
      data-from={from}
      className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/[0.05] via-primary/[0.02] to-background p-8 lg:p-10"
    >
      <div className="mx-auto max-w-3xl space-y-3 text-center">
        <div className="text-xs font-semibold uppercase tracking-widest text-primary">
          {sectionEyebrow}
        </div>
        <h2 id="entry-mode-picker-title" className="font-heading text-2xl font-bold">
          {sectionTitle}
        </h2>
        <p className="text-sm text-muted-foreground">{sectionSubtitle}</p>
      </div>

      <div className="mt-8 grid gap-5 lg:grid-cols-3">
        {/* 1. Pick an asset — Next.js <Link> per Sprint-1 scope */}
        <Link
          href={pickAssetHref}
          data-testid="entry-mode-pick-asset"
          data-from={from}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-blue-200 bg-blue-50">
            <Search className="h-6 w-6 text-blue-500" />
          </div>
          <h3 className="font-heading text-lg font-semibold">{pickAssetLabel}</h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
            {pickAssetDesc}
          </p>
          <span className="mt-6 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-primary">
            {pickAssetCta}
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </Link>

        {/* 2. Upload portfolio — startFlow('portfolio_mode') per PRD-13b */}
        <button
          type="button"
          data-testid="entry-mode-upload-portfolio"
          data-from={from}
          onClick={launchPortfolioFlow}
          onMouseEnter={prefetchPortfolio}
          onFocus={prefetchPortfolio}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        >
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-emerald-200 bg-emerald-50">
            <Upload className="h-6 w-6 text-emerald-600" />
          </div>
          <h3 className="font-heading text-lg font-semibold">{uploadPortfolioLabel}</h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
            {uploadPortfolioDesc}
          </p>
          <span className="mt-6 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-primary">
            {uploadPortfolioCta}
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </button>

        {/* 3. Chat builder — surface decides how to open (Home: dispatchChatSeed) */}
        <button
          type="button"
          data-testid="entry-mode-chat-builder"
          data-from={from}
          onClick={onChatBuilderOpen}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        >
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
            <MessageSquare className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-heading text-lg font-semibold">{chatBuilderLabel}</h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
            {chatBuilderDesc}
          </p>
          <span className="mt-6 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-primary">
            {chatBuilderCta}
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </button>
      </div>
    </section>
  );
}
