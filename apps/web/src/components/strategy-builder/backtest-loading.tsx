"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchTemplate, StrategyJson } from "@/lib/contracts";
import { researchTemplates } from "@/lib/contracts";

// ── Respect prefers-reduced-motion ───────────────────────────────────────────

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

// ── Stages ────────────────────────────────────────────────────────────────────

const STAGES = [
  { key: "prices",   label: "Fetching prices",     detail: (s: StrategyJson) => `${s.universe.slice(0, 3).join(", ")}${s.universe.length > 3 ? ` +${s.universe.length - 3}` : ""} · ${new Date(s.start_date).getFullYear()}–${new Date(s.end_date).getFullYear()}` },
  { key: "signal",   label: "Building signal",     detail: () => "Ranking & scoring positions" },
  { key: "simulate", label: "Simulating trades",   detail: () => "Running trade-by-trade simulation" },
  { key: "metrics",  label: "Calculating metrics", detail: () => "Sharpe, drawdown, win rate…" },
  { key: "report",   label: "Generating report",   detail: () => "Preparing your results" },
] as const;

type StageKey = typeof STAGES[number]["key"];
type StageStatus = "pending" | "running" | "done";

// ── Context cards ─────────────────────────────────────────────────────────────

interface ContextCard { title: string; body: React.ReactNode }

function buildContextCards(strategy: StrategyJson): ContextCard[] {
  const template = researchTemplates.find(
    t => t.strategy.strategy_type === strategy.strategy_type && t.availability === "ready",
  ) as ResearchTemplate | undefined;

  const cards: ContextCard[] = [];

  if (template?.academicRef) {
    cards.push({
      title: "Why this strategy has an edge",
      body: (
        <div className="space-y-2.5">
          <p className="text-sm leading-relaxed text-foreground/80">
            {template.whatItCaptures ?? template.description}
          </p>
          <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2">
            <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div>
              <p className="text-xs font-semibold text-foreground/70">{template.academicRef.citation}</p>
              <p className="mt-0.5 text-xs italic text-muted-foreground">&ldquo;{template.academicRef.note}&rdquo;</p>
            </div>
          </div>
        </div>
      ),
    });
  }

  if (strategy.universe.length > 0) {
    const tickerList = strategy.universe.slice(0, 6).join(", ");
    const rest = strategy.universe.length > 6 ? ` and ${strategy.universe.length - 6} more` : "";
    const years = Math.round(
      (new Date(strategy.end_date).getTime() - new Date(strategy.start_date).getTime()) / (365.25 * 24 * 3600 * 1000),
    );
    cards.push({
      title: "Your universe at a glance",
      body: (
        <div className="space-y-2">
          <p className="text-sm text-foreground/80">
            Testing across <strong>{strategy.universe.length}</strong> {strategy.universe.length === 1 ? "asset" : "assets"}:{" "}
            <span className="font-mono text-xs">{tickerList}{rest}</span>
          </p>
          <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-muted/30 px-3 py-2 text-xs">
            <div><span className="text-muted-foreground">Period</span><br /><strong>{years}Y</strong></div>
            <div><span className="text-muted-foreground">Start</span><br /><strong className="font-mono">{strategy.start_date.slice(0, 7)}</strong></div>
            <div><span className="text-muted-foreground">Cost</span><br /><strong>{strategy.transaction_cost_bps + strategy.slippage_bps} bps</strong></div>
          </div>
        </div>
      ),
    });
  }

  cards.push({
    title: "When your results load, focus on these first",
    body: (
      <ol className="space-y-2">
        {[
          { metric: "Sharpe ratio",        desc: "Anything above 0.8 is worth studying further",         color: "bg-blue-500" },
          { metric: "Max drawdown",        desc: "This is what you'd actually have to live through",      color: "bg-rose-500" },
          { metric: "Excess vs benchmark", desc: "Did the strategy beat a simple buy-and-hold?",          color: "bg-emerald-500" },
          { metric: "Turnover",            desc: "High turnover erodes returns — check the trade log",    color: "bg-amber-500" },
        ].map(({ metric, desc, color }) => (
          <li key={metric} className="flex gap-2.5 text-sm">
            <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", color)} />
            <span>
              <strong className="text-foreground">{metric}</strong>
              <span className="text-muted-foreground"> — {desc}</span>
            </span>
          </li>
        ))}
      </ol>
    ),
  });

  return cards;
}

// ── Stage progress hook ───────────────────────────────────────────────────────

function useStageProgress(isRunning: boolean): Record<StageKey, StageStatus> {
  const [statuses, setStatuses] = useState<Record<StageKey, StageStatus>>({
    prices: "running", signal: "pending", simulate: "pending", metrics: "pending", report: "pending",
  });

  useEffect(() => {
    if (!isRunning) return;
    setStatuses({ prices: "running", signal: "pending", simulate: "pending", metrics: "pending", report: "pending" });

    const schedule: [number, StageKey, StageKey][] = [
      [1800, "prices",   "signal"],
      [4000, "signal",   "simulate"],
      [7500, "simulate", "metrics"],
      [9500, "metrics",  "report"],
    ];

    const timers = schedule.map(([delay, finish, next]) =>
      setTimeout(() => setStatuses(prev => ({ ...prev, [finish]: "done", [next]: "running" })), delay),
    );
    return () => timers.forEach(clearTimeout);
  }, [isRunning]);

  return statuses;
}

// ── Main component ────────────────────────────────────────────────────────────

interface BacktestLoadingProps {
  strategy: StrategyJson;
  isRunning: boolean;
}

export function BacktestLoading({ strategy, isRunning }: BacktestLoadingProps) {
  const reducedMotion = useReducedMotion();
  const statuses = useStageProgress(isRunning);
  const [cardIndex, setCardIndex] = useState(0);
  const [fadeIn, setFadeIn] = useState(true);
  const cards = buildContextCards(strategy);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isRunning || cards.length <= 1 || reducedMotion) return;
    intervalRef.current = setInterval(() => {
      setFadeIn(false);
      setTimeout(() => {
        setCardIndex(i => (i + 1) % cards.length);
        setFadeIn(true);
      }, 300);
    }, 5000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning, cards.length, reducedMotion]);

  const activeCard = cards[cardIndex];

  return (
    <div className="flex flex-col items-center gap-8 px-4 py-14">

      {/* Progress tracker */}
      <div className="w-full max-w-3xl">

        {/* Desktop: horizontal flow */}
        <div className="hidden items-start sm:flex" role="progressbar" aria-label="Backtest progress">
          {STAGES.map((stage, idx) => {
            const status = statuses[stage.key as StageKey];
            const isLast = idx === STAGES.length - 1;
            const isDone = status === "done";
            const isActive = status === "running";

            return (
              <div key={stage.key} className="flex flex-1 items-start">
                {/* Stage node */}
                <div className="flex min-w-0 flex-col items-center gap-1.5 flex-1">
                  <div className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-all",
                    reducedMotion ? "" : "duration-500",
                    isDone    ? "border-primary bg-primary text-primary-foreground shadow-md shadow-primary/20" :
                    isActive  ? "border-primary bg-primary/15 text-primary" :
                                "border-border bg-background text-muted-foreground",
                  )}>
                    {isDone
                      ? <Check className="h-4 w-4" aria-hidden="true" />
                      : isActive
                      ? <Loader2 className={cn("h-4 w-4", !reducedMotion && "animate-spin")} aria-hidden="true" />
                      : <span className="text-xs font-bold">{idx + 1}</span>
                    }
                  </div>
                  <span className={cn(
                    "text-center text-[11px] font-medium leading-tight max-w-[72px]",
                    isActive ? "text-primary" : isDone ? "text-foreground/80" : "text-muted-foreground",
                  )}>
                    {stage.label}
                  </span>
                  {isActive && (
                    <span className="text-center text-[10px] text-muted-foreground max-w-[80px] leading-tight">
                      {stage.detail(strategy)}
                    </span>
                  )}
                </div>

                {/* Connector line with fill animation */}
                {!isLast && (
                  <div className="relative mt-[18px] mx-0.5 h-0.5 flex-1 overflow-hidden rounded-full bg-border">
                    <div className={cn(
                      "absolute inset-y-0 left-0 rounded-full bg-primary",
                      reducedMotion ? "" : "transition-all duration-700",
                      isDone ? "w-full" : "w-0",
                    )} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Mobile: simple active stage label */}
        <div className="flex flex-col items-center gap-2 sm:hidden">
          {STAGES.filter(s => statuses[s.key as StageKey] === "running").map(stage => (
            <div key={stage.key} className="flex items-center gap-2 text-sm font-medium text-primary">
              <Loader2 className={cn("h-4 w-4", !reducedMotion && "animate-spin")} aria-hidden="true" />
              {stage.label}…
            </div>
          ))}
          {/* Mini dot progress */}
          <div className="flex gap-1.5 mt-1">
            {STAGES.map((s, i) => {
              const st = statuses[s.key as StageKey];
              return (
                <span key={i} className={cn(
                  "h-1.5 rounded-full transition-all",
                  reducedMotion ? "" : "duration-300",
                  st === "done" ? "w-4 bg-primary" : st === "running" ? "w-3 bg-primary/60" : "w-1.5 bg-border",
                )} />
              );
            })}
          </div>
        </div>
      </div>

      {/* Context card — glassmorphism style */}
      {activeCard && (
        <div
          className={cn(
            "w-full max-w-2xl rounded-2xl border border-border/80 bg-card/90 p-6 shadow-xl backdrop-blur-sm",
            reducedMotion ? "opacity-100" : "transition-opacity duration-300",
            reducedMotion ? "" : (fadeIn ? "opacity-100" : "opacity-0"),
          )}
          aria-live="polite"
          aria-atomic="true"
        >
          {/* Card header */}
          <div className="mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
            <h4 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {activeCard.title}
            </h4>
          </div>

          {activeCard.body}

          {/* Dot pagination */}
          {cards.length > 1 && (
            <div className="mt-5 flex justify-center gap-1.5" role="tablist" aria-label="Context slides">
              {cards.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  role="tab"
                  aria-selected={i === cardIndex}
                  aria-label={`Slide ${i + 1} of ${cards.length}`}
                  onClick={() => { setCardIndex(i); setFadeIn(true); }}
                  className={cn(
                    "cursor-pointer rounded-full transition-all",
                    reducedMotion ? "" : "duration-300",
                    i === cardIndex
                      ? "h-1.5 w-4 bg-primary"
                      : "h-1.5 w-1.5 bg-border hover:bg-primary/50",
                  )}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
