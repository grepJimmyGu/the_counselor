"use client";

import { useState } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import {
  AlertTriangle, TrendingUp, TrendingDown, Minus,
  ChevronDown, ChevronUp, Flame, Droplets, Wheat, Gem,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { MetricLabel } from "@/components/ui/metric-label";
import type { CommodityMetricsInput, QuestionScore, MetricRow, DataQuality } from "@/lib/evaluation/types";
import {
  calculateCommodityHealthScore,
  calculateCommodityValuationScore,
  calculateCommodityTrendScore,
  getFinalScore,
  getFinalLabel,
  getScoreStatus,
} from "@/lib/evaluation/scoring";
import {
  interpretCommodityHealth,
  interpretCommodityValuation,
  interpretCommodityTrend,
  buildCommodityContradictionWarning,
  buildCommodityAnalystSummary,
} from "@/lib/evaluation/commodity-interpretation";

// ── Small sub-components (shared with stock dashboard) ────────────────────────

function DataQualityBadge({ quality }: { quality: DataQuality }) {
  const config = {
    live:        { label: "Live",      className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    estimated:   { label: "Estimated", className: "bg-amber-50 text-amber-700 border-amber-200" },
    mocked:      { label: "Mock",      className: "bg-blue-50 text-blue-700 border-blue-200" },
    unavailable: { label: "N/A",       className: "bg-muted/50 text-muted-foreground border-border" },
  } as const;
  const c = config[quality];
  return (
    <span className={cn(
      "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
      c.className
    )}>
      {c.label}
    </span>
  );
}

function ScoreGauge({ score }: { score: number }) {
  const color    = score >= 65 ? "bg-emerald-500" : score >= 42 ? "bg-amber-500" : "bg-red-500";
  const textColor = score >= 65 ? "text-emerald-600" : score >= 42 ? "text-amber-500" : "text-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className={cn("font-mono text-xl font-bold", textColor)}>{score}</span>
        <span className="font-mono text-[10px] text-muted-foreground">/ 100</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function StatusChip({ status }: { status: "strong" | "neutral" | "weak" }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
      status === "strong" ? "bg-emerald-50 text-emerald-700"
      : status === "neutral" ? "bg-amber-50 text-amber-700"
      : "bg-red-50 text-red-600"
    )}>
      {status === "strong" ? <TrendingUp className="h-2.5 w-2.5" />
       : status === "neutral" ? <Minus className="h-2.5 w-2.5" />
       : <TrendingDown className="h-2.5 w-2.5" />}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function MiniSparkline({ data }: { data?: number[] }) {
  if (!data || data.length < 2) return null;
  const valid = data.filter(v => v > 0);
  if (valid.length < 2) return null;
  const chartData = valid.map((v, i) => ({ i, v }));
  const isUp = valid[valid.length - 1] > valid[0];
  return (
    <ResponsiveContainer width={48} height={20}>
      <LineChart data={chartData}>
        <Line type="monotone" dataKey="v" dot={false} stroke={isUp ? "#10b981" : "#ef4444"} strokeWidth={1.5} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Question Scorecard ────────────────────────────────────────────────────────

const ACCENT_COLORS = {
  amber:  { dot: "bg-amber-500",   border: "border-amber-100", bg: "bg-amber-50/30" },
  blue:   { dot: "bg-blue-500",    border: "border-blue-100",  bg: "bg-blue-50/30" },
  violet: { dot: "bg-violet-500",  border: "border-violet-100", bg: "bg-violet-50/30" },
} as const;
type Accent = keyof typeof ACCENT_COLORS;

function QuestionScorecardCard({
  qs, label, accent,
}: { qs: QuestionScore; label: string; accent: Accent }) {
  const c = ACCENT_COLORS[accent];
  return (
    <div className={cn("rounded-xl border p-4 space-y-3 shadow-sm", c.border, c.bg, "bg-white")}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <div className={cn("h-2 w-2 rounded-full", c.dot)} />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        </div>
        <StatusChip status={qs.status} />
      </div>
      <ScoreGauge score={qs.score} />
      <p className="text-sm font-medium leading-snug text-foreground">{qs.answer}</p>
      <p className="text-[11px] leading-relaxed text-muted-foreground">{qs.explanation}</p>
      {/* Top 3 metrics */}
      <div className="space-y-1 pt-1 border-t border-border/40">
        {qs.topMetrics.slice(0, 3).map((m) => (
          <div key={m.name} className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-muted-foreground truncate">{m.name}</span>
            <span className={cn(
              "font-mono text-[11px] font-semibold shrink-0",
              m.status === "strong" ? "text-emerald-600"
              : m.status === "weak"   ? "text-red-500"
              : "text-foreground"
            )}>
              {m.formatted}
            </span>
          </div>
        ))}
      </div>
      {/* Warning */}
      {qs.warning && (
        <div className="flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50/60 px-2.5 py-1.5 text-[10px] text-amber-700">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {qs.warning}
        </div>
      )}
    </div>
  );
}

// ── Metric Detail Panel ───────────────────────────────────────────────────────

function MetricDetailPanelSection({ qs, label }: { qs: QuestionScore; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-white shadow-sm">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center gap-2 px-5 py-3.5 text-left hover:bg-muted/20 transition-colors"
      >
        <ScoreGauge score={qs.score} />
        <span className="ml-2 flex-1 text-sm font-semibold">{label}</span>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="border-t border-border px-5 py-4 overflow-x-auto">
          <table className="w-full text-xs min-w-[560px]">
            <thead>
              <tr className="border-b border-border text-[10px] text-muted-foreground">
                <th className="pb-2 text-left font-medium w-44">Metric</th>
                <th className="pb-2 text-right font-medium w-28">Value</th>
                <th className="pb-2 text-center font-medium w-16">Status</th>
                <th className="pb-2 text-right font-medium w-12">Quality</th>
                <th className="pb-2 text-left font-medium pl-4">Interpretation</th>
              </tr>
            </thead>
            <tbody>
              {qs.topMetrics.map((m) => (
                <tr key={m.name} className="border-b border-border/30 last:border-0">
                  <td className="py-2.5 pr-2">
                    {m.tooltip
                      ? <MetricLabel label={m.name} tooltip={m.tooltip} labelClassName="text-[11px]" />
                      : <span className="text-[11px]">{m.name}</span>
                    }
                  </td>
                  <td className="py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {m.sparkline && <MiniSparkline data={m.sparkline} />}
                      <span className={cn(
                        "font-mono font-semibold text-[11px]",
                        m.status === "strong" ? "text-emerald-600"
                        : m.status === "weak" ? "text-red-500"
                        : ""
                      )}>
                        {m.formatted}
                      </span>
                    </div>
                  </td>
                  <td className="py-2.5 text-center">
                    {m.status && <StatusChip status={m.status} />}
                  </td>
                  <td className="py-2.5 text-right">
                    <DataQualityBadge quality={m.quality} />
                  </td>
                  <td className="py-2.5 pl-4 text-muted-foreground leading-relaxed">
                    {m.interpretation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Final Summary ─────────────────────────────────────────────────────────────

function FinalAnalystSummaryCard({
  overallScore, overallLabel, summary, bull, bear, watch, contradiction,
}: {
  overallScore: number;
  overallLabel: string;
  summary: string;
  bull: string;
  bear: string;
  watch: string[];
  contradiction: string | null;
}) {
  const scoreColor =
    overallScore >= 68 ? "text-emerald-600"
    : overallScore >= 48 ? "text-amber-500"
    : "text-red-500";
  const labelBg =
    overallLabel === "Attractive" || overallLabel === "Moderately Positive"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : overallLabel === "Neutral"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-red-50 text-red-600 border-red-200";

  return (
    <div className="rounded-xl border border-border bg-white shadow-sm p-5 space-y-4">
      <div className="flex items-center gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Overall Score</div>
          <span className={cn("font-mono text-4xl font-bold", scoreColor)}>{overallScore}</span>
          <span className="font-mono text-sm text-muted-foreground"> / 100</span>
        </div>
        <div className="h-10 w-px bg-border" />
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">View</div>
          <span className={cn("rounded-full border px-3 py-1 text-xs font-semibold", labelBg)}>{overallLabel}</span>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-foreground/80">{summary}</p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border-l-4 border-emerald-400 bg-emerald-50/40 px-4 py-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-emerald-600">Bull Case</div>
          <p className="text-xs leading-relaxed text-foreground/75">{bull}</p>
        </div>
        <div className="rounded-lg border-l-4 border-red-400 bg-red-50/40 px-4 py-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-red-600">Bear Case</div>
          <p className="text-xs leading-relaxed text-foreground/75">{bear}</p>
        </div>
      </div>

      <div>
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Key Metrics to Watch</div>
        <ul className="space-y-1">
          {watch.map((w) => (
            <li key={w} className="flex items-start gap-2 text-xs text-foreground/70">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              {w}
            </li>
          ))}
        </ul>
      </div>

      {contradiction && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-800">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span><span className="font-semibold">Contradiction: </span>{contradiction}</span>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/60">
        Commodity analysis uses mock/estimated data. Scores reflect inventory, supply-demand, futures curve, CFTC positioning, and macro conditions. Not financial advice.
      </p>
    </div>
  );
}

// ── Category icon ─────────────────────────────────────────────────────────────

function CommodityIcon({ category }: { category: string }) {
  if (category === "energy") return <Flame className="h-4 w-4 text-orange-500" />;
  if (category === "metals") return <Gem className="h-4 w-4 text-yellow-500" />;
  if (category === "agriculture") return <Wheat className="h-4 w-4 text-green-600" />;
  return <Droplets className="h-4 w-4 text-blue-500" />;
}

// ── Asset Summary Card ────────────────────────────────────────────────────────

function CommodityAssetCard({ m }: { m: CommodityMetricsInput }) {
  const fmtPct = (v: number | null) =>
    v === null ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

  return (
    <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <CommodityIcon category={m.category} />
            <span className="font-mono text-xl font-bold">{m.symbol}</span>
            <Badge variant="outline" className="text-[10px] capitalize">{m.category}</Badge>
          </div>
          <div className="text-base text-muted-foreground">{m.name}</div>
        </div>
        <div className="text-right">
          {m.spotPrice != null && (
            <div className="font-mono text-2xl font-bold">
              ${m.spotPrice.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<span className="text-sm text-muted-foreground">/{m.unit}</span>
            </div>
          )}
          {m.perf1d != null && (
            <div className={cn("font-mono text-sm font-medium", m.perf1d >= 0 ? "text-emerald-600" : "text-red-500")}>
              {fmtPct(m.perf1d)} 1D
            </div>
          )}
        </div>
      </div>
      {/* Snapshot metrics */}
      <div className="mt-3 grid grid-cols-4 gap-3 border-t border-border/40 pt-3">
        {[
          { label: "1M", value: fmtPct(m.perf1m) },
          { label: "3M", value: fmtPct(m.perf3m) },
          { label: "12M", value: fmtPct(m.perf12m) },
          { label: "Futures Curve", value: m.futuresCurve ? m.futuresCurve.charAt(0).toUpperCase() + m.futuresCurve.slice(1) : "—" },
          { label: "Inventory", value: m.inventoryPercentile != null ? `${Math.round(m.inventoryPercentile)}th pct` : "—" },
          { label: "Supply/Demand", value: m.supplyDemandLabel ? m.supplyDemandLabel.charAt(0).toUpperCase() + m.supplyDemandLabel.slice(1) : "—" },
          { label: "CFTC Position", value: m.cftcPositioningPct != null ? `${Math.round(m.cftcPositioningPct)}th pct` : "—" },
          { label: "Spare Capacity", value: m.spareCapacity ? m.spareCapacity.charAt(0).toUpperCase() + m.spareCapacity.slice(1) : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-muted/30 px-3 py-2">
            <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="mt-0.5 font-mono text-xs font-medium">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main exported component ───────────────────────────────────────────────────

interface Props {
  m: CommodityMetricsInput;
}

export function CommodityEvaluationDashboard({ m }: Props) {
  const healthScore    = calculateCommodityHealthScore(m);
  const valuationScore = calculateCommodityValuationScore(m);
  const trendScore     = calculateCommodityTrendScore(m);
  const overallScore   = getFinalScore(healthScore, valuationScore, trendScore);
  const overallLabel   = getFinalLabel(overallScore);

  const health      = interpretCommodityHealth(m, healthScore);
  const valuation   = interpretCommodityValuation(m, valuationScore);
  const trend       = interpretCommodityTrend(m, trendScore);
  const contradiction = buildCommodityContradictionWarning(healthScore, valuationScore, trendScore, m);
  const { summary, bull, bear, watch } = buildCommodityAnalystSummary(
    m, health, valuation, trend, overallScore, overallLabel
  );

  return (
    <div className="space-y-5">
      {/* Asset summary */}
      <CommodityAssetCard m={m} />

      {/* Three scorecards */}
      <div className="grid gap-4 lg:grid-cols-3">
        <QuestionScorecardCard qs={health}    label="Physical Market Health" accent="amber" />
        <QuestionScorecardCard qs={valuation} label="Valuation"              accent="blue" />
        <QuestionScorecardCard qs={trend}     label="Market Trend"           accent="violet" />
      </div>

      {/* Detail panels */}
      <MetricDetailPanelSection qs={health}    label="Physical Market Health — Detailed Metrics" />
      <MetricDetailPanelSection qs={valuation} label="Valuation — Detailed Metrics" />
      <MetricDetailPanelSection qs={trend}     label="Market Trend — Detailed Metrics" />

      {/* Final summary */}
      <FinalAnalystSummaryCard
        overallScore={overallScore}
        overallLabel={overallLabel}
        summary={summary}
        bull={bull}
        bear={bear}
        watch={watch}
        contradiction={contradiction}
      />
    </div>
  );
}
