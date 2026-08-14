"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
} from "lucide-react";
import type { Route } from "next";
import { Button } from "@/components/ui/button";
import { HomeMarketPulseBlock } from "@/components/home/home-market-pulse-block";
import { HomeCuratedScreens } from "@/components/home/home-curated-screens";
import { HomeQuantStrategies } from "@/components/home/home-quant-strategies";
import { MarketCatalysts } from "@/components/home/market-catalysts";
import { SmartSearchBox } from "@/components/search/smart-search-box";
import { HomeMarketStrip } from "@/components/home/home-market-strip";
import { HomeFocusSections } from "@/components/home/home-focus-sections";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";
import { StrategyBuilderModal } from "@/components/strategy-builder/strategy-builder-modal";
import { ChatWidget } from "@/components/ChatWidget";
import { NotificationBanner } from "@/components/notifications/notification-banner";

// ── How it works — timeline steps ──────────────────────────────────────────────

// ── Main page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderTemplate, setBuilderTemplate] = useState<ResearchTemplate | undefined>(undefined);
  const [builderIdea, setBuilderIdea] = useState<string | undefined>(undefined);

  const featuredTemplates = researchTemplates
    .filter((t) => t.availability !== "unavailable")
    .slice(0, 3);


  function openTemplate(template: ResearchTemplate) {
    setBuilderIdea(undefined);
    setBuilderTemplate(template);
    setBuilderOpen(true);
  }

  function openBuilder() {
    setBuilderIdea(undefined);
    setBuilderTemplate(undefined);
    setBuilderOpen(true);
  }

  return (
    <main className="min-h-screen bg-background">
      <StrategyBuilderModal
        open={builderOpen}
        onClose={() => { setBuilderOpen(false); setBuilderTemplate(undefined); setBuilderIdea(undefined); }}
        initialTemplate={builderTemplate}
        initialIdea={builderIdea}
      />

      {/* Floating chat widget — mounted on Home as the always-on
          assistant. The PRD-11 picker's third tile is now Custom
          Build (PRD-16), but the chat is still reachable via the
          floating launcher; surfaces like the stock page also
          subscribe to `dispatchChatSeed`. */}
      <ChatWidget />

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-border bg-gradient-to-br from-primary/10 via-primary/5 to-background">
        {/* Decorative grid pattern */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(circle, var(--color-primary) 1px, transparent 1px)`,
            backgroundSize: "24px 24px",
          }}
          aria-hidden="true"
        />

        <div className="relative mx-auto max-w-[1200px] px-6 pb-20 pt-24 lg:pb-28 lg:pt-32">
          {/* Wide enough for the box to breathe — the six Conditions columns
              and the company-preview drawer both want ~1080px. The prose
              children keep their own narrower measures (h1 is centered, the
              subhead is max-w-xl), so only the box actually uses the width. */}
          <div className="mx-auto max-w-[1080px] text-center">
            {/* PRD-29 — the box IS the product (問財 pattern), so it leads.
                Removed from above it: the "Investment Research Platform" badge,
                the "Discover. Build. Track." headline, the marketing paragraph,
                and three CTA buttons — all three of which (Market Pulse,
                Community, Strategy Builder) are already in the top nav, so
                nothing became unreachable. Home now offers a query, it doesn't
                advertise features. */}
            <h1 className="font-heading text-3xl font-bold tracking-tight lg:text-4xl">
              Screen the US market
            </h1>
            <p className="mx-auto mt-3 max-w-xl text-base text-muted-foreground">
              A ticker, a company, or a screen — type it.
            </p>

            <div className="mt-6">
              <SmartSearchBox />
            </div>

            {/* Positioning, not marketing: the research/tool framing is a
                stated product requirement, kept to one compact line. */}
            <div className="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
              {[
                "No live trading",
                "End-of-day prices",
                "Research tool, not advice",
              ].map((label) => (
                <span key={label} className="flex items-center gap-1.5">
                  <span className="h-1 w-1 rounded-full bg-primary/60" aria-hidden="true" />
                  {label}
                </span>
              ))}
            </div>

            {/* PRD-24a §0.3 — compact Market Pulse (major indices) for the hero */}
            <HomeMarketStrip />
          </div>
        </div>
      </section>

      {/* ── Page body ────────────────────────────────────────────────────── */}
      <div className="mx-auto max-w-[1200px] space-y-16 px-6 py-12">

        {/* ── Market Snapshot ────────────────────────────────────────────── */}
        {/* PRD-29 below the fold — every block is a query to run or a result
            to adopt (the 問財 bar). Replaces <MarketSnapshot>, which showed a
            hardcoded SPY/QQQ/GLD/NVDA watchlist: four tickers nobody chose,
            answering a question nobody asked. */}
        {/* A true 2×2: Moving today · Hot Market Picks / Quant Rules · Catalysts.
            `items-start` is gone — it was there because "Traders ask" was too
            short to fill a cell, and that block is now the top section of Hot
            Market Picks rather than a box of its own. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <HomeMarketPulseBlock />
          <HomeCuratedScreens />
          {/* Block 4 now fills the second cell, so block 3 no longer spans the
              row — the four blocks sit as a 2×2 grid. */}
          <HomeQuantStrategies
            onOpenTemplate={openTemplate}
            onBuildFromScratch={openBuilder}
          />
          <MarketCatalysts />
        </div>

        {/* ── PRD-19 Step 5: in-app notification banner (signed-in users only) ── */}
        <NotificationBanner />

        {/* ── PRD-24a §3.5–3.7 — the 3-focus reorganization (Discover · Build ·
            Your Livermore). Replaces the EntryModePicker + research pillars. ── */}
        <HomeFocusSections />

        {/* ── Templates — compact row ────────────────────────────────────── */}
        <section className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-muted/30 px-6 py-4">
          <span className="text-sm font-semibold text-foreground">Popular templates:</span>
          {featuredTemplates.map((tmpl) => (
            <button
              key={tmpl.id}
              type="button"
              onClick={() => openTemplate(tmpl)}
              className="cursor-pointer rounded-full border border-border bg-white px-3 py-1.5 text-xs font-medium text-foreground transition-colors duration-200 hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
            >
              {tmpl.name}
            </button>
          ))}
          <Link
            href={"/templates" as Route}
            className="ml-auto text-xs font-medium text-primary transition-colors hover:underline"
          >
            View all →
          </Link>
        </section>

        {/* ── Bottom CTA ─────────────────────────────────────────────────── */}
        <section className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/5 to-primary/[0.02] p-10">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-heading text-2xl font-bold">Ready to start researching?</h2>
            <p className="mt-3 text-muted-foreground">
              Screen the market, discover community strategies, then build and backtest your own.
            </p>
            <div className="mt-6 flex items-center justify-center gap-4">
              <Button asChild size="lg" className="rounded-xl px-8 shadow-lg shadow-primary/10">
                <Link href={"/stocks" as Route}>
                  Open Market Pulse <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Link
                href={"/community" as Route}
                className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                Browse Community →
              </Link>
            </div>
          </div>
        </section>

      </div>
    </main>
  );
}
