"use client";

import { ArrowRight } from "lucide-react";

import { BuilderChatDrawer } from "@/components/strategy-builder/builder-chat-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { StrategyJson } from "@/lib/contracts";

interface ChatBuilderSectionProps {
  onOpenWizard: () => void;
  onPreviewStrategy: (strategyJson: StrategyJson) => void;
}

const EXAMPLES = [
  "Monthly momentum on AAPL, MSFT, NVDA",
  "Mean reversion strategy for QQQ",
];

export function ChatBuilderSection({ onOpenWizard, onPreviewStrategy }: ChatBuilderSectionProps) {
  return (
    <section className="border-b border-border bg-background">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5 px-6 py-8 md:flex-row md:items-center md:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="bg-primary/10 text-primary hover:bg-primary/10">Chat Builder</Badge>
            <Badge variant="outline">Guest access</Badge>
          </div>
          <div>
            <h2 className="font-heading text-2xl font-bold tracking-tight">
              Draft a backtest setup from chat.
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Describe the tickers and strategy style. Livermore prepares a backtest configuration for review in the builder.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <span key={example} className="rounded-full border border-border bg-muted/30 px-3 py-1 text-xs text-muted-foreground">
                {example}
              </span>
            ))}
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:flex-row md:flex-col lg:flex-row">
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
    </section>
  );
}
