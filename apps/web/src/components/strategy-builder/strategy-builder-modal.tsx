"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, ArrowRight, Check, ChevronRight, Lock,
  Pencil, Play, Search, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StrategyBriefCard } from "./strategy-brief-card";
import {
  researchTemplates,
  type ResearchTemplate,
  type StrategyJson,
  type RebalanceFrequency,
} from "@/lib/contracts";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type Step =
  | "launch"
  | "template-pick"
  | "template-brief"
  | "template-universe"
  | "custom-1" | "custom-2" | "custom-3" | "custom-4" | "custom-5"
  | "preview";

interface CustomConfig {
  universe: string;          // "sp500" | "nasdaq100" | "russell1000" | "custom" | "skip"
  customTickers: string;     // raw comma-separated input
  selectedTemplate: ResearchTemplate | null;
  maxPositionPct: number;
  stopLossEnabled: boolean;
  stopLossPct: number;
  holdPeriod: RebalanceFrequency;
  minAdv: number;
  dateRange: "3Y" | "5Y" | "10Y";
  capital: number;
  costBps: number;
}

const DEFAULT_CUSTOM: CustomConfig = {
  universe: "sp500",
  customTickers: "",
  selectedTemplate: null,
  maxPositionPct: 5,
  stopLossEnabled: false,
  stopLossPct: 8,
  holdPeriod: "monthly",
  minAdv: 5000000,
  dateRange: "5Y",
  capital: 100000,
  costBps: 10,
};

const UNIVERSE_DEFAULTS: Record<string, string[]> = {
  sp500:      ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
  nasdaq100:  ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","COST","NFLX"],
  russell1000:["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA","BAC","WMT","LLY","KO","PEP"],
  commodities:["GLD","SLV","USO","UNG","DBA","DBC"],
};

// ── Keyword-based template matching for custom mode B2 ────────────────────────

const ARCHETYPE_KEYWORDS: Array<{ patterns: RegExp[]; ids: string[] }> = [
  { patterns: [/momentum|trend|going up|rising|outperform|winner|breakout/i],           ids: ["cross-sectional-momentum-12-1","time-series-momentum","dual-momentum"] },
  { patterns: [/reversal|oversold|bounce|dip|revert|mean reversion|contrarian/i],        ids: ["bollinger-mean-reversion","short-term-reversal"] },
  { patterns: [/sector|rotate|rotation|cycle|ETF|asset class/i],                         ids: ["sector-rotation-spdr","etf-rotation","time-series-momentum"] },
  { patterns: [/pairs|spread|cointegr|relative|two stock|correlated/i],                  ids: ["pairs-trading-long-only"] },
  { patterns: [/low.?vol|stable|defensive|lower risk|less risk|min.?var/i],               ids: ["low-volatility","time-series-momentum"] },
];

function matchTemplates(idea: string): ResearchTemplate[] {
  for (const { patterns, ids } of ARCHETYPE_KEYWORDS) {
    if (patterns.some(p => p.test(idea))) {
      return ids
        .map(id => researchTemplates.find(t => t.id === id))
        .filter((t): t is ResearchTemplate => !!t && t.availability === "ready");
    }
  }
  // Default: top 3 by-evidence ready templates
  return researchTemplates
    .filter(t => t.availability === "ready" && t.evidenceTier === "A")
    .slice(0, 3);
}

// ── Date range helpers ────────────────────────────────────────────────────────

function dateRangeToStartDate(range: "3Y" | "5Y" | "10Y"): string {
  const now = new Date();
  const years = range === "3Y" ? 3 : range === "10Y" ? 10 : 5;
  return new Date(now.getFullYear() - years, now.getMonth(), now.getDate())
    .toISOString().split("T")[0];
}

const today = new Date().toISOString().split("T")[0];

// ── Build final StrategyJson ──────────────────────────────────────────────────

function buildStrategyFromTemplate(
  template: ResearchTemplate,
  tickers: string[],
  dateRange: "3Y" | "5Y" | "10Y",
  strategyName: string,
): StrategyJson {
  return {
    ...template.strategy,
    strategy_name: strategyName,
    universe: tickers.length > 0 ? tickers : template.defaultTickers,
    start_date: dateRangeToStartDate(dateRange),
    end_date: today,
  };
}

function buildStrategyFromCustom(config: CustomConfig, strategyName: string): StrategyJson | null {
  const tmpl = config.selectedTemplate;
  if (!tmpl) return null;

  const rawTickers =
    config.universe === "custom"
      ? config.customTickers.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
      : UNIVERSE_DEFAULTS[config.universe] ?? tmpl.defaultTickers;

  const riskMgmt = config.stopLossEnabled
    ? { stop_loss_pct: config.stopLossPct / 100 }
    : {};

  return {
    ...tmpl.strategy,
    strategy_name: strategyName,
    universe: rawTickers,
    start_date: dateRangeToStartDate(config.dateRange),
    end_date: today,
    rebalance_frequency: config.holdPeriod,
    initial_capital: config.capital,
    transaction_cost_bps: config.costBps,
    slippage_bps: config.costBps,
    position_sizing: {
      ...tmpl.strategy.position_sizing,
      max_positions: Math.max(1, Math.floor(100 / config.maxPositionPct)),
    },
    risk_management: riskMgmt,
  };
}

// ── Category colours ──────────────────────────────────────────────────────────

const CAT_COLOR: Record<string, string> = {
  Momentum: "border-blue-500/50 text-blue-600 bg-blue-500/10",
  Rotation:  "border-primary/50 text-primary bg-primary/10",
  Factor:    "border-yellow-500/50 text-yellow-600 bg-yellow-500/10",
  Reversal:  "border-rose-500/50 text-rose-600 bg-rose-500/10",
  Arbitrage: "border-cyan-500/50 text-cyan-600 bg-cyan-500/10",
  Carry:     "border-orange-500/50 text-orange-600 bg-orange-500/10",
  Sentiment: "border-purple-500/50 text-purple-600 bg-purple-500/10",
  Alternative:"border-teal-500/50 text-teal-600 bg-teal-500/10",
};

const EVIDENCE_DOT: Record<string, string> = { A: "bg-emerald-500", B: "bg-amber-500", C: "bg-orange-500" };

// ── Sub-components ────────────────────────────────────────────────────────────

function StepDot({ active, done }: { active: boolean; done: boolean }) {
  return (
    <span className={cn(
      "flex h-2 w-2 rounded-full transition-all duration-300",
      done ? "bg-primary" : active ? "bg-primary scale-125" : "bg-border",
    )} />
  );
}

function NumberInput({ label, value, onChange, min, max, step = 1, suffix = "" }: {
  label: string; value: number; onChange: (v: number) => void;
  min: number; max: number; step?: number; suffix?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <div className="flex items-center gap-2">
        <Input
          type="number" min={min} max={max} step={step}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="h-9 w-28 text-sm font-mono"
        />
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface StrategyBuilderModalProps {
  open: boolean;
  onClose: () => void;
  initialTemplate?: ResearchTemplate;
}

export function StrategyBuilderModal({ open, onClose, initialTemplate }: StrategyBuilderModalProps) {
  const router = useRouter();

  // ── State ──────────────────────────────────────────────────────────────────
  const [step, setStep] = useState<Step>(initialTemplate ? "template-brief" : "launch");
  const [selectedTemplate, setSelectedTemplate] = useState<ResearchTemplate | null>(initialTemplate ?? null);
  const [templateTickers, setTemplateTickers] = useState<string>(
    initialTemplate?.defaultTickers.join(", ") ?? ""
  );
  const [templateDateRange, setTemplateDateRange] = useState<"3Y" | "5Y" | "10Y">("5Y");
  const [customIdeaText, setCustomIdeaText] = useState("");
  const [customCandidates, setCustomCandidates] = useState<ResearchTemplate[]>([]);
  const [customConfig, setCustomConfig] = useState<CustomConfig>(DEFAULT_CUSTOM);
  const [strategyName, setStrategyName] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Reset when opened
  useEffect(() => {
    if (open) {
      if (initialTemplate) {
        setStep("template-brief");
        setSelectedTemplate(initialTemplate);
        setTemplateTickers(initialTemplate.defaultTickers.join(", "));
      } else {
        setStep("launch");
        setSelectedTemplate(null);
        setTemplateTickers("");
        setCustomIdeaText("");
        setCustomConfig(DEFAULT_CUSTOM);
      }
      setTemplateDateRange("5Y");
      setStrategyName("");
      setCategoryFilter("All");
      setSearchQuery("");
    }
  }, [open, initialTemplate]);

  // Auto-focus name input when editing
  useEffect(() => {
    if (editingName) nameInputRef.current?.focus();
  }, [editingName]);

  if (!open) return null;

  // ── Derived values ─────────────────────────────────────────────────────────
  const readyTemplates = researchTemplates.filter(t => t.availability === "ready");
  const categories = ["All", ...Array.from(new Set(readyTemplates.map(t => t.category)))];

  const filteredTemplates = readyTemplates.filter(t => {
    if (categoryFilter !== "All" && t.category !== categoryFilter) return false;
    if (searchQuery && !t.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
        !t.description.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  function autoName(tmpl: ResearchTemplate, tickers: string): string {
    const tickerList = tickers.split(",").map(s => s.trim()).filter(Boolean);
    const suffix = tickerList.length > 0
      ? tickerList.length <= 3 ? tickerList.join(", ") : `${tickerList.slice(0, 2).join(", ")} +${tickerList.length - 2}`
      : tmpl.defaultTickers.slice(0, 2).join(", ");
    return `${tmpl.name} — ${suffix}`;
  }

  function resolvedTickers(): string[] {
    return templateTickers.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
  }

  // ── Navigation helpers ─────────────────────────────────────────────────────
  function goBack() {
    const prev: Partial<Record<Step, Step>> = {
      "template-pick": "launch",
      "template-brief": "template-pick",
      "template-universe": "template-brief",
      "custom-1": "launch",
      "custom-2": "custom-1",
      "custom-3": "custom-2",
      "custom-4": "custom-3",
      "custom-5": "custom-4",
      "preview": step === "template-universe" ? "template-universe" : "custom-5",
    };
    // If we opened with an initialTemplate, back from brief → close
    if (step === "template-brief" && initialTemplate) { onClose(); return; }
    const prevStep = prev[step];
    if (prevStep) setStep(prevStep);
  }

  function handleSelectTemplate(tmpl: ResearchTemplate) {
    setSelectedTemplate(tmpl);
    setTemplateTickers(tmpl.defaultTickers.join(", "));
    setStep("template-brief");
  }

  function handleBriefContinue() {
    setStep("template-universe");
  }

  function handleUniverseContinue() {
    const name = autoName(selectedTemplate!, templateTickers);
    setStrategyName(name);
    setStep("preview");
  }

  function handleCustomIdeaSubmit() {
    const candidates = matchTemplates(customIdeaText);
    setCustomCandidates(candidates.length ? candidates : readyTemplates.slice(0, 3));
    setStep("custom-2");
  }

  function handleCustomTemplateSelect(tmpl: ResearchTemplate) {
    setCustomConfig(c => ({ ...c, selectedTemplate: tmpl }));
    setStep("custom-3");
  }

  function handleCustomPreview() {
    const tmpl = customConfig.selectedTemplate;
    if (!tmpl) return;
    const name = `${tmpl.name} — Custom`;
    setStrategyName(name);
    setStep("preview");
  }

  function handleRunBacktest() {
    let strategyJson: StrategyJson | null = null;

    if (selectedTemplate && (step === "preview" || true)) {
      // Determine if we came from template or custom path
      const isCustom = customConfig.selectedTemplate !== null && selectedTemplate === null;
      if (isCustom) {
        strategyJson = buildStrategyFromCustom({ ...customConfig }, strategyName);
      } else if (selectedTemplate) {
        strategyJson = buildStrategyFromTemplate(selectedTemplate, resolvedTickers(), templateDateRange, strategyName);
      }
    }

    // Try custom path
    if (!strategyJson && customConfig.selectedTemplate) {
      strategyJson = buildStrategyFromCustom(customConfig, strategyName);
    }

    if (!strategyJson) return;

    strategyJson.strategy_name = strategyName;
    sessionStorage.setItem("pendingStrategy", JSON.stringify(strategyJson));
    onClose();
    router.push("/workspace?fromBuilder=true&autorun=true");
  }

  // ── Custom step dot count ──────────────────────────────────────────────────
  const customStepNum: Record<Step, number> = {
    "custom-1": 1, "custom-2": 2, "custom-3": 3, "custom-4": 4, "custom-5": 5,
    launch: 0, "template-pick": 0, "template-brief": 0, "template-universe": 0, preview: 0,
  };
  const currentCustomStep = customStepNum[step] ?? 0;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background" role="dialog" aria-modal="true">
      {/* Top bar */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-3">
          {step !== "launch" && (
            <button
              type="button"
              onClick={goBack}
              className="cursor-pointer flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
          )}
          <span className="font-heading text-base font-semibold">Strategy Builder</span>
        </div>

        {/* Custom mode step dots */}
        {currentCustomStep > 0 && (
          <div className="flex items-center gap-1.5">
            {[1, 2, 3, 4, 5].map(n => (
              <StepDot key={n} active={n === currentCustomStep} done={n < currentCustomStep} />
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={onClose}
          aria-label="Close strategy builder"
          className="cursor-pointer rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto">

        {/* ── LAUNCH ────────────────────────────────────────────────────── */}
        {step === "launch" && (
          <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center gap-8 px-6 py-16">
            <div className="text-center">
              <h2 className="font-heading text-3xl font-bold">Build a strategy</h2>
              <p className="mt-2 text-muted-foreground">Start from a proven template or describe your own idea step by step.</p>
            </div>
            <div className="grid w-full gap-4 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setStep("template-pick")}
                className="cursor-pointer group rounded-2xl border-2 border-border bg-card p-6 text-left transition-all duration-200 hover:border-primary hover:shadow-md"
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                  <BookOpenIcon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-heading text-lg font-semibold">Use a Template</h3>
                <p className="mt-1 text-sm text-muted-foreground">Start from a proven quant framework with full academic context.</p>
                <div className="mt-4 flex items-center gap-1 text-xs font-medium text-primary">
                  Browse templates <ChevronRight className="h-3.5 w-3.5" />
                </div>
              </button>

              <button
                type="button"
                onClick={() => setStep("custom-1")}
                className="cursor-pointer group rounded-2xl border-2 border-border bg-card p-6 text-left transition-all duration-200 hover:border-primary hover:shadow-md"
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
                  <PencilIcon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-heading text-lg font-semibold">Describe My Idea</h3>
                <p className="mt-1 text-sm text-muted-foreground">Walk through 5 steps — we&apos;ll map your idea to the right strategy framework.</p>
                <div className="mt-4 flex items-center gap-1 text-xs font-medium text-primary">
                  Start building <ChevronRight className="h-3.5 w-3.5" />
                </div>
              </button>
            </div>
          </div>
        )}

        {/* ── TEMPLATE PICK ─────────────────────────────────────────────── */}
        {step === "template-pick" && (
          <div className="mx-auto max-w-5xl px-6 py-8">
            <h2 className="font-heading text-2xl font-bold">Choose a template</h2>
            <p className="mt-1 text-muted-foreground">Each template includes full academic context and a step-by-step strategy brief.</p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search templates…"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="h-9 w-56 pl-9 text-sm"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {categories.map(cat => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setCategoryFilter(cat)}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                      categoryFilter === cat
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground",
                    )}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredTemplates.map(tmpl => (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => handleSelectTemplate(tmpl)}
                  className="cursor-pointer group rounded-xl border border-border bg-card p-4 text-left transition-all duration-200 hover:border-primary/50 hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", CAT_COLOR[tmpl.category] ?? "border-border text-muted-foreground")}>
                      {tmpl.category}
                    </span>
                    {tmpl.evidenceTier && (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-muted-foreground">
                        <span className={cn("h-1.5 w-1.5 rounded-full", EVIDENCE_DOT[tmpl.evidenceTier] ?? "bg-border")} />
                        {tmpl.evidenceTier}
                      </span>
                    )}
                  </div>
                  <h3 className="font-heading mt-2.5 text-sm font-semibold group-hover:text-primary transition-colors">{tmpl.name}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground line-clamp-2">{tmpl.description}</p>
                  <div className="mt-3 flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                    View strategy brief <ArrowRight className="h-3 w-3" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── TEMPLATE BRIEF ────────────────────────────────────────────── */}
        {step === "template-brief" && selectedTemplate && (
          <div className="mx-auto max-w-2xl px-6 py-8">
            <div className="mb-4 rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
              Here&apos;s how <strong className="text-foreground">{selectedTemplate.name}</strong> works.
              {selectedTemplate.academicRef && " It's been documented by researchers and practitioners for decades."}
            </div>
            <StrategyBriefCard template={selectedTemplate} />
            <div className="mt-6 flex justify-end">
              <Button onClick={handleBriefContinue} size="lg" className="gap-2">
                Looks good <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── TEMPLATE UNIVERSE ─────────────────────────────────────────── */}
        {step === "template-universe" && selectedTemplate && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <UniverseStep
              template={selectedTemplate}
              tickers={templateTickers}
              onTickersChange={setTemplateTickers}
              dateRange={templateDateRange}
              onDateRangeChange={setTemplateDateRange}
              onContinue={handleUniverseContinue}
            />
          </div>
        )}

        {/* ── CUSTOM STEP 1 — What are you trading? ─────────────────────── */}
        {step === "custom-1" && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <h2 className="font-heading text-2xl font-bold">What are you trading?</h2>
            <p className="mt-1 text-muted-foreground text-sm">Skip to use S&P 500 stocks by default — you can always change this later.</p>
            <div className="mt-6 grid gap-3">
              {[
                { id: "sp500",      label: "S&P 500 Stocks",    desc: "500 large-cap US companies" },
                { id: "nasdaq100",  label: "Nasdaq 100",         desc: "Top 100 tech-heavy US stocks" },
                { id: "russell1000",label: "Russell 1000",       desc: "1000 large & mid-cap US stocks" },
                { id: "commodities",label: "Commodities",        desc: "Gold, oil, agricultural ETF proxies" },
                { id: "custom",     label: "Specific tickers…",  desc: "Enter your own list" },
              ].map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setCustomConfig(c => ({ ...c, universe: opt.id }))}
                  className={cn(
                    "cursor-pointer flex items-center justify-between rounded-xl border p-4 text-left transition-all",
                    customConfig.universe === opt.id
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border hover:border-primary/40",
                  )}
                >
                  <div>
                    <div className="font-medium">{opt.label}</div>
                    <div className="text-xs text-muted-foreground">{opt.desc}</div>
                  </div>
                  {customConfig.universe === opt.id && <Check className="h-4 w-4 text-primary" />}
                </button>
              ))}
            </div>
            {customConfig.universe === "custom" && (
              <div className="mt-4 space-y-1">
                <label className="text-sm font-medium">Tickers (comma-separated)</label>
                <Input
                  placeholder="AAPL, MSFT, NVDA, AMZN…"
                  value={customConfig.customTickers}
                  onChange={e => setCustomConfig(c => ({ ...c, customTickers: e.target.value }))}
                  className="font-mono"
                />
              </div>
            )}
            <div className="mt-8 flex gap-3">
              <Button variant="outline" onClick={() => { setCustomConfig(c => ({ ...c, universe: "sp500" })); setStep("custom-2"); }}>
                Skip (use S&P 500)
              </Button>
              <Button onClick={() => setStep("custom-2")} className="gap-2">
                Next <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── CUSTOM STEP 2 — What's your idea? ────────────────────────── */}
        {step === "custom-2" && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <h2 className="font-heading text-2xl font-bold">What&apos;s your trading idea?</h2>
            <p className="mt-1 text-sm text-muted-foreground">Describe it in plain language — one or two sentences is enough.</p>
            <textarea
              value={customIdeaText}
              onChange={e => setCustomIdeaText(e.target.value)}
              placeholder={'e.g. "I want to buy stocks that have been rising for the past year and sell the losers"'}
              rows={4}
              className="mt-5 w-full rounded-xl border border-border bg-background px-4 py-3 text-sm leading-relaxed placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary resize-none"
            />
            <Button onClick={handleCustomIdeaSubmit} disabled={customIdeaText.trim().length < 5} className="mt-4 gap-2">
              Find matching strategies <ArrowRight className="h-4 w-4" />
            </Button>

            {customCandidates.length > 0 && (
              <div className="mt-8 space-y-3">
                <p className="text-sm font-medium">Based on your description, here are the closest matches:</p>
                {customCandidates.slice(0, 3).map(tmpl => (
                  <button
                    key={tmpl.id}
                    type="button"
                    onClick={() => handleCustomTemplateSelect(tmpl)}
                    className="cursor-pointer group w-full rounded-xl border border-border bg-card p-4 text-left transition-all hover:border-primary/50 hover:shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase", CAT_COLOR[tmpl.category] ?? "")}>{tmpl.category}</span>
                      {tmpl.evidenceTier && (
                        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                          <span className={cn("h-1.5 w-1.5 rounded-full", EVIDENCE_DOT[tmpl.evidenceTier] ?? "bg-border")} />
                          Evidence {tmpl.evidenceTier}
                        </span>
                      )}
                    </div>
                    <h4 className="font-heading mt-2 text-sm font-semibold group-hover:text-primary">{tmpl.name}</h4>
                    <p className="mt-0.5 text-xs text-muted-foreground">{tmpl.whatItCaptures?.split(".")[0] ?? tmpl.description}</p>
                    <div className="mt-3 flex items-center gap-1 text-xs font-medium text-primary opacity-0 group-hover:opacity-100">
                      Use this framework <ArrowRight className="h-3 w-3" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── CUSTOM STEP 3 — Execution + Risk ─────────────────────────── */}
        {step === "custom-3" && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <h2 className="font-heading text-2xl font-bold">How do you want to manage positions?</h2>
            <p className="mt-1 text-sm text-muted-foreground">We&apos;ve pre-filled sensible defaults — change anything that doesn&apos;t feel right.</p>
            <div className="mt-6 space-y-5">
              <NumberInput
                label="Max % of portfolio per position"
                value={customConfig.maxPositionPct}
                onChange={v => setCustomConfig(c => ({ ...c, maxPositionPct: v }))}
                min={1} max={100} step={1} suffix="%"
              />
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">Cut a position if it drops</label>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setCustomConfig(c => ({ ...c, stopLossEnabled: !c.stopLossEnabled }))}
                    className={cn(
                      "cursor-pointer relative h-6 w-10 rounded-full transition-colors",
                      customConfig.stopLossEnabled ? "bg-primary" : "bg-border",
                    )}
                  >
                    <span className={cn(
                      "absolute top-1 h-4 w-4 rounded-full bg-white transition-transform shadow-sm",
                      customConfig.stopLossEnabled ? "left-5" : "left-1",
                    )} />
                  </button>
                  <span className="text-sm text-muted-foreground">{customConfig.stopLossEnabled ? "Stop-loss enabled" : "No stop-loss"}</span>
                </div>
                {customConfig.stopLossEnabled && (
                  <NumberInput
                    label="Stop-loss at"
                    value={customConfig.stopLossPct}
                    onChange={v => setCustomConfig(c => ({ ...c, stopLossPct: v }))}
                    min={1} max={50} step={1} suffix="% drop"
                  />
                )}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Direction</label>
                <div className="flex gap-2">
                  {["Long only", "Long & Short"].map(opt => (
                    <button
                      key={opt}
                      type="button"
                      className={cn(
                        "cursor-pointer rounded-lg border px-4 py-2 text-sm transition-colors",
                        opt === "Long only" ? "border-primary bg-primary/5 text-primary" : "border-border text-muted-foreground cursor-not-allowed opacity-50",
                      )}
                      disabled={opt === "Long & Short"}
                    >
                      {opt} {opt === "Long & Short" && <Lock className="ml-1 inline h-3 w-3" />}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-8">
              <Button onClick={() => setStep("custom-4")} className="gap-2">
                Next <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── CUSTOM STEP 4 — Hold period ───────────────────────────────── */}
        {step === "custom-4" && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <h2 className="font-heading text-2xl font-bold">How long will you hold each position?</h2>
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {([
                { label: "Daily",    value: "daily"    as RebalanceFrequency, desc: "Rebalance every day" },
                { label: "Weekly",   value: "weekly"   as RebalanceFrequency, desc: "Rebalance each week" },
                { label: "Monthly",  value: "monthly"  as RebalanceFrequency, desc: "Rebalance each month" },
                { label: "Quarterly",value: "quarterly"as RebalanceFrequency, desc: "Rebalance each quarter" },
              ]).map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setCustomConfig(c => ({ ...c, holdPeriod: opt.value }))}
                  className={cn(
                    "cursor-pointer rounded-xl border p-4 text-center transition-all",
                    customConfig.holdPeriod === opt.value
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border hover:border-primary/40",
                  )}
                >
                  <div className="font-semibold">{opt.label}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{opt.desc}</div>
                </button>
              ))}
            </div>
            <div className="mt-6">
              <NumberInput
                label="Minimum daily trading volume per stock"
                value={customConfig.minAdv / 1_000_000}
                onChange={v => setCustomConfig(c => ({ ...c, minAdv: v * 1_000_000 }))}
                min={0} max={100} step={0.5} suffix="M/day"
              />
            </div>
            <div className="mt-8">
              <Button onClick={() => setStep("custom-5")} className="gap-2">
                Next <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── CUSTOM STEP 5 — Time + capital ───────────────────────────── */}
        {step === "custom-5" && (
          <div className="mx-auto max-w-xl px-6 py-12">
            <h2 className="font-heading text-2xl font-bold">Time period &amp; starting capital</h2>
            <p className="mt-1 text-sm text-muted-foreground">How far back should the backtest go?</p>
            <div className="mt-5 flex gap-3">
              {(["3Y", "5Y", "10Y"] as const).map(range => (
                <button
                  key={range}
                  type="button"
                  onClick={() => setCustomConfig(c => ({ ...c, dateRange: range }))}
                  className={cn(
                    "cursor-pointer flex-1 rounded-xl border py-3 text-center font-semibold transition-all",
                    customConfig.dateRange === range
                      ? "border-primary bg-primary/5 ring-1 ring-primary text-primary"
                      : "border-border hover:border-primary/40",
                  )}
                >
                  {range}
                </button>
              ))}
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <NumberInput
                label="Starting capital"
                value={customConfig.capital}
                onChange={v => setCustomConfig(c => ({ ...c, capital: v }))}
                min={1000} max={10000000} step={1000} suffix="USD"
              />
              <NumberInput
                label="Transaction cost estimate"
                value={customConfig.costBps}
                onChange={v => setCustomConfig(c => ({ ...c, costBps: v }))}
                min={0} max={100} step={1} suffix="bps/trade"
              />
            </div>
            <div className="mt-8">
              <Button onClick={handleCustomPreview} disabled={!customConfig.selectedTemplate} className="gap-2">
                Preview Strategy <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* ── PREVIEW ───────────────────────────────────────────────────── */}
        {step === "preview" && (
          <PreviewStep
            strategyName={strategyName}
            editingName={editingName}
            nameInputRef={nameInputRef}
            onNameChange={setStrategyName}
            onEditName={() => setEditingName(true)}
            onBlurName={() => setEditingName(false)}
            selectedTemplate={selectedTemplate ?? customConfig.selectedTemplate}
            tickers={selectedTemplate ? resolvedTickers() : (
              customConfig.universe === "custom"
                ? customConfig.customTickers.split(",").map(s => s.trim()).filter(Boolean)
                : UNIVERSE_DEFAULTS[customConfig.universe] ?? []
            )}
            dateRange={selectedTemplate ? templateDateRange : customConfig.dateRange}
            capital={selectedTemplate ? 100000 : customConfig.capital}
            costBps={selectedTemplate ? 10 : customConfig.costBps}
            rebalance={selectedTemplate ? selectedTemplate.strategy.rebalance_frequency : customConfig.holdPeriod}
            maxPositionPct={selectedTemplate
              ? (selectedTemplate.strategy.position_sizing.max_positions ? Math.round(100 / selectedTemplate.strategy.position_sizing.max_positions) : 5)
              : customConfig.maxPositionPct}
            onEdit={goBack}
            onRunBacktest={handleRunBacktest}
          />
        )}

      </div>
    </div>
  );
}

// ── Universe step sub-component ───────────────────────────────────────────────

function UniverseStep({
  template, tickers, onTickersChange,
  dateRange, onDateRangeChange, onContinue,
}: {
  template: ResearchTemplate;
  tickers: string;
  onTickersChange: (v: string) => void;
  dateRange: "3Y" | "5Y" | "10Y";
  onDateRangeChange: (v: "3Y" | "5Y" | "10Y") => void;
  onContinue: () => void;
}) {
  const isMulti = template.multiTicker;
  const minCount = template.minTickers ?? 1;
  const tickerCount = tickers.split(",").map(s => s.trim()).filter(Boolean).length;
  const isValid = tickerCount >= minCount;

  // Context-aware question
  let question = template.tickerLabel || "Which ticker do you want to test this on?";
  if (template.strategy.strategy_type === "sector_rotation") question = "Which sector ETFs? (defaults to all 11 SPDR sector ETFs)";
  else if (template.strategy.strategy_type === "pairs_trading") question = "Which two stocks do you want to pair up? (e.g. COST and WMT)";
  else if (!isMulti) question = `Which ${template.category === "Reversal" ? "stock or ETF" : "ticker"} do you want to test this on?`;
  else if (minCount >= 10) question = `Which group of stocks? (need at least ${minCount} for a meaningful cross-section)`;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-heading text-2xl font-bold">{question}</h2>
        {isMulti && minCount > 1 && (
          <p className="mt-1 text-sm text-muted-foreground">Enter comma-separated tickers — minimum {minCount} for this strategy type.</p>
        )}
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">
          {isMulti ? "Tickers (comma-separated)" : "Ticker"}
        </label>
        <Input
          value={tickers}
          onChange={e => onTickersChange(e.target.value)}
          placeholder={template.defaultTickers.slice(0, 4).join(", ") + (template.defaultTickers.length > 4 ? ", …" : "")}
          className="font-mono"
        />
        {isMulti && (
          <p className="text-xs text-muted-foreground">
            {tickerCount} entered{minCount > 1 ? ` · need at least ${minCount}` : ""}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground">How far back should we test?</label>
        <div className="flex gap-3">
          {(["3Y", "5Y", "10Y"] as const).map(r => (
            <button
              key={r}
              type="button"
              onClick={() => onDateRangeChange(r)}
              className={cn(
                "cursor-pointer flex-1 rounded-xl border py-2.5 text-center font-semibold transition-all text-sm",
                dateRange === r
                  ? "border-primary bg-primary/5 ring-1 ring-primary text-primary"
                  : "border-border hover:border-primary/40",
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <Button onClick={onContinue} disabled={!isValid} size="lg" className="gap-2">
        Preview Strategy <ArrowRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

// ── Preview step sub-component ────────────────────────────────────────────────

function PreviewStep({
  strategyName, editingName, nameInputRef,
  onNameChange, onEditName, onBlurName,
  selectedTemplate, tickers, dateRange,
  capital, costBps, rebalance, maxPositionPct,
  onEdit, onRunBacktest,
}: {
  strategyName: string;
  editingName: boolean;
  nameInputRef: React.RefObject<HTMLInputElement | null>;
  onNameChange: (v: string) => void;
  onEditName: () => void;
  onBlurName: () => void;
  selectedTemplate: ResearchTemplate | null;
  tickers: string[];
  dateRange: "3Y" | "5Y" | "10Y";
  capital: number;
  costBps: number;
  rebalance: RebalanceFrequency;
  maxPositionPct: number;
  onEdit: () => void;
  onRunBacktest: () => void;
}) {
  const tickerDisplay = tickers.length <= 4
    ? tickers.join(", ")
    : `${tickers.slice(0, 3).join(", ")} +${tickers.length - 3} more`;

  const summaryRows = [
    { label: "Strategy type", value: selectedTemplate?.name ?? "Custom" },
    { label: "Universe",      value: tickerDisplay || "Default" },
    { label: "Test period",   value: dateRange + " of history" },
    { label: "Rebalance",     value: rebalance.charAt(0).toUpperCase() + rebalance.slice(1) },
    { label: "Max per position", value: `${maxPositionPct}%` },
    { label: "Starting capital", value: `$${capital.toLocaleString()}` },
    { label: "Cost estimate", value: `${costBps} bps/trade` },
    { label: "Direction",     value: "Long only" },
  ];

  return (
    <div className="mx-auto max-w-xl px-6 py-12">
      <h2 className="font-heading text-2xl font-bold">Your strategy is ready</h2>
      <p className="mt-1 text-sm text-muted-foreground">Review the summary, then run the backtest to see results.</p>

      <div className="mt-6 overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        {/* Name row */}
        <div className="flex items-center gap-2 border-b border-border px-5 py-4">
          {editingName ? (
            <input
              ref={nameInputRef}
              value={strategyName}
              onChange={e => onNameChange(e.target.value)}
              onBlur={onBlurName}
              onKeyDown={e => e.key === "Enter" && onBlurName()}
              className="flex-1 bg-transparent text-base font-semibold focus:outline-none"
            />
          ) : (
            <>
              <span className="flex-1 font-heading text-base font-semibold">{strategyName}</span>
              <button
                type="button"
                onClick={onEditName}
                aria-label="Edit strategy name"
                className="cursor-pointer rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
              >
                <Pencil className="h-4 w-4" />
              </button>
            </>
          )}
        </div>

        {/* Summary rows */}
        <div className="divide-y divide-border/60">
          {summaryRows.map(({ label, value }) => (
            <div key={label} className="flex items-center justify-between px-5 py-2.5">
              <span className="text-sm text-muted-foreground">{label}</span>
              <span className="text-sm font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 flex gap-3">
        <Button variant="outline" onClick={onEdit} className="gap-2">
          <ArrowLeft className="h-4 w-4" /> Edit
        </Button>
        <Button onClick={onRunBacktest} size="lg" className="flex-1 gap-2">
          <Play className="h-4 w-4" /> Run Backtest
        </Button>
      </div>
    </div>
  );
}

// ── Inline icon stubs (avoids extra imports) ──────────────────────────────────
function BookOpenIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  );
}
function PencilIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}
