"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import {
  ChevronDown, ChevronUp, AlertTriangle, Lock,
  TrendingUp, ArrowRight, Info,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TickerSearch } from "@/components/workspace/ticker-search";
import { UniverseInput } from "@/components/universe-input";
import { researchTemplates, type ResearchTemplate, type StrategyJson } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { StrategyBuilderModal } from "@/components/strategy-builder/strategy-builder-modal";
import { BuilderChatDrawer } from "@/components/strategy-builder/builder-chat-drawer";

// ── Badge style maps ─────────────────────────────────────────────────────────

const CATEGORY_COLOR: Record<string, string> = {
  Momentum:     "border-blue-500/50 text-blue-500 bg-blue-500/10",
  Rotation:     "border-primary/50 text-primary bg-primary/10",
  Factor:       "border-yellow-500/50 text-yellow-600 bg-yellow-500/10",
  Carry:        "border-orange-500/50 text-orange-500 bg-orange-500/10",
  Sentiment:    "border-purple-500/50 text-purple-500 bg-purple-500/10",
  Alternative:  "border-teal-500/50 text-teal-500 bg-teal-500/10",
  Reversal:     "border-rose-500/50 text-rose-500 bg-rose-500/10",
  Arbitrage:    "border-cyan-500/50 text-cyan-600 bg-cyan-500/10",
};

const EVIDENCE_CONFIG: Record<string, { className: string; tooltip: string }> = {
  A: {
    className: "border-emerald-500/60 text-emerald-600 bg-emerald-500/10",
    tooltip: "Tier A — strong academic evidence replicated across multiple markets and time periods.",
  },
  B: {
    className: "border-amber-500/60 text-amber-600 bg-amber-500/10",
    tooltip: "Tier B — moderate evidence; mixed or inconsistent results across papers or markets.",
  },
  C: {
    className: "border-orange-500/60 text-orange-600 bg-orange-500/10",
    tooltip: "Tier C — primarily practitioner evidence; limited peer-reviewed academic support.",
  },
};

const CAPACITY_CONFIG: Record<string, string> = {
  Retail:        "border-sky-500/50 text-sky-600 bg-sky-500/10",
  Prosumer:      "border-indigo-500/50 text-indigo-500 bg-indigo-500/10",
  Institutional: "border-violet-500/50 text-violet-500 bg-violet-500/10",
  Pro:           "border-amber-500/60 text-amber-600 bg-amber-500/10",
};

const HORIZON_CONFIG: Record<string, string> = {
  Intraday:       "border-red-500/50 text-red-500 bg-red-500/10",
  Swing:          "border-teal-500/50 text-teal-500 bg-teal-500/10",
  Position:       "border-primary/50 text-primary bg-primary/10",
  "Multi-quarter": "border-purple-500/50 text-purple-500 bg-purple-500/10",
};

// ── Evidence tooltip badge ───────────────────────────────────────────────────

function EvidenceBadge({ tier }: { tier: string }) {
  const cfg = EVIDENCE_CONFIG[tier];
  if (!cfg) return null;
  return (
    <div className="group relative inline-flex">
      <Badge variant="outline" className={cn("cursor-help text-[10px] font-semibold px-1.5 py-0.5 gap-1", cfg.className)}>
        <Info className="h-2.5 w-2.5 shrink-0" />
        Evidence {tier}
      </Badge>
      <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 w-56 -translate-x-1/2 rounded-lg border border-border bg-popover px-3 py-2 text-[11px] leading-relaxed text-muted-foreground shadow-lg opacity-0 transition-opacity duration-200 group-hover:opacity-100 z-20">
        {cfg.tooltip}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
      </div>
    </div>
  );
}

// ── Default settings preview ─────────────────────────────────────────────────

function DefaultSettingsPreview({ template }: { template: ResearchTemplate }) {
  const rule = template.strategy.rules?.[0];
  if (!rule) return null;

  const fields: Record<string, unknown> = {};
  if (rule.formation_period_days) fields.formation_days = rule.formation_period_days;
  if (rule.skip_period_days)      fields.skip_days = rule.skip_period_days;
  if (rule.lookback_days)         fields.lookback_days = rule.lookback_days;
  if (rule.top_n !== undefined)   fields.top_n = rule.top_n;
  if (rule.top_pct !== undefined) fields.top_pct = rule.top_pct;
  if (rule.rank_direction)        fields.rank_direction = rule.rank_direction;
  if (rule.num_std !== undefined) fields.num_std = rule.num_std;
  if (rule.zscore_entry !== undefined) fields.zscore_entry = rule.zscore_entry;
  if (rule.zscore_exit  !== undefined) fields.zscore_exit  = rule.zscore_exit;
  if (rule.holding_window_days !== undefined) fields.holding_window = rule.holding_window_days;
  fields.rebalance = template.strategy.rebalance_frequency;

  if (Object.keys(fields).length === 0) return null;

  return (
    <div className="rounded-md border border-border/60 bg-muted/40 px-3 py-2 font-mono text-[10px] leading-relaxed">
      {Object.entries(fields).map(([k, v]) => (
        <div key={k} className="flex items-center gap-1">
          <span className="text-primary/70">{k}</span>
          <span className="text-muted-foreground/60">:</span>
          <span className="text-foreground/80">{JSON.stringify(v)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Caveats collapsible ──────────────────────────────────────────────────────

function CaveatSection({ caveats }: { caveats: string[] }) {
  const [open, setOpen] = useState(false);
  if (!caveats.length) return null;
  return (
    <div className="rounded-md border border-amber-200/60 bg-amber-50/40">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left cursor-pointer"
      >
        <AlertTriangle className="h-3 w-3 shrink-0 text-amber-500" />
        <span className="text-[10px] font-semibold text-amber-700">
          {caveats.length} caveat{caveats.length > 1 ? "s" : ""}
        </span>
        <span className="ml-auto">
          {open
            ? <ChevronUp className="h-3 w-3 text-amber-500" />
            : <ChevronDown className="h-3 w-3 text-amber-500" />}
        </span>
      </button>
      {open && (
        <ul className="border-t border-amber-200/60 px-3 py-2 space-y-1.5">
          {caveats.map((c, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[10px] text-amber-800 leading-relaxed">
              <span className="mt-0.5 shrink-0 text-amber-400">•</span>
              {c}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Template card ─────────────────────────────────────────────────────────────

function TemplateCard({
  template,
  onOpen,
  onPreviewStrategy,
}: {
  template: ResearchTemplate;
  onOpen: (template: ResearchTemplate, tickers: string[]) => void;
  onPreviewStrategy: (strategyJson: StrategyJson) => void;
}) {
  const [tickers, setTickers] = useState<string[]>(template.defaultTickers);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const canAct = template.availability !== "unavailable" && tickers.length > 0;
  const contextStrategy: StrategyJson = {
    ...template.strategy,
    strategy_name: template.name,
    universe: tickers.length ? tickers : template.defaultTickers,
  };

  return (
    <div className={cn(
      "relative flex flex-col rounded-xl border bg-card/70 p-5 space-y-4 transition-all duration-200",
      template.comingSoon
        ? "border-border/40 opacity-70"
        : "border-border shadow-sm hover:border-primary/30 hover:shadow-md",
    )}>

      {/* Coming soon overlay */}
      {template.comingSoon && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-background/65 backdrop-blur-[2px]">
          <div className="flex flex-col items-center gap-2 px-6 text-center">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background shadow-sm">
              <Lock className="h-4 w-4 text-muted-foreground" />
            </div>
            <p className="text-sm font-semibold">Coming Soon</p>
            <p className="text-[11px] text-muted-foreground leading-snug max-w-[200px]">
              {template.dataGapReason ?? "Requires additional data pipeline support."}
            </p>
          </div>
        </div>
      )}

      {/* Header badges */}
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <Badge variant="outline" className={cn("text-[10px] font-semibold shrink-0", CATEGORY_COLOR[template.category] ?? "")}>
            {template.category.toUpperCase()}
          </Badge>
          <div className="flex flex-wrap items-center gap-1.5">
            {template.evidenceTier && <EvidenceBadge tier={template.evidenceTier} />}
            {template.capacityBadge && (
              <Badge variant="outline" className={cn("text-[10px] font-semibold", CAPACITY_CONFIG[template.capacityBadge] ?? "border-border text-muted-foreground")}>
                {template.capacityBadge}
              </Badge>
            )}
            {template.horizonBadge && (
              <Badge variant="outline" className={cn("text-[10px] font-semibold", HORIZON_CONFIG[template.horizonBadge] ?? "")}>
                {template.horizonBadge}
              </Badge>
            )}
            {template.availability === "proxy" && (
              <Badge variant="outline" className="text-[10px] border-yellow-500/50 text-yellow-600">ETF Proxy</Badge>
            )}
          </div>
        </div>

        {/* Name + description */}
        <div>
          <h3 className="text-sm font-semibold leading-snug">{template.name}</h3>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{template.description}</p>
        </div>

        {/* What it captures */}
        {template.whatItCaptures && (
          <div className="space-y-0.5">
            <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60">What it captures</p>
            <p className="text-[11px] text-muted-foreground/90 leading-relaxed">{template.whatItCaptures}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
          <span><span className="text-foreground/50">Data</span> · {template.dataRequirement}</span>
          <span><span className="text-foreground/50">Universe</span> · {template.universeDescription}</span>
        </div>
      </div>

      {/* Expandable details */}
      <div>
        <button
          onClick={() => setDetailsOpen(v => !v)}
          className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          {detailsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {detailsOpen ? "Hide" : "Show"} details
        </button>
        {detailsOpen && (
          <div className="mt-3 space-y-3">
            <div className="space-y-1">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60">What it tests</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{template.whatItTests}</p>
            </div>
            <div className="space-y-1">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60">Default settings</p>
              <DefaultSettingsPreview template={template} />
            </div>
          </div>
        )}
      </div>

      {/* Caveats */}
      {template.caveats && template.caveats.length > 0 && !template.comingSoon && (
        <CaveatSection caveats={template.caveats} />
      )}

      {/* Ticker input */}
      {!template.comingSoon && (
        <div>
          {template.availability === "unavailable" ? (
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2.5 text-[11px] text-muted-foreground leading-relaxed">
              {template.dataGapReason}
            </div>
          ) : (
            <div className="space-y-1.5">
              <div className="text-[10px] text-muted-foreground font-medium">{template.tickerLabel}</div>
              {template.multiTicker ? (
                <UniverseInput defaultValue={template.defaultTickers} minTickers={template.minTickers} onChange={setTickers} />
              ) : (
                <TickerSearch value={tickers} onChange={setTickers} maxSymbols={1} />
              )}
            </div>
          )}
        </div>
      )}

      {/* CTA */}
      {template.availability !== "unavailable" && !template.comingSoon && (
        <div className="mt-auto grid gap-2">
          <Button size="sm" disabled={!canAct} onClick={() => onOpen(template, tickers)} className="w-full text-sm font-semibold">
            Build with this template <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
          </Button>
          <BuilderChatDrawer
            context={{
              source_page: "templates",
              selected_template_id: template.id,
              current_strategy_json: contextStrategy,
            }}
            onPreviewStrategy={onPreviewStrategy}
            triggerLabel="Chat with template"
            triggerSize="sm"
            triggerClassName="w-full"
          />
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TemplatesPage() {
  const [activeCategory, setActiveCategory] = useState<string>("All");
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderTemplate, setBuilderTemplate] = useState<ResearchTemplate | undefined>(undefined);
  const [builderTickers, setBuilderTickers] = useState("");
  const [builderDraft, setBuilderDraft] = useState<StrategyJson | undefined>(undefined);

  function handleOpenBuilder(template: ResearchTemplate, tickers: string[]) {
    setBuilderDraft(undefined);
    setBuilderTemplate(template);
    setBuilderTickers(tickers.join(", "));
    setBuilderOpen(true);
  }

  function openDraftStrategy(strategyJson: StrategyJson) {
    setBuilderTemplate(undefined);
    setBuilderTickers("");
    setBuilderDraft(strategyJson);
    setBuilderOpen(true);
  }

  const phaseA = researchTemplates.filter(t => t.availability !== "unavailable" && !t.comingSoon);
  const comingSoon = researchTemplates.filter(t => t.comingSoon);
  const legacyUnavailable = researchTemplates.filter(t => t.availability === "unavailable" && !t.comingSoon);

  const categories = ["All", ...Array.from(new Set(phaseA.map(t => t.category)))];
  const visible = activeCategory === "All" ? phaseA : phaseA.filter(t => t.category === activeCategory);

  const evidenceLegend = [
    { tier: "A", label: "Strong academic evidence across multiple markets." },
    { tier: "B", label: "Moderate evidence; mixed results." },
    { tier: "C", label: "Practitioner evidence only." },
  ];

  return (
    <main className="min-h-screen bg-background">
      <StrategyBuilderModal
        open={builderOpen}
        onClose={() => { setBuilderOpen(false); setBuilderTemplate(undefined); setBuilderTickers(""); setBuilderDraft(undefined); }}
        initialStrategyJson={builderDraft}
        initialTemplate={builderTemplate}
        initialTemplateTickers={builderTickers}
      />
      <div className="mx-auto max-w-6xl px-4 py-8 space-y-10 md:px-6">

        {/* Page header */}
        <div className="space-y-4 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            <Badge className="bg-primary/10 text-primary hover:bg-primary/10">Livermore Alpha</Badge>
            <Badge variant="outline">Research Templates</Badge>
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Template Gallery</h1>
            <p className="mt-2 text-sm text-muted-foreground max-w-2xl leading-relaxed">
              Pre-built strategy frameworks grounded in academic research. Each template ships
              with evidence tier ratings, capacity constraints, regime caveats, and default
              settings so you can calibrate expectations before running a backtest.
            </p>
          </div>
          <BuilderChatDrawer
            context={{ source_page: "templates" }}
            onPreviewStrategy={openDraftStrategy}
            triggerLabel="Start Builder Chat"
          />

          {/* Evidence legend strip */}
          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-muted/20 px-4 py-3">
            <span className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground">Evidence tiers</span>
            {evidenceLegend.map(({ tier, label }) => (
              <div key={tier} className="flex items-center gap-1.5">
                <Badge variant="outline" className={cn("text-[10px] font-semibold", EVIDENCE_CONFIG[tier]?.className)}>
                  {tier}
                </Badge>
                <span className="text-[10px] text-muted-foreground hidden sm:inline">{label}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span className="rounded-full bg-primary/10 text-primary px-2.5 py-0.5 font-medium">
              {phaseA.length} available now
            </span>
            <span>·</span>
            <span>{comingSoon.length} coming soon</span>
          </div>
        </div>

        {/* Category filter */}
        <div className="flex flex-wrap gap-2">
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors cursor-pointer touch-manipulation",
                activeCategory === cat
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Available now */}
        <section className="space-y-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold">Available Now</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Run immediately — all use price data the engine supports.
              </p>
            </div>
            <span className="shrink-0 rounded-full bg-primary/10 text-primary px-2.5 py-0.5 text-xs font-medium">
              {visible.length}
            </span>
          </div>
          {visible.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No templates in this category.</p>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map(t => <TemplateCard key={t.id} template={t} onOpen={handleOpenBuilder} onPreviewStrategy={openDraftStrategy} />)}
            </div>
          )}
        </section>

        {/* Coming soon (Phase B) */}
        {comingSoon.length > 0 && (
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-semibold">Coming Soon — Phase B</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Fundamental and event-driven templates pending data pipeline support.
              </p>
            </div>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {comingSoon.map(t => <TemplateCard key={t.id} template={t} onOpen={handleOpenBuilder} onPreviewStrategy={openDraftStrategy} />)}
            </div>
          </section>
        )}

        {/* Legacy unavailable */}
        {legacyUnavailable.length > 0 && (
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-semibold">Requires Additional Data</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Shown for research planning.</p>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              {legacyUnavailable.map(t => <TemplateCard key={t.id} template={t} onOpen={handleOpenBuilder} onPreviewStrategy={openDraftStrategy} />)}
            </div>
          </section>
        )}

        <div className="border-t border-border pt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-muted-foreground">
          <p>Evidence tiers reflect peer-reviewed literature as of 2025. Past evidence ≠ future performance.</p>
          <Link href={"/" as Route} className="flex items-center gap-1.5 hover:text-foreground transition-colors shrink-0">
            Back to dashboard <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

      </div>
    </main>
  );
}
