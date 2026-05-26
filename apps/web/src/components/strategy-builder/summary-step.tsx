"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ShieldCheck, Sliders, Target, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ResearchTemplate } from "@/lib/contracts";
import type { WizardStrategy } from "./wizard/strategy-wizard-data";
import { ResultsDisclaimer } from "./results-disclaimer";

/**
 * Summary step — 4-block model: WHAT / WHEN IN / HOW MUCH / WHEN OUT.
 *
 * Replaces the modal's template-brief + template-universe + custom-3/4/5
 * screens for the wizard path (PR-C, 2026-05-24). WHEN IN and WHEN OUT
 * are read-only template-baked copy; HOW MUCH is the editable surface
 * (risk preset + weight distribution + capital + transaction-cost
 * opt-in).
 *
 * Risk-preset display (Low/Medium/High) is wired UI-only in this PR;
 * PR-D will add `applyRiskLevel()` to actually mutate the StrategyJSON
 * before backtest.
 */

export type RiskPreset = "low" | "medium" | "high";

// Mirrors `risk_control_prompt.md` mapping table. UI-only display in
// PR-C; PR-D wires the StrategyJSON mutation.
const RISK_PRESETS: Record<RiskPreset, {
  label: string;
  desc: string;
  pills: string[];
}> = {
  low: {
    label: "Conservative",
    desc: "Sleep-easy. Vol-targeted to 8% annual; portfolio halts at −15% drawdown.",
    pills: ["Vol target: 8%", "Max DD stop: 15%", "Per-position stop: 8%"],
  },
  medium: {
    label: "Balanced",
    desc: "Typical retail. Modest vol scaling; portfolio halts at −25% drawdown.",
    pills: ["Vol target: 12%", "Max DD stop: 25%", "Per-position stop: 12%"],
  },
  high: {
    label: "Aggressive",
    desc: "Long-run compounding. No vol scaling; halts only at −40% drawdown.",
    pills: ["No vol scaling", "Max DD stop: 40%", "No per-position stop"],
  },
};

export interface SummaryStepConfig {
  /** Free-input list of tickers (the WHAT). Comma- or space-separated. */
  tickers: string;
  /** Risk preset, defaults from wizard's `dd` answer. */
  riskPreset: RiskPreset;
  /** Weight mode: equal (auto-divide) or custom (per-ticker free input). */
  weightMode: "equal" | "custom";
  /** Custom weights, keyed by ticker. Only used when weightMode="custom". */
  customWeights: Record<string, number>;
  /** Starting capital in USD. */
  capital: number;
  /** Transaction-cost opt-in. When false, sent as 0 to the backend. */
  costEnabled: boolean;
  /** Transaction cost in bps/trade. Used only when costEnabled=true. */
  costBps: number;
}

export interface SummaryStepProps {
  /** The picked strategy from the wizard. Provides plain-English signals. */
  template: ResearchTemplate;
  /** Optional richer signal copy from the framework strategy. Used if
   *  the template doesn't carry its own `whenInCopy`/`whenOutCopy`. */
  wizardStrategy?: WizardStrategy;
  /** Initial preset, derived from the wizard's drawdown answer. */
  initialRiskPreset?: RiskPreset;
  /** Pre-filled tickers (e.g. from a stock-detail page click). */
  initialTickers?: string;
  onContinue: (config: SummaryStepConfig) => void;
}

export function SummaryStep({
  template,
  wizardStrategy,
  initialRiskPreset = "medium",
  initialTickers,
  onContinue,
}: SummaryStepProps) {
  const [tickers, setTickers] = useState<string>(
    initialTickers?.trim() || template.defaultTickers.join(", "),
  );
  const [riskPreset, setRiskPreset] = useState<RiskPreset>(initialRiskPreset);
  const [weightMode, setWeightMode] = useState<"equal" | "custom">("equal");
  const [customWeights, setCustomWeights] = useState<Record<string, number>>({});
  const [capital, setCapital] = useState<number>(100_000);
  const [costEnabled, setCostEnabled] = useState<boolean>(false);
  const [costBps, setCostBps] = useState<number>(10);

  const tickerList = useMemo(
    () =>
      tickers
        .split(/[,\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean),
    [tickers],
  );

  const isBasket = tickerList.length >= 2;

  // Initialize custom weights to equal when switching modes
  useEffect(() => {
    if (weightMode === "custom" && tickerList.length > 0) {
      const equalPct = Math.round((100 / tickerList.length) * 10) / 10;
      const init: Record<string, number> = {};
      for (const t of tickerList) {
        init[t] = customWeights[t] ?? equalPct;
      }
      setCustomWeights(init);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weightMode, tickerList.join(",")]);

  const totalWeight = useMemo(() => {
    if (weightMode === "equal") return 100;
    return tickerList.reduce((sum, t) => sum + (customWeights[t] ?? 0), 0);
  }, [weightMode, customWeights, tickerList]);

  const weightValid = weightMode === "equal" || Math.abs(totalWeight - 100) < 0.1;
  const tickersValid = tickerList.length > 0;
  const capitalValid = capital >= 1_000 && capital <= 100_000_000;
  const canContinue = tickersValid && weightValid && capitalValid;

  const whenIn = template.whenInCopy ?? deriveWhenIn(template, wizardStrategy);
  const whenOut = template.whenOutCopy ?? deriveWhenOut(template, wizardStrategy);

  function submit(): void {
    onContinue({
      tickers,
      riskPreset,
      weightMode,
      customWeights,
      capital,
      costEnabled,
      costBps,
    });
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8 space-y-5">
      <div>
        <h2 className="font-heading text-2xl font-bold">{template.name}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{template.description}</p>
      </div>

      {/* WHAT */}
      <Section icon={<Target className="h-4 w-4" />} title="What" subtitle="Which asset(s) the strategy trades">
        <label className="block">
          <span className="text-xs font-medium text-muted-foreground">
            Tickers — comma or space separated
          </span>
          <Input
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
            placeholder="AAPL, MSFT, NVDA"
            className="mt-1.5 font-mono text-sm"
          />
        </label>
        {tickerList.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {tickerList.map((t) => (
              <span
                key={t}
                className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs font-medium"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </Section>

      {/* WHEN IN — read-only */}
      <Section
        icon={<ArrowRight className="h-4 w-4 rotate-180" />}
        title="When in"
        subtitle="The signal that triggers a buy"
        readOnly
      >
        <p className="text-sm leading-relaxed text-foreground/85">{whenIn}</p>
      </Section>

      {/* HOW MUCH — editable */}
      <Section icon={<Wallet className="h-4 w-4" />} title="How much" subtitle="Position sizing, risk, and capital">
        {/* Risk preset */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" /> Risk level
          </div>
          <div className="grid grid-cols-3 gap-2">
            {(Object.keys(RISK_PRESETS) as RiskPreset[]).map((preset) => {
              const isSelected = riskPreset === preset;
              const cfg = RISK_PRESETS[preset];
              return (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setRiskPreset(preset)}
                  aria-pressed={isSelected}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-left transition-colors",
                    isSelected
                      ? "border-primary bg-primary/8 ring-1 ring-primary"
                      : "border-border hover:border-primary/40 hover:bg-muted/30",
                  )}
                >
                  <div className={cn("text-sm font-semibold", isSelected && "text-primary")}>
                    {cfg.label}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground leading-snug">
                    {cfg.desc}
                  </div>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            {RISK_PRESETS[riskPreset].pills.map((pill) => (
              <span
                key={pill}
                className="rounded-md border border-border bg-muted/30 px-1.5 py-0.5 font-mono text-foreground/70"
              >
                {pill}
              </span>
            ))}
          </div>
        </div>

        {/* Weight distribution — only when basket */}
        {isBasket && (
          <div className="mt-5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Sliders className="h-3.5 w-3.5" /> Position weights
            </div>
            <div className="flex gap-2">
              {(["equal", "custom"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setWeightMode(mode)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                    weightMode === mode
                      ? "border-primary bg-primary/8 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/40",
                  )}
                >
                  {mode === "equal" ? "Equal weight" : "Custom weights"}
                </button>
              ))}
            </div>
            {weightMode === "custom" && (
              <div className="mt-2 space-y-1.5">
                {tickerList.map((t) => (
                  <div key={t} className="flex items-center gap-2">
                    <span className="w-16 font-mono text-xs font-semibold">{t}</span>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={customWeights[t] ?? 0}
                      onChange={(e) =>
                        setCustomWeights((w) => ({ ...w, [t]: Number(e.target.value) || 0 }))
                      }
                      className="h-8 w-24 font-mono text-sm"
                    />
                    <span className="text-xs text-muted-foreground">%</span>
                  </div>
                ))}
                <div className={cn("mt-1 text-xs font-medium", weightValid ? "text-emerald-600" : "text-red-500")}>
                  Total: {totalWeight.toFixed(1)}% {weightValid ? "✓" : `(should be 100.0%)`}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Capital + costs */}
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">Starting capital (USD)</span>
            <Input
              type="number"
              min={1000}
              max={100_000_000}
              step={1000}
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value) || 0)}
              className="mt-1.5 font-mono text-sm"
            />
            {!capitalValid && (
              <span className="mt-0.5 block text-[11px] text-red-500">
                Must be between $1,000 and $100M
              </span>
            )}
          </label>
          <div>
            <span className="text-xs font-medium text-muted-foreground">Transaction costs</span>
            <div className="mt-1.5 flex items-center gap-3">
              <button
                type="button"
                onClick={() => setCostEnabled((v) => !v)}
                className={cn(
                  "relative h-6 w-10 rounded-full transition-colors",
                  costEnabled ? "bg-primary" : "bg-border",
                )}
                aria-pressed={costEnabled}
              >
                <span
                  className={cn(
                    "absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
                    costEnabled ? "left-5" : "left-1",
                  )}
                />
              </button>
              <span className="text-xs text-muted-foreground">
                {costEnabled ? "Included in backtest" : "Not modelled"}
              </span>
            </div>
            {costEnabled && (
              <Input
                type="number"
                min={0}
                max={100}
                step={1}
                value={costBps}
                onChange={(e) => setCostBps(Number(e.target.value) || 0)}
                className="mt-2 h-8 w-28 font-mono text-sm"
                aria-label="Transaction cost in basis points"
              />
            )}
          </div>
        </div>
      </Section>

      {/* WHEN OUT — read-only */}
      <Section
        icon={<ArrowRight className="h-4 w-4" />}
        title="When out"
        subtitle="The signal that triggers a sell"
        readOnly
      >
        <p className="text-sm leading-relaxed text-foreground/85">{whenOut}</p>
      </Section>

      {/* PR-E (2026-05-24): inline disclaimer at the commit point —
          the user is about to run a backtest; remind them what the
          result actually means. The full banner appears on the
          results screen; here we use the compact inline variant. */}
      <ResultsDisclaimer variant="inline" className="pt-2" />

      {/* CTA */}
      <div className="flex justify-end pt-2">
        <Button onClick={submit} disabled={!canContinue} size="lg" className="gap-2">
          Preview strategy <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function Section({
  icon,
  title,
  subtitle,
  readOnly,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  readOnly?: boolean;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section
      className={cn(
        "rounded-2xl border p-4",
        readOnly ? "border-border bg-muted/20" : "border-border bg-card",
      )}
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            {icon}
            {title}
          </div>
          {subtitle && (
            <div className="mt-0.5 text-xs text-muted-foreground">{subtitle}</div>
          )}
        </div>
        {readOnly && (
          <span className="rounded-full border border-border bg-background px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Template-defined
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

/** Derive plain-English entry signal copy from a template's strategy
 *  JSON when no explicit `whenInCopy` is set. Best-effort — explicit
 *  copy on the template is always preferred. */
function deriveWhenIn(template: ResearchTemplate, wizardStrategy?: WizardStrategy): string {
  // Prefer the wizard strategy's blurb when present — it's tuned for retail.
  if (wizardStrategy) return wizardStrategy.blurb;
  const t = template.strategy.strategy_type as string;
  switch (t) {
    case "moving_average_filter":
      return "Hold when the asset's price is above a long moving average (e.g. 200-day). Otherwise sit in cash.";
    case "moving_average_crossover":
      return "Go long when the fast moving average (e.g. 50-day) crosses above the slow moving average (e.g. 200-day).";
    case "time_series_momentum":
      return "Hold when the asset's trailing 12-month return is positive. Otherwise sit in cash.";
    case "cross_sectional_momentum":
      return "Each rebalance, rank the universe by past-12-month return (skip last month). Hold the top decile.";
    case "rsi_mean_reversion":
      return "Buy when RSI(14) drops below 30 (oversold). Wait to exit until RSI crosses back above 60.";
    case "bollinger_mean_reversion":
      return "Buy when price falls below the lower Bollinger band (mean − 2σ). Wait for price to revert to the mean.";
    case "breakout":
      return "Go long when price closes above its N-day high (e.g. 60-day breakout).";
    case "sector_rotation":
      return "Each rebalance, hold the top-3 of 11 sector ETFs by their trailing 6-month return.";
    case "dual_momentum":
      return "Pick the best of a small set (e.g. SPY/EFA/AGG) by 12-month return. If best return is negative, go to bonds/cash.";
    case "pairs_trading":
      return "Long the cheaper leg of a cointegrated pair when the spread z-score < −2.";
    default:
      return template.description;
  }
}

/** Derive plain-English exit signal copy. Same fallback pattern. */
function deriveWhenOut(template: ResearchTemplate, wizardStrategy?: WizardStrategy): string {
  if (wizardStrategy?.example) return wizardStrategy.example;
  const t = template.strategy.strategy_type as string;
  switch (t) {
    case "moving_average_filter":
      return "Sell when price drops back below the moving average. Return to cash until the signal re-fires.";
    case "moving_average_crossover":
      return "Sell when the fast MA crosses back below the slow MA.";
    case "time_series_momentum":
      return "Sell when the trailing 12-month return turns negative.";
    case "cross_sectional_momentum":
    case "sector_rotation":
    case "dual_momentum":
      return "Re-rank at each rebalance. Names that fall out of the top decile are sold; new top names are bought.";
    case "rsi_mean_reversion":
      return "Sell when RSI(14) crosses above 60, or stop out at −7% from entry.";
    case "bollinger_mean_reversion":
      return "Sell when price returns to the mean (SMA), or stop out at −7% from entry.";
    case "breakout":
      return "Sell when price closes below its N-day low (e.g. 20-day exit window).";
    case "pairs_trading":
      return "Close the position when the spread reverts to its mean (z-score back to 0).";
    default:
      return "Sell when the entry signal flips, or your stop-loss triggers.";
  }
}
