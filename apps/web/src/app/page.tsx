import Link from "next/link";
import { ArrowRight, BarChart2, Bot, ShieldCheck, FileSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarketSnapshot } from "@/components/home/market-snapshot";
import { AssetSearch } from "@/components/home/asset-search";
import { StrategyTeaser } from "@/components/home/strategy-teaser";
import { researchTemplates } from "@/lib/contracts";

const HOW_IT_WORKS = [
  {
    icon: Bot,
    step: "01",
    title: "Describe Your Strategy",
    desc: "Write a trading idea in plain language. The AI parser converts it to structured strategy JSON — no coding required.",
  },
  {
    icon: BarChart2,
    step: "02",
    title: "Run a Deterministic Backtest",
    desc: "A rules-based backtesting engine runs on historical price data. No look-ahead bias, no black-box surprises.",
  },
  {
    icon: Bot,
    step: "03",
    title: "Get AI-Powered Analysis",
    desc: "An explainer breaks down performance drivers. An independent sandbox reviewer flags overfit risk and what to test next.",
  },
  {
    icon: ShieldCheck,
    step: "04",
    title: "Stress-Test for Robustness",
    desc: "Parameter sensitivity, sub-period analysis, and transaction cost stress tests reveal if the edge is durable.",
  },
];

export default function HomePage() {
  const featuredTemplates = researchTemplates.filter((t) => t.availability !== "unavailable").slice(0, 3);

  return (
    <main className="min-h-screen bg-background">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border bg-gradient-to-br from-primary/5 via-background to-background">
        <div className="mx-auto max-w-[1200px] px-6 py-20 lg:py-28">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-primary">
              <BarChart2 className="h-3.5 w-3.5" />
              Investment Strategy Research
            </div>
            <h1 className="font-heading mt-4 text-4xl font-bold leading-tight tracking-tight lg:text-5xl">
              Research Investment Strategies,{" "}
              <span className="text-primary">Backed by Data</span>
            </h1>
            <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
              Describe a trading idea in plain language. Livermore converts it to a validated backtest,
              surfaces AI-powered analysis, and applies a skeptical reviewer that pushes back on false confidence.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Button asChild size="lg" className="rounded-xl px-6">
                <Link href="/workspace">
                  Open Workspace <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-xl px-6">
                <Link href="/templates">Browse Templates</Link>
              </Button>
            </div>
            <div className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              {["No live trading", "Price-based strategies only", "Deterministic backtester", "AI explanation + review"].map((label) => (
                <span key={label} className="flex items-center gap-1.5">
                  <span className="h-1 w-1 rounded-full bg-primary/60" aria-hidden="true" />
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-[1200px] space-y-16 px-6 py-14">

        {/* Market Snapshot */}
        <MarketSnapshot />

        {/* Asset Explorer */}
        <AssetSearch />

        {/* Strategy Builder Teaser */}
        <StrategyTeaser />

        {/* How It Works */}
        <section className="space-y-8">
          <div className="text-center">
            <h2 className="font-heading text-2xl font-bold">How It Works</h2>
            <p className="mt-2 text-muted-foreground">From natural language idea to stress-tested research — in four steps</p>
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

        {/* Research Templates Preview */}
        <section className="space-y-6">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="font-heading text-2xl font-bold">Research Templates</h2>
              <p className="mt-1 text-muted-foreground">Pre-built strategy frameworks to get started instantly</p>
            </div>
            <Link href="/templates" className="text-sm font-medium text-primary transition-colors hover:underline">
              View all →
            </Link>
          </div>
          <div className="grid gap-5 sm:grid-cols-3">
            {featuredTemplates.map((tmpl) => (
              <div key={tmpl.id} className="flex flex-col rounded-xl border border-border bg-white p-5 shadow-sm transition-all duration-200 hover:border-primary/30 hover:shadow-md">
                <div className="flex items-start justify-between gap-2">
                  <div className="rounded-md border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {tmpl.category}
                  </div>
                  <FileSearch className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
                <h3 className="font-heading mt-3 text-sm font-semibold">{tmpl.name}</h3>
                <p className="mt-1.5 flex-1 text-xs leading-relaxed text-muted-foreground">{tmpl.description}</p>
                <Link href="/templates" className="mt-4 text-xs font-medium text-primary hover:underline">
                  Use this template →
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* Footer CTA */}
        <section className="rounded-2xl border border-primary/20 bg-primary/5 p-10 text-center">
          <h2 className="font-heading text-2xl font-bold">Ready to research a strategy?</h2>
          <p className="mt-3 text-muted-foreground">Open the workspace to describe, backtest, and review any price-based strategy.</p>
          <Button asChild size="lg" className="mt-6 rounded-xl px-8">
            <Link href="/workspace">
              Start Researching <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </section>

      </div>
    </main>
  );
}
