"use client";

import { ArrowRight, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const IDEA_STARTERS = [
  "Buy SPY when 50-day MA crosses above 200-day MA",
  "RSI mean reversion on AAPL: buy below 30, sell above 60",
  "Rotate monthly into top 2 commodities from GLD, USO, UNG, DBA",
  "GLD trend following: buy when price above 200-day MA",
  "Equal-weight SPY, QQQ, IEF, GLD rebalanced monthly",
];

export function StrategyTeaser({ onOpenBuilder }: { onOpenBuilder: (idea?: string) => void }) {
  return (
    <section className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/[0.08] via-primary/[0.03] to-background p-10">
      <div className="mx-auto max-w-2xl space-y-6 text-center">
        <div className="flex items-center justify-center gap-2">
          <div className="relative">
            <WandSparkles className="h-5 w-5 text-primary" />
            <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" aria-hidden="true" style={{ animationDuration: "2s" }} />
          </div>
          <span className="text-xs font-semibold uppercase tracking-widest text-primary">Strategy Builder</span>
        </div>
        <h2 className="font-heading text-2xl font-bold">Describe Your Strategy, We Handle the Rest</h2>
        <p className="text-muted-foreground">
          Start from a research-backed template or describe a strategy idea in plain language.
          The builder turns it into structured backtest settings before anything runs.
        </p>

        <Button onClick={() => onOpenBuilder()} size="lg" className="gap-2 rounded-xl px-8 shadow-lg shadow-primary/10">
          Open Strategy Builder <ArrowRight className="h-4 w-4" />
        </Button>

        <div className="flex flex-wrap justify-center gap-2">
          {IDEA_STARTERS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => onOpenBuilder(chip)}
              className={cn(
                "cursor-pointer rounded-full border border-border bg-white px-4 py-2 text-sm text-muted-foreground",
                "transition-all duration-200 hover:border-primary/40 hover:bg-primary/5 hover:text-foreground hover:shadow-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              {chip}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
