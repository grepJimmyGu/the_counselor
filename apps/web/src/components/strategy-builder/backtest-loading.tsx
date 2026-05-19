"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchTemplate, StrategyJson } from "@/lib/contracts";
import { researchTemplates } from "@/lib/contracts";

// ── Progress stages ───────────────────────────────────────────────────────────

const STAGES = [
  { key: "prices",    label: "Fetching prices",       detail: (s: StrategyJson) => `${s.universe.slice(0, 3).join(", ")}${s.universe.length > 3 ? ` +${s.universe.length - 3}` : ""} · ${new Date(s.start_date).getFullYear()}–${new Date(s.end_date).getFullYear()}` },
  { key: "signal",    label: "Building signal",        detail: (_: StrategyJson) => "Ranking & scoring positions" },
  { key: "simulate",  label: "Simulating trades",      detail: (_: StrategyJson, trades?: number) => trades ? `${trades.toLocaleString()} trades processed` : "Running trade-by-trade simulation" },
  { key: "metrics",   label: "Calculating metrics",    detail: (_: StrategyJson) => "Sharpe, drawdown, win rate…" },
  { key: "report",    label: "Generating report",      detail: (_: StrategyJson) => "Preparing results" },
];

type StageKey = typeof STAGES[number]["key"];
type StageStatus = "pending" | "running" | "done";

// ── Context card types ────────────────────────────────────────────────────────

interface ContextCard {
  title: string;
  body: string | React.ReactNode;
}

function buildContextCards(strategy: StrategyJson): ContextCard[] {
  const template = researchTemplates.find(t =>
    t.strategy.strategy_type === strategy.strategy_type && t.availability === "ready"
  ) as ResearchTemplate | undefined;

  const cards: ContextCard[] = [];

  // Card A — Strategy context
  if (template?.academicRef) {
    cards.push({
      title: "Why this strategy has an edge",
      body: (
        <div className="space-y-2">
          <p className="text-sm leading-relaxed text-foreground/80">
            {template.whatItCaptures ?? template.description}
          </p>
          <p className="text-xs text-muted-foreground">
            📑 {template.academicRef.citation}
          </p>
          <p className="text-xs italic text-muted-foreground">
            &ldquo;{template.academicRef.note}&rdquo;
          </p>
        </div>
      ),
    });
  }

  // Card B — Universe context
  if (strategy.universe.length > 0) {
    const tickerList = strategy.universe.slice(0, 6).join(", ");
    const rest = strategy.universe.length > 6 ? ` and ${strategy.universe.length - 6} more` : "";
    cards.push({
      title: "Your universe at a glance",
      body: (
        <div className="space-y-2">
          <p className="text-sm text-foreground/80">
            Testing across <strong>{strategy.universe.length}</strong> assets: {tickerList}{rest}.
          </p>
          <p className="text-sm text-muted-foreground">
            Period: {strategy.start_date} → {strategy.end_date} ·{" "}
            {Math.round((new Date(strategy.end_date).getTime() - new Date(strategy.start_date).getTime()) / (365.25 * 24 * 3600 * 1000))} years of data
          </p>
          <p className="text-sm text-muted-foreground">
            Cost assumption: {strategy.transaction_cost_bps + strategy.slippage_bps} bps combined per round trip
          </p>
        </div>
      ),
    });
  }

  // Card C — What to look for
  cards.push({
    title: "When your results load, focus on these first",
    body: (
      <ol className="space-y-2">
        {[
          ["Sharpe ratio", "Anything above 0.8 is worth studying further"],
          ["Max drawdown", "This is what you'd actually have to live through"],
          ["Excess vs benchmark", "Did the strategy beat a simple buy-and-hold?"],
          ["Turnover", "High turnover erodes returns — check the trade log"],
        ].map(([metric, desc]) => (
          <li key={metric} className="flex gap-2 text-sm">
            <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
            <span><strong className="text-foreground">{metric}</strong> — <span className="text-muted-foreground">{desc}</span></span>
          </li>
        ))}
      </ol>
    ),
  });

  return cards;
}

// ── Simulate stage progression ────────────────────────────────────────────────

function useStageProgress(isRunning: boolean): Record<StageKey, StageStatus> {
  const [statuses, setStatuses] = useState<Record<StageKey, StageStatus>>({
    prices: "running", signal: "pending", simulate: "pending", metrics: "pending", report: "pending",
  });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isRunning) return;
    // Reset
    setStatuses({ prices: "running", signal: "pending", simulate: "pending", metrics: "pending", report: "pending" });

    const schedule = [
      [1800, "prices",   "signal"],
      [4000, "signal",   "simulate"],
      [7500, "simulate", "metrics"],
      [9500, "metrics",  "report"],
    ] as [number, StageKey, StageKey][];

    const timers = schedule.map(([delay, finish, next]) =>
      setTimeout(() => setStatuses(prev => ({ ...prev, [finish]: "done", [next]: "running" })), delay)
    );

    return () => timers.forEach(clearTimeout);
  }, [isRunning]);

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  return statuses;
}

// ── Main component ────────────────────────────────────────────────────────────

interface BacktestLoadingProps {
  strategy: StrategyJson;
  isRunning: boolean;
}

export function BacktestLoading({ strategy, isRunning }: BacktestLoadingProps) {
  const statuses = useStageProgress(isRunning);
  const [cardIndex, setCardIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const cards = buildContextCards(strategy);

  // Rotate cards every 5 seconds with fade
  useEffect(() => {
    if (!isRunning || cards.length <= 1) return;
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setCardIndex(i => (i + 1) % cards.length);
        setVisible(true);
      }, 400);
    }, 5000);
    return () => clearInterval(interval);
  }, [isRunning, cards.length]);

  const activeCard = cards[cardIndex];

  return (
    <div className="flex flex-col items-center gap-8 py-12 px-4">

      {/* Progress tracker */}
      <div className="w-full max-w-3xl">
        <div className="hidden items-center sm:flex">
          {STAGES.map((stage, idx) => {
            const status = statuses[stage.key as StageKey];
            const isLast = idx === STAGES.length - 1;
            return (
              <div key={stage.key} className="flex flex-1 items-center">
                <div className="flex min-w-0 flex-col items-center gap-1.5">
                  {/* Icon */}
                  <div className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-500",
                    status === "done"    ? "border-primary bg-primary text-primary-foreground" :
                    status === "running" ? "border-primary bg-primary/10 text-primary animate-pulse" :
                                          "border-border bg-background text-muted-foreground",
                  )}>
                    {status === "done"
                      ? <Check className="h-4 w-4" />
                      : status === "running"
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : <span className="text-xs font-bold">{idx + 1}</span>
                    }
                  </div>
                  {/* Label */}
                  <span className={cn(
                    "text-center text-[11px] font-medium leading-tight max-w-[80px]",
                    status === "running" ? "text-primary" : status === "done" ? "text-foreground" : "text-muted-foreground",
                  )}>
                    {stage.label}
                  </span>
                  {/* Detail */}
                  {status === "running" && (
                    <span className="text-center text-[10px] text-muted-foreground max-w-[80px]">
                      {stage.detail(strategy)}
                    </span>
                  )}
                </div>
                {/* Connector line */}
                {!isLast && (
                  <div className={cn(
                    "mx-1 h-0.5 flex-1 transition-all duration-700",
                    status === "done" ? "bg-primary" : "bg-border",
                  )} />
                )}
              </div>
            );
          })}
        </div>

        {/* Mobile: simple status line */}
        <div className="sm:hidden text-center">
          {Object.entries(statuses).map(([key, status]) => {
            if (status !== "running") return null;
            const stage = STAGES.find(s => s.key === key);
            if (!stage) return null;
            return (
              <div key={key} className="flex items-center justify-center gap-2 text-sm font-medium text-primary">
                <Loader2 className="h-4 w-4 animate-spin" />
                {stage.label}…
              </div>
            );
          })}
        </div>
      </div>

      {/* Context card */}
      {activeCard && (
        <div
          className={cn(
            "w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-sm transition-opacity duration-400",
            visible ? "opacity-100" : "opacity-0",
          )}
        >
          <div className="mb-3 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
              {activeCard.title}
            </h4>
          </div>
          {typeof activeCard.body === "string"
            ? <p className="text-sm leading-relaxed text-foreground/80">{activeCard.body}</p>
            : activeCard.body
          }
          {/* Card indicator dots */}
          {cards.length > 1 && (
            <div className="mt-4 flex justify-center gap-1.5">
              {cards.map((_, i) => (
                <span key={i} className={cn(
                  "h-1.5 w-1.5 rounded-full transition-all",
                  i === cardIndex ? "bg-primary" : "bg-border",
                )} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
