"use client";

/**
 * <EntryModePicker> — PRD-11 home-page entry-mode picker.
 *
 * Three CTAs that replace the legacy "Describe Your Strategy" teaser on
 * the Home page (and, later, the re-engagement modal that will reuse this
 * brick from the shelf):
 *
 *   1. Pick an asset    → startFlow('one_asset_mode', { fromTrigger })
 *                          (Sprint 2 / Mode 1 refactor — was a <Link> to
 *                          /stocks during Sprint 1.)
 *   2. Upload portfolio → startFlow('portfolio_mode', { fromTrigger })
 *   3. Build from scratch → startFlow('custom_build_mode', { fromTrigger })
 *                          (PRD-16 — Custom Mode composer. Was previously
 *                          a "Chat builder" tile pointing at a floating
 *                          chat widget; replaced once the composer
 *                          shipped to make it the canonical from-scratch
 *                          path. Chat widget still reachable via the
 *                          floating launcher on the Home page.)
 *
 * Lives under `lib/flows/bricks/` per the Sprint-1 architecture rule: any
 * launcher that fronts the flow runtime ships as a brick so re-engagement
 * modals can pick it off the shelf without duplicating layout / copy.
 *
 * portfolio_mode, one_asset_mode, and custom_build_mode self-register via
 * the side-effect imports below. Idempotent via the getFlow() guards
 * inside each module, so the universal /flow/[flowId] shell can also
 * import them without colliding.
 */

import { useRouter } from "next/navigation";
import { ArrowRight, Filter, Search, Upload, Wand2 } from "lucide-react";
import { startFlow } from "../runtime";
import { registerModeCopy, useFlowCopy } from "../copy";
import "../portfolio-mode";
import "../one-asset-mode";
import "../custom-build-mode";
import { INITIAL_CUSTOM_BUILD_CONTEXT } from "../custom-build-mode-context";

registerModeCopy("home_picker", {
  section_eyebrow: "Get started",
  section_title: "How do you want to start?",
  section_subtitle:
    "Pick the entry point that fits where you are — a single asset, your portfolio, or a custom strategy from scratch.",
  pick_asset_label: "Pick an asset",
  pick_asset_desc:
    "Look up a stock, ETF, or commodity to see price history and apply a backtested strategy.",
  pick_asset_cta: "Apply a strategy",
  upload_portfolio_label: "Upload portfolio",
  upload_portfolio_desc:
    "Bring your holdings — we diagnose style, factor exposure, and recommend an overlay.",
  upload_portfolio_cta: "Upload holdings",
  custom_build_label: "Build from scratch",
  custom_build_desc:
    "Combine signal primitives with AND / OR rules. Optional intraday monitoring + multi-tier exits when you're ready to run live.",
  custom_build_cta: "Open composer",
  screen_market_label: "Screen the market",
  screen_market_desc:
    "Compose a reading and watch it narrow the S&P 500 to a matched basket, ranked by backtested return.",
  screen_market_cta: "Open screener",
});

export interface EntryModePickerProps {
  /**
   * Surface identifier for analytics + the `fromTrigger` passed into
   * `startFlow`. Format: `"home"`, `"reengagement_modal"`, …
   * Used to build per-CTA triggers like `"home/upload_portfolio"`.
   */
  from: string;
}

export function EntryModePicker({
  from,
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

  const customBuildLabel = useFlowCopy("home_picker", "custom_build_label");
  const customBuildDesc = useFlowCopy("home_picker", "custom_build_desc");
  const customBuildCta = useFlowCopy("home_picker", "custom_build_cta");

  const screenMarketLabel = useFlowCopy("home_picker", "screen_market_label");
  const screenMarketDesc = useFlowCopy("home_picker", "screen_market_desc");
  const screenMarketCta = useFlowCopy("home_picker", "screen_market_cta");

  function launchOneAssetFlow() {
    startFlow("one_asset_mode", {
      initialContext: { fromTrigger: `${from}/pick_asset` },
    });
  }

  function launchPortfolioFlow() {
    startFlow("portfolio_mode", {
      initialContext: { fromTrigger: `${from}/upload_portfolio` },
    });
  }

  function launchCustomBuildFlow() {
    // Spread the mode's INITIAL_*_CONTEXT defaults — unlike one_asset_mode
    // and portfolio_mode (whose initial bricks tolerate undefined optional
    // fields), CustomBuildCanvas dereferences `context.rules` on its first
    // render. Without these defaults the brick crashes with "Cannot read
    // properties of undefined (reading 'map')" and the user sees Next.js's
    // "This page couldn't load" boundary.
    startFlow("custom_build_mode", {
      initialContext: {
        ...INITIAL_CUSTOM_BUILD_CONTEXT,
        fromTrigger: `${from}/custom_build`,
      },
    });
  }

  function launchScreenMarketFlow() {
    // PRD-23b — the SAME custom_build_mode flow, with a standing universe
    // preselected (unified mode). The size-branch routes sp500 → scan→rank.
    startFlow("custom_build_mode", {
      initialContext: {
        ...INITIAL_CUSTOM_BUILD_CONTEXT,
        universe_id: "sp500",
        fromTrigger: `${from}/screen_market`,
      },
    });
  }

  // Hover-based prefetch — warms the flow-shell route on intent so the
  // perceived load on click is <300ms.
  function prefetchOneAsset() {
    router.prefetch("/flow/one_asset_mode");
  }

  function prefetchPortfolio() {
    router.prefetch("/flow/portfolio_mode");
  }

  function prefetchCustomBuild() {
    router.prefetch("/flow/custom_build_mode");
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

      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {/* 1. Pick an asset — startFlow('one_asset_mode') per Sprint 2 */}
        <button
          type="button"
          data-testid="entry-mode-pick-asset"
          data-from={from}
          onClick={launchOneAssetFlow}
          onMouseEnter={prefetchOneAsset}
          onFocus={prefetchOneAsset}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
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
        </button>

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

        {/* 3. Build from scratch — startFlow('custom_build_mode') per PRD-16 */}
        <button
          type="button"
          data-testid="entry-mode-custom-build"
          data-from={from}
          onClick={launchCustomBuildFlow}
          onMouseEnter={prefetchCustomBuild}
          onFocus={prefetchCustomBuild}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        >
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
            <Wand2 className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-heading text-lg font-semibold">{customBuildLabel}</h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
            {customBuildDesc}
          </p>
          <span className="mt-6 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-primary">
            {customBuildCta}
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </button>

        {/* 4. Screen the market — same custom_build_mode, standing universe
            preselected (PRD-23b unified mode). */}
        <button
          type="button"
          data-testid="entry-mode-screen-market"
          data-from={from}
          onClick={launchScreenMarketFlow}
          onMouseEnter={prefetchCustomBuild}
          onFocus={prefetchCustomBuild}
          className="group flex flex-col rounded-2xl border border-border/60 bg-white/80 p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        >
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
            <Filter className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-heading text-lg font-semibold">{screenMarketLabel}</h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
            {screenMarketDesc}
          </p>
          <span className="mt-6 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-primary">
            {screenMarketCta}
            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </button>
      </div>
    </section>
  );
}
