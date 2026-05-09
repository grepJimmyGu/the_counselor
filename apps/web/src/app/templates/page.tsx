"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TickerSearch } from "@/components/workspace/ticker-search";
import { UniverseInput } from "@/components/universe-input";
import { researchTemplates, type ResearchTemplate } from "@/lib/contracts";
import { useLocale } from "@/lib/locale-context";

// ── Template card ──────────────────────────────────────────────────────────────

function TemplateCard({ template }: { template: ResearchTemplate }) {
  const router = useRouter();
  const { t } = useLocale();
  const [tickers, setTickers] = useState<string[]>(template.defaultTickers);
  const tickerStr = tickers.join(",");
  const canAct = template.availability !== "unavailable" && tickers.length > 0;

  function navigateTo(path: "load" | "build", autorun = false) {
    const param = template.multiTicker ? `tickers=${tickerStr}` : `ticker=${tickerStr}`;
    const autorunStr = autorun ? "&autorun=true" : "";
    router.push(`/workspace?templateId=${template.id}&path=${path}&${param}${autorunStr}`);
  }

  const categoryColor: Record<ResearchTemplate["category"], string> = {
    Momentum: "border-blue-500/50 text-blue-400 bg-blue-500/10",
    Rotation:  "border-primary/50 text-primary bg-primary/10",
    Factor:    "border-yellow-500/50 text-yellow-400 bg-yellow-500/10",
    Carry:     "border-orange-500/50 text-orange-400 bg-orange-500/10",
  };

  return (
    <div className="flex flex-col justify-between rounded-lg border border-border bg-card/70 p-5 space-y-4">

      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Badge variant="outline" className={`text-xs font-medium ${categoryColor[template.category]}`}>
            {template.category.toUpperCase()}
          </Badge>
          {template.availability === "proxy" && (
            <Badge variant="outline" className="text-xs border-yellow-500/50 text-yellow-400">
              ETF Proxy
            </Badge>
          )}
        </div>

        <div>
          <h3 className="text-sm font-semibold">{template.name}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{template.description}</p>
        </div>

        <div className="space-y-1">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">What it tests</div>
          <p className="text-xs text-muted-foreground/80 leading-5">{template.whatItTests}</p>
        </div>

        <div className="flex gap-4 text-xs text-muted-foreground">
          <span><span className="text-foreground/60">Data</span> · {template.dataRequirement}</span>
          <span><span className="text-foreground/60">Universe</span> · {template.universeDescription}</span>
        </div>
      </div>

      {/* Ticker input or data gap */}
      <div>
        {template.availability === "unavailable" ? (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground leading-5">
            {template.dataGapReason}
          </div>
        ) : (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground font-medium">{template.tickerLabel}</div>
            {template.multiTicker ? (
              <UniverseInput
                defaultValue={template.defaultTickers}
                minTickers={template.minTickers}
                onChange={setTickers}
              />
            ) : (
              <TickerSearch
                value={tickers}
                onChange={setTickers}
                maxSymbols={1}
              />
            )}
          </div>
        )}
      </div>

      {/* Single CTA — click to load + auto-run */}
      {template.availability !== "unavailable" && (
        <div className="space-y-2">
          <Button
            size="sm"
            disabled={!canAct}
            onClick={() => navigateTo("load", true)}
            className="w-full text-sm font-semibold"
          >
            {template.availability === "proxy" ? t.templateRunBacktestProxy : t.templateRunBacktest}
          </Button>
          <button
            type="button"
            disabled={!canAct}
            onClick={() => navigateTo("build")}
            className="w-full cursor-pointer text-center text-xs text-muted-foreground transition-colors duration-200 hover:text-foreground disabled:opacity-40"
          >
            {t.templateCustomise}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function TemplatesPage() {
  const available = researchTemplates.filter((t) => t.availability !== "unavailable");
  const unavailable = researchTemplates.filter((t) => t.availability === "unavailable");

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-4 py-8 space-y-10">

        {/* Header */}
        <div className="space-y-3 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/15 text-primary hover:bg-primary/15">Livermore</Badge>
            <Badge variant="outline">Research Templates</Badge>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Research Templates</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Use a structured investment framework as the starting point for your own hypothesis.
            Each template defines a strategy type, required data, and testable rules.
            Review the rules before running a backtest.
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-full bg-primary/10 text-primary px-2.5 py-0.5 font-medium">
              {available.length} available now
            </span>
            <span>·</span>
            <span>{unavailable.length} require additional data</span>
          </div>
        </div>

        {/* Available Now */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-medium">Available Now</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              These templates can be tested immediately using price data.
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {available.map((t) => <TemplateCard key={t.id} template={t} />)}
          </div>
        </section>

        {/* Requires Additional Data */}
        {unavailable.length > 0 && (
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-medium">Requires Additional Data</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                These frameworks require data not yet available in this tool.
                Shown here so you can plan your research.
              </p>
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              {unavailable.map((t) => <TemplateCard key={t.id} template={t} />)}
            </div>
          </section>
        )}

      </div>
    </main>
  );
}
