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
    <section className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/5 via-background to-background p-8">
      <div className="mx-auto max-w-2xl space-y-5 text-center">
        <div className="flex items-center justify-center gap-2">
          <WandSparkles className="h-5 w-5 text-primary" />
          <span className="text-xs font-semibold uppercase tracking-widest text-primary">Strategy Builder</span>
        </div>
        <h2 className="font-heading text-2xl font-bold">Describe Your Strategy, We Handle the Rest</h2>
        <p className="text-muted-foreground">
          Start from a research-backed template or describe a strategy idea in plain language.
          The builder turns it into structured backtest settings before anything runs.
        </p>

        <Button onClick={() => onOpenBuilder()} className="gap-2">
          Open Strategy Builder <ArrowRight className="h-4 w-4" />
        </Button>

        <div className="flex flex-wrap justify-center gap-2">
          {IDEA_STARTERS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => onOpenBuilder(chip)}
              className={cn(
                "cursor-pointer rounded-full border border-border bg-white px-3 py-1.5 text-xs text-muted-foreground",
                "transition-colors duration-200 hover:border-primary/40 hover:bg-primary/5 hover:text-foreground",
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
