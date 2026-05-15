"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart2,
  Bot,
  FileSearch,
  Newspaper,
  Search,
  ShieldCheck,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { Route } from "next";
import { Button } from "@/components/ui/button";
import { MarketSnapshot } from "@/components/home/market-snapshot";
import { AssetSearch } from "@/components/home/asset-search";
import { StrategyTeaser } from "@/components/home/strategy-teaser";
import { CapabilityGlossary } from "@/components/home/capability-glossary";
import { researchTemplates } from "@/lib/contracts";

// ── Three research pillars ────────────────────────────────────────────────────

const PILLARS = [
  {
    icon: Search,
    label: "Market Pulse & Stock Analysis",
    color: "text-blue-500",
    bg: "bg-blue-50 border-blue-200",
    description:
      "Track sector capital flow using Chaikin Money Flow, monitor index performance, and drill into any stock for a 3-question evaluation: Health, Valuation, and Trend.",
    cta: "Market Pulse",
    href: "/stocks",
    features: ["Sector capital flow (CMF)", "Health · Valuation · Trend scores", "Business model + market position"],
  },
  {
    icon: Newspaper,
    label: "News & Sentiment",
    color: "text-purple-500",
    bg: "bg-purple-50 border-purple-200",
    description:
      "AI-powered news catalyst analysis with 7 pre-built research toolkits. Identify stocks with meaningful catalysts, rising attention, or headline risks before they move.",
    cta: "View Sentiment Hub",
    href: "/sentiment",
    features: ["Catalyst type & materiality", "9-score signal framework", "7 pre-built toolkits"],
  },
  {
    icon: Bot,
    label: "Strategy Builder",
    color: "text-primary",
    bg: "bg-primary/5 border-primary/20",
    description:
      "Describe a trading idea in plain language. The AI parser converts it to a validated backtest, then an independent reviewer pushes back on overfit risk.",
    cta: "Open Workspace",
    href: "/workspace",
    features: ["Natural language → strategy JSON", "Deterministic backtester", "AI explainer + sandbox review"],
  },
];

// ── How it works ─────────────────────────────────────────────────────────────

const HOW_IT_WORKS = [
  {
    icon: Search,
    step: "01",
    title: "Screen & Discover",
    desc: "Track sector capital flow, monitor index performance, and evaluate any stock across Health, Valuation, and Trend — plus commodities with physical market signals.",
  },
  {
    icon: BarChart2,
    step: "02",
    title: "Analyze the Fundamentals",
    desc: "Drill into any ticker for financial health scores — revenue growth, margins, cash flow, balance sheet strength, and valuation risk.",
  },
  {
    icon: Newspaper,
    step: "03",
    title: "Read the News Signals",
    desc: "AI extracts catalyst type, sentiment trend, and signal quality from recent news. See what's driving attention and whether it's material.",
  },
  {
    icon: Bot,
    step: "04",
    title: "Build & Stress-Test a Strategy",
    desc: "Describe a rules-based strategy in plain English. Run a deterministic backtest, then apply parameter sensitivity and sub-period stress tests.",
  },
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function HomePage() {
  const featuredTemplates = researchTemplates
    .filter((t) => t.availability !== "unavailable")
    .slice(0, 3);

  return (
    <main className="min-h-screen bg-background">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-border bg-gradient-to-br from-primary/5 via-background to-background">
        <div className="mx-auto max-w-[1200px] px-6 py-20 lg:py-28">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-primary">
              <TrendingUp className="h-3.5 w-3.5" />
              Investment Research Platform
            </div>
            <h1 className="font-heading mt-4 text-4xl font-bold leading-tight tracking-tight lg:text-5xl">
              Market Pulse.{" "}
              <span className="text-primary">Read the Signals.</span>
              <br />
              Build Strategies.
            </h1>
            <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
              Three research lenses in one platform — fundamental analysis, news &amp; sentiment signals,
              and rules-based strategy backtesting. No live trading, no AI recommendations.
              Just data-driven research tools.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg" className="rounded-xl px-6">
                <Link href={"/stocks" as Route}>
                  Market Pulse <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-xl px-6">
                <Link href={"/sentiment" as Route}>
                  <Newspaper className="mr-2 h-4 w-4" />
                  News & Sentiment
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-xl px-6">
                <Link href={"/workspace" as Route}>
                  Strategy Builder
                </Link>
              </Button>
            </div>
            <div className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
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
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1200px] space-y-12 px-6 py-10">

        {/* ── Three Research Pillars ────────────────────────────────────── */}
        <section className="space-y-6">
          <div className="text-center">
            <h2 className="font-heading text-2xl font-bold">Three Research Lenses</h2>
            <p className="mt-2 text-muted-foreground">Each lens answers a different question before you invest</p>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            {PILLARS.map(({ icon: Icon, label, color, bg, description, cta, href, features }) => (
              <div
                key={label}
                className="flex flex-col rounded-xl border border-border bg-white p-6 shadow-sm transition-all duration-200 hover:border-primary/30 hover:shadow-md"
              >
                <div className={`mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg border ${bg}`}>
                  <Icon className={`h-5 w-5 ${color}`} />
                </div>
                <h3 className="font-heading text-base font-semibold">{label}</h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
                <ul className="mt-4 space-y-1.5">
                  {features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color.replace("text-", "bg-")}`} />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button asChild variant="outline" size="sm" className="mt-5">
                  <Link href={href as Route}>
                    {cta} <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Link>
                </Button>
              </div>
            ))}
          </div>
        </section>

        {/* ── Market Snapshot ───────────────────────────────────────────── */}
        <MarketSnapshot />

        {/* ── Asset Explorer ────────────────────────────────────────────── */}
        <AssetSearch />

        {/* ── Strategy Builder Teaser ───────────────────────────────────── */}
        <StrategyTeaser />

        {/* ── Capability Glossary ───────────────────────────────────────── */}
        <CapabilityGlossary />

        {/* ── How It Works ──────────────────────────────────────────────── */}
        <section className="space-y-8">
          <div className="text-center">
            <h2 className="font-heading text-2xl font-bold">How It Works</h2>
            <p className="mt-2 text-muted-foreground">From discovery to stress-tested strategy — four steps</p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map(({ icon: Icon, step, title, desc }) => (
              <div key={step} className="rounded-xl border border-border bg-white p-5 shadow-sm">
                <div className="mb-3 flex items-center gap-3">
                  <span className="font-mono text-3xl font-bold text-primary/20">{step}</span>
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/8">
                    <Icon className="h-4 w-4 text-primary" />
                  </div>
                </div>
                <h3 className="font-heading text-sm font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Research Templates Preview ────────────────────────────────── */}
        <section className="space-y-6">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="font-heading text-2xl font-bold">Strategy Templates</h2>
              <p className="mt-1 text-muted-foreground">Pre-built frameworks — click to run instantly</p>
            </div>
            <Link
              href={"/templates" as Route}
              className="text-sm font-medium text-primary transition-colors hover:underline"
            >
              View all →
            </Link>
          </div>
          <div className="grid gap-5 sm:grid-cols-3">
            {featuredTemplates.map((tmpl) => (
              <div
                key={tmpl.id}
                className="flex flex-col rounded-xl border border-border bg-white p-5 shadow-sm transition-all duration-200 hover:border-primary/30 hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="rounded-md border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {tmpl.category}
                  </div>
                  <FileSearch className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
                <h3 className="font-heading mt-3 text-sm font-semibold">{tmpl.name}</h3>
                <p className="mt-1.5 flex-1 text-xs leading-relaxed text-muted-foreground">{tmpl.description}</p>
                <Link
                  href={"/templates" as Route}
                  className="mt-4 text-xs font-medium text-primary hover:underline"
                >
                  Use this template →
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* ── Footer CTA ────────────────────────────────────────────────── */}
        <section className="rounded-2xl border border-primary/20 bg-primary/5 p-10">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-heading text-2xl font-bold">Ready to start researching?</h2>
            <p className="mt-3 text-muted-foreground">
              Screen for opportunities, analyze the fundamentals, read the news signals, then backtest a strategy.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg" className="rounded-xl px-8">
                <Link href={"/stocks" as Route}>
                  Market Pulse <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-xl px-6">
                <Link href={"/sentiment" as Route}>
                  <Zap className="mr-2 h-4 w-4" />
                  Sentiment Hub
                </Link>
              </Button>
            </div>
          </div>
        </section>

      </div>
    </main>
  );
}
