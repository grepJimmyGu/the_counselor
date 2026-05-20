"use client";

import { ArrowRight, BarChart3, Bot, PanelRightOpen, ShieldCheck, Sparkles } from "lucide-react";

import { BuilderChatDrawer } from "@/components/strategy-builder/builder-chat-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { StrategyJson } from "@/lib/contracts";

interface ChatBuilderSectionProps {
  onOpenWizard: () => void;
  onPreviewStrategy: (strategyJson: StrategyJson) => void;
}

const EXAMPLES = [
  "Test monthly momentum on AAPL, MSFT, and NVDA",
  "Build a mean reversion strategy for QQQ",
  "Try sector rotation across XLK, XLF, XLE, and XLV",
];

const CAPABILITIES = [
  { icon: Bot, label: "Plain-English strategy drafting" },
  { icon: PanelRightOpen, label: "Preview before any backtest runs" },
  { icon: BarChart3, label: "Historical paper strategy framing" },
  { icon: ShieldCheck, label: "Research-only language and guardrails" },
];

export function ChatBuilderSection({ onOpenWizard, onPreviewStrategy }: ChatBuilderSectionProps) {
  return (
    <section className="border-b border-border bg-muted/20">
      <div className="mx-auto grid max-w-[1200px] gap-8 px-6 py-10 lg:grid-cols-[minmax(0,1fr)_440px] lg:items-center">
        <div className="space-y-6">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-primary/10 text-primary hover:bg-primary/10">Chat Builder</Badge>
              <Badge variant="outline">No account required to draft</Badge>
            </div>
            <div className="max-w-2xl space-y-2">
              <h2 className="font-heading text-2xl font-bold tracking-tight sm:text-3xl">
                Describe a strategy. Review the draft. Then decide whether to backtest.
              </h2>
              <p className="text-sm leading-relaxed text-muted-foreground sm:text-base">
                Start with a plain-language idea and Livermore turns it into a structured paper strategy draft.
                The chat builder opens the existing preview flow, so you can inspect assumptions before anything runs.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {CAPABILITIES.map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-2 text-sm text-foreground/80">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-primary">
                  <Icon className="h-4 w-4" />
                </span>
                <span>{label}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <BuilderChatDrawer
              context={{ source_page: "home" }}
              onPreviewStrategy={onPreviewStrategy}
              triggerLabel="Start Chat Builder"
              triggerSize="lg"
              triggerClassName="rounded-xl px-6"
            />
            <Button variant="outline" size="lg" className="rounded-xl px-6" onClick={onOpenWizard}>
              Open guided wizard
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-background p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Sparkles className="h-4 w-4" />
              </span>
              <div>
                <div className="text-sm font-semibold">Draft console</div>
                <div className="text-[11px] text-muted-foreground">Paper strategy only</div>
              </div>
            </div>
            <Badge variant="outline" className="text-[10px]">Preview first</Badge>
          </div>

          <div className="space-y-2">
            {EXAMPLES.map((example) => (
              <div key={example} className="rounded-lg border border-border bg-muted/25 px-3 py-2 text-xs text-muted-foreground">
                {example}
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/8 px-3 py-2 text-xs leading-relaxed text-emerald-700">
            Output: structured draft, assumptions, and a review step before historical backtesting.
          </div>
        </div>
      </div>
    </section>
  );
}
