"use client";

import { BookOpen, Shield, TrendingUp, BarChart2, Clock, Repeat, FlaskConical, Microscope } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchTemplate, StrategyJson } from "@/lib/contracts";

// ── Evidence tier styles ──────────────────────────────────────────────────────

const TIER_STYLES: Record<string, { pill: string; dot: string; glow: string; label: string }> = {
  A: { pill: "border-emerald-500/60 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500", glow: "shadow-emerald-500/10", label: "Tier A — strong academic evidence replicated across markets" },
  B: { pill: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",         dot: "bg-amber-500",  glow: "shadow-amber-500/10",  label: "Tier B — moderate evidence; mixed results" },
  C: { pill: "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400",     dot: "bg-orange-500",glow: "shadow-orange-500/10", label: "Tier C — practitioner-based evidence" },
};

const HORIZON_LABELS: Record<string, string> = {
  Swing: "Days to weeks",
  Position: "Weeks to months",
  "Multi-quarter": "Quarters+",
  Intraday: "Intraday",
};

// ── Perf context colours (semantic) ──────────────────────────────────────────

const PERF_CONFIGS = [
  { key: "returnRange",  label: "Typical return",    valueClass: "text-emerald-600 dark:text-emerald-400" },
  { key: "sharpeRange",  label: "Risk-adjusted",     valueClass: "text-blue-600 dark:text-blue-400" },
  { key: "worstStretch", label: "Worst stretch",     valueClass: "text-rose-600 dark:text-rose-400" },
] as const;

// ── Layer derivation ──────────────────────────────────────────────────────────

interface Layer { icon: React.ElementType; label: string; value: string }

function deriveCapacityLabel(badge?: string): string {
  if (badge === "Retail") return "Retail-scale";
  if (badge === "Prosumer") return "Prosumer-scale";
  if (badge === "Institutional") return "Institutional-scale";
  return badge ?? "";
}

function deriveLayers(template: ResearchTemplate): Layer[] {
  const s: StrategyJson = template.strategy;
  const rule = s.rules?.[0] ?? {};

  let signalDesc = "Proprietary signal";
  if ("formation_period_days" in rule && rule.formation_period_days) {
    const pct = rule.top_pct ? `top ${Math.round((rule.top_pct as number) * 100)}%` : rule.top_n ? `top ${rule.top_n}` : "top decile";
    const skip = rule.skip_period_days ? `, skip last ${rule.skip_period_days / 21}M` : "";
    signalDesc = `Ranks by ${rule.formation_period_days}-day return (${Math.round((rule.formation_period_days as number) / 21)}M${skip}), holds ${pct}`;
  } else if ("lookback_days" in rule && rule.lookback_days && s.strategy_type === "bollinger_mean_reversion") {
    signalDesc = `Enters below ${rule.num_std ?? 2}× Bollinger Band (${rule.lookback_days}-day), exits at midband`;
  } else if ("lookback_days" in rule && rule.lookback_days && s.strategy_type === "pairs_trading") {
    signalDesc = `z-score entry ${rule.zscore_entry ?? 2.0}, exit ${rule.zscore_exit ?? 0.5}, stop ${rule.zscore_stop ?? 3.0}`;
  } else if ("lookback_days" in rule && rule.lookback_days) {
    signalDesc = `${rule.lookback_days}-day lookback — holds assets with positive absolute return`;
  } else if ("top_n" in rule && rule.top_n) {
    signalDesc = `Ranks by trailing ${rule.ranking_lookback_days ?? 63}-day return, holds top ${rule.top_n}`;
  } else if ("entry_window" in rule && rule.entry_window) {
    signalDesc = `${rule.entry_window}-day high breakout entry, ${rule.exit_window}-day low exit`;
  }

  const freq = s.rebalance_frequency.charAt(0).toUpperCase() + s.rebalance_frequency.slice(1);
  const method = s.position_sizing.method === "equal_weight" ? "Equal dollar per position" : s.position_sizing.method.replace(/_/g, " ");
  const maxPos = s.position_sizing.max_positions;
  const stop = s.risk_management.stop_loss_pct ? ` · ${Math.round(s.risk_management.stop_loss_pct * 100)}% stop-loss` : "";
  const years = Math.round(new Date(s.end_date).getFullYear() - new Date(s.start_date).getFullYear());
  const cost = s.transaction_cost_bps + s.slippage_bps;

  return [
    { icon: BarChart2,    label: "Trades",       value: template.universeDescription },
    { icon: TrendingUp,   label: "Core idea",    value: template.whatItCaptures?.split(".")[0] ?? template.description },
    { icon: Microscope,   label: "How it picks", value: signalDesc },
    { icon: Repeat,       label: "Execution",    value: `${method} · ${freq} rebalance` },
    { icon: Shield,       label: "Protection",   value: maxPos ? `Max ${maxPos} positions${stop} · Long only` : `No hard cap${stop} · Long only` },
    { icon: Clock,        label: "Hold period",  value: template.horizonBadge ? (HORIZON_LABELS[template.horizonBadge] ?? template.horizonBadge) : `${freq} cycle` },
    { icon: FlaskConical, label: "How we test",  value: `Up to ${years} years · ${cost} bps combined cost/slippage` },
    { icon: BookOpen,     label: "After results",value: "Review sector attribution, regime dependence, and parameter sensitivity" },
  ];
}

// ── Component ─────────────────────────────────────────────────────────────────

interface StrategyBriefCardProps {
  template: ResearchTemplate;
  className?: string;
}

export function StrategyBriefCard({ template, className }: StrategyBriefCardProps) {
  const tier = template.evidenceTier ?? "B";
  const tierStyle = TIER_STYLES[tier] ?? TIER_STYLES.B;
  const layers = deriveLayers(template);

  return (
    <div className={cn(
      "overflow-hidden rounded-2xl border border-border bg-card shadow-md",
      tierStyle.glow && `shadow-lg ${tierStyle.glow}`,
      className,
    )}>

      {/* Header — gradient accent */}
      <div className="relative bg-gradient-to-br from-primary/8 via-transparent to-transparent px-5 pt-5 pb-4">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-heading text-xl font-bold tracking-tight">{template.name}</h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span className="capitalize font-medium">{template.category}</span>
              <span className="text-border">·</span>
              <span className="capitalize">{template.strategy.rebalance_frequency}</span>
              {template.capacityBadge && (
                <>
                  <span className="text-border">·</span>
                  <span>{deriveCapacityLabel(template.capacityBadge)}</span>
                </>
              )}
            </div>
          </div>
          <div
            className={cn("shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest cursor-help", tierStyle.pill)}
            title={tierStyle.label}
          >
            <span className={cn("mr-1.5 inline-block h-1.5 w-1.5 rounded-full", tierStyle.dot)} />
            Evidence {tier}
          </div>
        </div>
      </div>

      {/* Performance context strip — color-coded semantics */}
      {template.perfContext && (
        <div className="mx-5 mb-1 grid grid-cols-3 divide-x divide-border overflow-hidden rounded-xl border border-border bg-muted/30">
          {PERF_CONFIGS.map(({ key, label, valueClass }) => (
            <div key={key} className="px-3 py-3">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</div>
              <div className={cn("mt-1 text-sm font-bold leading-snug", valueClass)}>
                {template.perfContext![key]}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 8-layer breakdown — alternating row backgrounds */}
      <div className="divide-y divide-border/50 border-t border-border px-5 mt-3">
        {layers.map(({ icon: Icon, label, value }, i) => (
          <div key={label} className={cn(
            "flex items-start gap-3 py-2.5 transition-colors duration-150",
            i % 2 === 0 ? "bg-transparent" : "bg-muted/20 -mx-5 px-5",
          )}>
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
              {i + 1}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="text-xs font-semibold text-muted-foreground">{label}</span>
              </div>
              <p className="mt-0.5 text-sm leading-snug text-foreground">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Credibility footer */}
      {template.academicRef && (
        <div className="mt-1 border-t border-border bg-gradient-to-br from-muted/40 to-transparent px-5 py-4">
          <div className="flex items-start gap-2.5">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-background">
              <BookOpen className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
            </div>
            <div className="space-y-0.5">
              <p className="text-xs font-semibold text-foreground/70">{template.academicRef.citation}</p>
              <p className="text-xs italic leading-relaxed text-muted-foreground">&ldquo;{template.academicRef.note}&rdquo;</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
