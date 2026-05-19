"use client";

import { BookOpen, Shield, TrendingUp, BarChart2, Clock, Repeat, FlaskConical, Microscope } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchTemplate, StrategyJson } from "@/lib/contracts";

// ── Evidence tier colours ─────────────────────────────────────────────────────

const TIER_STYLES: Record<string, { pill: string; dot: string; label: string }> = {
  A: { pill: "border-emerald-500/60 bg-emerald-500/10 text-emerald-700", dot: "bg-emerald-500", label: "Evidence A — strong academic support" },
  B: { pill: "border-amber-500/60 bg-amber-500/10 text-amber-700", dot: "bg-amber-500", label: "Evidence B — moderate support" },
  C: { pill: "border-orange-500/60 bg-orange-500/10 text-orange-700", dot: "bg-orange-500", label: "Evidence C — practitioner-based" },
};

const HORIZON_LABELS: Record<string, string> = {
  Swing: "Days to weeks",
  Position: "Weeks to months",
  "Multi-quarter": "Quarters+",
  Intraday: "Intraday",
};

// ── 8-layer derivation from template data ─────────────────────────────────────

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

  // Layer 3 — signal description
  let signalDesc = "Proprietary signal";
  if ("formation_period_days" in rule && rule.formation_period_days) {
    const pct = rule.top_pct ? `top ${Math.round((rule.top_pct as number) * 100)}%` : rule.top_n ? `top ${rule.top_n}` : "top decile";
    const skip = rule.skip_period_days ? `, skip last ${rule.skip_period_days / 21}M` : "";
    signalDesc = `Ranks by ${rule.formation_period_days}-day return (${Math.round((rule.formation_period_days as number) / 21)}M${skip}), holds ${pct}`;
  } else if ("lookback_days" in rule && rule.lookback_days && s.strategy_type === "bollinger_mean_reversion") {
    signalDesc = `Enters when price closes below ${rule.num_std ?? 2}× Bollinger Band (${rule.lookback_days}-day window), exits at midband`;
  } else if ("lookback_days" in rule && rule.lookback_days && s.strategy_type === "pairs_trading") {
    signalDesc = `Enters when log-spread z-score > ${rule.zscore_entry ?? 2.0}, exits at ${rule.zscore_exit ?? 0.5}, stop at ${rule.zscore_stop ?? 3.0}`;
  } else if ("lookback_days" in rule && rule.lookback_days) {
    signalDesc = `Signal lookback: ${rule.lookback_days} days — holds assets with positive absolute return`;
  } else if ("top_n" in rule && rule.top_n) {
    signalDesc = `Ranks by trailing ${rule.ranking_lookback_days ?? 63}-day return, holds top ${rule.top_n}`;
  } else if ("entry_window" in rule && rule.entry_window) {
    signalDesc = `Enters on ${rule.entry_window}-day high breakout, exits on ${rule.exit_window}-day low`;
  }

  // Layer 4 — execution
  const freq = s.rebalance_frequency.charAt(0).toUpperCase() + s.rebalance_frequency.slice(1);
  const method = s.position_sizing.method === "equal_weight" ? "Equal dollar per position" : s.position_sizing.method.replace(/_/g, " ");
  const execDesc = `${method} · ${freq} rebalance`;

  // Layer 5 — protection
  const maxPos = s.position_sizing.max_positions;
  const stop = s.risk_management.stop_loss_pct ? ` · ${Math.round(s.risk_management.stop_loss_pct * 100)}% stop-loss` : "";
  const protDesc = maxPos
    ? `Max ${maxPos} positions${stop} · Long only`
    : `No hard position cap${stop} · Long only`;

  // Layer 6 — hold period
  const horizon = template.horizonBadge ? HORIZON_LABELS[template.horizonBadge] ?? template.horizonBadge : freq + " rebalance cycle";

  // Layer 7 — backtest config
  const years = Math.round((new Date(s.end_date).getFullYear() - new Date(s.start_date).getFullYear()));
  const cost = s.transaction_cost_bps + s.slippage_bps;
  const testDesc = `Up to ${years} years of history · ${cost} bps combined cost/slippage per trade`;

  return [
    { icon: BarChart2, label: "Trades",          value: template.universeDescription },
    { icon: TrendingUp, label: "Core idea",       value: template.whatItCaptures?.split(".")[0] ?? template.description },
    { icon: Microscope, label: "How it picks",    value: signalDesc },
    { icon: Repeat,     label: "Execution",       value: execDesc },
    { icon: Shield,     label: "Protection",      value: protDesc },
    { icon: Clock,      label: "Hold period",     value: horizon },
    { icon: FlaskConical, label: "How we test",   value: testDesc },
    { icon: BookOpen,   label: "After results",   value: "Review sector attribution, check regime dependence, run parameter sensitivity" },
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
    <div className={cn("overflow-hidden rounded-2xl border border-border bg-card shadow-sm", className)}>

      {/* Header */}
      <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div className="min-w-0">
          <h3 className="font-heading text-xl font-bold tracking-tight">{template.name}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span className="capitalize">{template.category}</span>
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
          className={cn("shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest", tierStyle.pill)}
          title={tierStyle.label}
        >
          <span className={cn("mr-1.5 inline-block h-1.5 w-1.5 rounded-full", tierStyle.dot)} />
          Evidence {tier}
        </div>
      </div>

      {/* Performance context strip */}
      {template.perfContext && (
        <div className="mx-5 mb-4 grid grid-cols-3 divide-x divide-border overflow-hidden rounded-xl border border-border bg-muted/40">
          {[
            { label: "Typical return", value: template.perfContext.returnRange },
            { label: "Risk-adjusted",  value: template.perfContext.sharpeRange },
            { label: "Worst stretch",  value: template.perfContext.worstStretch },
          ].map(({ label, value }) => (
            <div key={label} className="px-4 py-3">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</div>
              <div className="mt-1 text-sm font-semibold leading-snug">{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 8-layer breakdown */}
      <div className="space-y-0 divide-y divide-border/60 border-t border-border px-5">
        {layers.map(({ icon: Icon, label, value }, i) => (
          <div key={label} className="flex items-start gap-3 py-2.5">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
              {i + 1}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="text-xs font-semibold text-muted-foreground">{label}</span>
              </div>
              <p className="mt-0.5 text-sm leading-snug text-foreground">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Credibility footer */}
      {template.academicRef && (
        <div className="mt-1 border-t border-border bg-muted/30 px-5 py-4">
          <div className="flex items-start gap-2">
            <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <div className="space-y-1">
              <p className="text-xs font-semibold text-muted-foreground">{template.academicRef.citation}</p>
              <p className="text-xs italic leading-relaxed text-muted-foreground">"{template.academicRef.note}"</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
