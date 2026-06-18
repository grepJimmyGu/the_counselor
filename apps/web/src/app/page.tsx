"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart2,
  Bot,
  Newspaper,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import type { Route } from "next";
import { Button } from "@/components/ui/button";
import { MarketSnapshot } from "@/components/home/market-snapshot";
import { HomeHeroSearch } from "@/components/home/home-hero-search";
import { HomeMarketStrip } from "@/components/home/home-market-strip";
import { HomeFocusSections } from "@/components/home/home-focus-sections";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";
import { StrategyBuilderModal } from "@/components/strategy-builder/strategy-builder-modal";
import { ChatWidget } from "@/components/ChatWidget";
import { NotificationBanner } from "@/components/notifications/notification-banner";

// ── How it works — timeline steps ──────────────────────────────────────────────

const HOW_IT_WORKS = [
  {
    icon: BarChart2,
    step: "01",
    title: "Screen with Market Pulse",
    desc: "Track sector flow, evaluate Health/Valuation/Trend, spot macro shifts.",
  },
  {
    icon: Newspaper,
    step: "02",
    title: "Read the News Signals",
    desc: "AI extracts catalyst type, sentiment trend, and signal quality from recent news.",
  },
  {
    icon: Users,
    step: "03",
    title: "Discover & Fork Strategies",
    desc: "Browse community strategies and fork ones that match your thesis.",
  },
  {
    icon: Bot,
    step: "04",
    title: "Build & Stress-Test",
    desc: "Choose a quant template or describe an idea in plain English. Run a deterministic backtest.",
  },
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderTemplate, setBuilderTemplate] = useState<ResearchTemplate | undefined>(undefined);
  const [builderIdea, setBuilderIdea] = useState<string | undefined>(undefined);

  const featuredTemplates = researchTemplates
    .filter((t) => t.availability !== "unavailable")
    .slice(0, 3);

  function openBuilder(idea?: string) {
    setBuilderTemplate(undefined);
    setBuilderIdea(idea);
    setBuilderOpen(true);
  }

  function openTemplate(template: ResearchTemplate) {
    setBuilderIdea(undefined);
    setBuilderTemplate(template);
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
          <div className="mx-auto max-w-3xl text-center">
            {/* Pill badge */}
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-primary">
              <TrendingUp className="h-3.5 w-3.5" />
              Investment Research Platform
            </div>

            <h1 className="font-heading text-5xl font-bold leading-[1.1] tracking-tight lg:text-6xl">
              Discover.{" "}
              <span className="text-primary">Build.</span>
              <br />
              Track.
            </h1>

            <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
              Discover what&rsquo;s moving today, build and backtest a rules-based
              strategy, then track it over time. No live trading, no AI
              recommendations — just data-driven tools.
            </p>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg" className="rounded-xl px-6 shadow-lg shadow-primary/10">
                <Link href={"/stocks" as Route}>
                  Market Pulse <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-xl px-6">
                <Link href={"/community" as Route}>
                  <Users className="mr-2 h-4 w-4" />
                  Community
                </Link>
              </Button>
              <Button variant="outline" size="lg" className="rounded-xl px-6" onClick={() => openBuilder()}>
                <Zap className="mr-2 h-4 w-4" />
                Strategy Builder
              </Button>
            </div>

            {/* PRD-24a §3.3 — hero lookup with in-place stock preview */}
            <div className="mt-8">
              <HomeHeroSearch />
            </div>

            {/* Trust chips — compact inline row */}
            <div className="mt-8 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
              {[
                "No live trading",
                "End-of-day prices",
                "Deterministic backtester",
                "AI research tools",
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
        <MarketSnapshot />

        {/* ── PRD-19 Step 5: in-app notification banner (signed-in users only) ── */}
        <NotificationBanner />

        {/* ── PRD-24a §3.5–3.7 — the 3-focus reorganization (Discover · Build ·
            Your Livermore). Replaces the EntryModePicker + research pillars. ── */}
        <HomeFocusSections />

        {/* ── How It Works — visual timeline ─────────────────────────────── */}
        <section className="space-y-8">
          <div className="text-center">
            <h2 className="font-heading text-2xl font-bold">How It Works</h2>
            <p className="mt-2 text-muted-foreground">From discovery to stress-tested strategy — four steps</p>
          </div>

          {/* Desktop: horizontal timeline */}
          <div className="relative hidden gap-0 sm:grid sm:grid-cols-4">
            {/* Connecting line */}
            <div className="absolute left-[12.5%] right-[12.5%] top-8 h-px bg-border" aria-hidden="true" />

            {HOW_IT_WORKS.map(({ icon: Icon, step, title, desc }) => (
              <div key={step} className="relative flex flex-col items-center text-center">
                {/* Step circle */}
                <div className="relative z-10 flex h-16 w-16 items-center justify-center rounded-2xl border-2 border-border bg-white shadow-sm">
                  <Icon className="h-6 w-6 text-primary" />
                </div>
                <span className="mt-3 font-mono text-xs font-bold text-primary/30">{step}</span>
                <h3 className="mt-1 font-heading text-sm font-semibold">{title}</h3>
                <p className="mt-1 max-w-[180px] text-xs leading-relaxed text-muted-foreground">{desc}</p>
              </div>
            ))}
          </div>

          {/* Mobile: vertical stack */}
          <div className="flex flex-col gap-0 sm:hidden">
            {HOW_IT_WORKS.map(({ icon: Icon, step, title, desc }, i) => (
              <div key={step} className="flex gap-4">
                {/* Left rail */}
                <div className="flex flex-col items-center">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-border bg-white shadow-sm">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  {i < HOW_IT_WORKS.length - 1 && (
                    <div className="mt-1 w-px flex-1 bg-border" aria-hidden="true" />
                  )}
                </div>
                {/* Content */}
                <div className="pb-8">
                  <span className="font-mono text-xs font-bold text-primary/30">{step}</span>
                  <h3 className="font-heading text-sm font-semibold">{title}</h3>
                  <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

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
