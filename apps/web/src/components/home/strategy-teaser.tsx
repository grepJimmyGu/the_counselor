"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PROMPT_CHIPS = [
  "Buy SPY when 50-day MA crosses above 200-day MA",
  "RSI mean reversion on AAPL: buy below 30, sell above 60",
  "Rotate monthly into top 2 commodities from GLD, USO, UNG, DBA",
  "GLD trend following: buy when price above 200-day MA",
  "Equal-weight SPY, QQQ, IEF, GLD rebalanced monthly",
];

export function StrategyTeaser() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");

  function launch(text: string) {
    const p = text.trim();
    if (!p) return;
    router.push(`/workspace?prompt=${encodeURIComponent(p)}`);
  }

  return (
    <section className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/5 via-background to-background p-8">
      <div className="mx-auto max-w-2xl space-y-5 text-center">
        <div className="flex items-center justify-center gap-2">
          <WandSparkles className="h-5 w-5 text-primary" />
          <span className="text-xs font-semibold uppercase tracking-widest text-primary">Strategy Builder</span>
        </div>
        <h2 className="font-heading text-2xl font-bold">Describe Your Strategy, We Handle the Rest</h2>
        <p className="text-muted-foreground">
          Write a trading idea in plain language. The AI parser converts it to structured strategy JSON,
          runs a deterministic backtest, and delivers an AI-powered analysis.
        </p>

        {/* Prompt input */}
        <div className="relative">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); launch(prompt); } }}
            rows={3}
            placeholder="e.g. Buy SPY when the 50-day moving average crosses above the 200-day moving average…"
            className="w-full resize-none rounded-xl border border-border bg-white px-4 py-3 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all duration-200"
          />
          <Button
            onClick={() => launch(prompt)}
            disabled={!prompt.trim()}
            className="absolute bottom-3 right-3"
            size="sm"
          >
            Analyze <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Chips */}
        <div className="flex flex-wrap justify-center gap-2">
          {PROMPT_CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => launch(chip)}
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
