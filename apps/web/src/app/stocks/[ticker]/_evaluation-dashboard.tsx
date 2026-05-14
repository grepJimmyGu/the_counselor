"use client";

import { useState, useEffect } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { AlertTriangle, TrendingUp, TrendingDown, Minus, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { MetricLabel } from "@/components/ui/metric-label";
import { getStockTrend } from "@/lib/api";
import type { CompanyOverviewResponse, StockTrendData } from "@/lib/contracts";
import type { StockMetricsInput, QuestionScore, MetricRow, DataQuality } from "@/lib/evaluation/types";
import {
  calculateStockHealthScore,
  calculateStockValuationScore,
  calculateStockTrendScore,
  getFinalScore,
  getFinalLabel,
} from "@/lib/evaluation/scoring";
import {
  interpretStockHealth,
  interpretStockValuation,
  interpretStockTrend,
  buildContradictionWarning,
  buildAnalystSummary,
} from "@/lib/evaluation/interpretation";

// ── Small sub-components ──────────────────────────────────────────────────────

function DataQualityBadge({ quality }: { quality: DataQuality }) {
  const config = {
    live: { label: "Live", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    estimated: { label: "Estimated", className: "bg-amber-50 text-amber-700 border-amber-200" },
    mocked: { label: "Mock", className: "bg-blue-50 text-blue-700 border-blue-200" },
    unavailable: { label: "N/A", className: "bg-muted/50 text-muted-foreground border-border" },
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

function ScoreGauge({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const color = score >= 65 ? "bg-emerald-500" : score >= 42 ? "bg-amber-500" : "bg-red-500";
  const textColor = score >= 65 ? "text-emerald-600" : score >= 42 ? "text-amber-500" : "text-red-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className={cn(
          "font-mono font-bold",
          size === "lg" ? "text-3xl" : size === "md" ? "text-xl" : "text-base",
          textColor
        )}>
          {score}
        </span>
        <span className="text-[10px] text-muted-foreground font-mono">/ 100</span>
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
      status === "strong" ? "bg-emerald-50 text-emerald-700" :
      status === "neutral" ? "bg-amber-50 text-amber-700" :
      "bg-red-50 text-red-600"
    )}>
      {status === "strong" ? <TrendingUp className="h-2.5 w-2.5" /> :
       status === "neutral" ? <Minus className="h-2.5 w-2.5" /> :
       <TrendingDown className="h-2.5 w-2.5" />}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function MiniSparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null;
  const chartData = data.map((v, i) => ({ i, v }));
  const isUp = data[data.length - 1] > data[0];
  return (
    <ResponsiveContainer width={48} height={20}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          dot={false}
          stroke={isUp ? "#10b981" : "#ef4444"}
          strokeWidth={1.5}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── QuestionScorecardCard ─────────────────────────────────────────────────────

interface QuestionScorecardCardProps {
  qs: QuestionScore;
  label: string;
  accent: "emerald" | "blue" | "violet";
}

function QuestionScorecardCard({ qs, label, accent }: QuestionScorecardCardProps) {
  const accentDot = accent === "emerald" ? "bg-emerald-500" : accent === "blue" ? "bg-blue-500" : "bg-violet-500";

  return (
    <div className="rounded-xl border border-border bg-white p-4 shadow-sm space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <div className={cn("h-1.5 w-1.5 rounded-full", accentDot)} />
          <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</span>
        </div>
        <StatusChip status={qs.status} />
      </div>

      {/* Question */}
      <p className="text-xs text-muted-foreground italic">{qs.question}</p>

      {/* Score + Answer */}
      <div className="flex items-start gap-3">
        <div className="w-24 shrink-0">
          <ScoreGauge score={qs.score} size="md" />
        </div>
        <p className="text-sm leading-snug text-foreground">{qs.answer}</p>
      </div>

      {/* Top 3 metric pills */}
      <div className="grid grid-cols-3 gap-1.5">
        {qs.topMetrics.map((metric) => (
          <div
            key={metric.name}
            className={cn(
              "rounded-md border px-2 py-1.5 text-center",
              metric.status === "strong" ? "border-emerald-200 bg-emerald-50" :
              metric.status === "neutral" ? "border-amber-200 bg-amber-50" :
              metric.status === "weak" ? "border-red-200 bg-red-50" :
              "border-border bg-muted/30"
            )}
          >
            <div className="truncate text-[9px] font-medium text-muted-foreground">{metric.name}</div>
            <div className={cn(
              "font-mono text-xs font-bold",
              metric.status === "strong" ? "text-emerald-700" :
              metric.status === "neutral" ? "text-amber-700" :
              metric.status === "weak" ? "text-red-600" :
              "text-muted-foreground"
            )}>
              {metric.formatted}
            </div>
          </div>
        ))}
      </div>

      {/* Warning */}
      {qs.warning && (
        <div className="flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
          <span className="text-[10px] leading-relaxed text-amber-700">{qs.warning}</span>
        </div>
      )}
    </div>
  );
}

// ── MetricDetailPanelSection ──────────────────────────────────────────────────

function MetricDetailPanelSection({ qs, label }: { qs: QuestionScore; label: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-border bg-white shadow-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-5 py-3 text-left transition-colors hover:bg-muted/20"
      >
        <span className="text-xs font-semibold text-muted-foreground">{label}</span>
        <div className="ml-auto flex items-center gap-2">
          <StatusChip status={qs.status} />
          {open ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-border px-5 py-4">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="pb-2 text-left font-medium text-muted-foreground w-[180px]">Metric</th>
                  <th className="pb-2 text-right font-medium text-muted-foreground w-[100px]">Value</th>
                  <th className="pb-2 text-center font-medium text-muted-foreground w-[80px]">Status</th>
                  <th className="pb-2 text-left font-medium text-muted-foreground">Interpretation</th>
                  <th className="pb-2 text-center font-medium text-muted-foreground w-[70px]">Quality</th>
                </tr>
              </thead>
              <tbody>
                {qs.topMetrics.map((metric) => (
                  <MetricTableRow key={metric.name} metric={metric} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricTableRow({ metric }: { metric: MetricRow }) {
  return (
    <tr className="border-b border-border/30 last:border-0">
      <td className="py-2.5 pr-4">
        {metric.tooltip ? (
          <MetricLabel
            label={metric.name}
            tooltip={metric.tooltip}
            labelClassName="text-xs"
          />
        ) : (
          <span className="text-xs">{metric.name}</span>
        )}
        {metric.change && (
          <div className="mt-0.5 text-[10px] text-muted-foreground">{metric.change}</div>
        )}
      </td>
      <td className="py-2.5 pr-4 text-right">
        <div className="flex items-center justify-end gap-1.5">
          {metric.sparkline && metric.sparkline.length >= 2 && (
            <MiniSparkline data={metric.sparkline} />
          )}
          <span className={cn(
            "font-mono font-medium",
            metric.status === "strong" ? "text-emerald-700" :
            metric.status === "neutral" ? "text-amber-700" :
            metric.status === "weak" ? "text-red-600" :
            "text-muted-foreground"
          )}>
            {metric.formatted}
          </span>
        </div>
      </td>
      <td className="py-2.5 pr-4 text-center">
        {metric.status ? (
          <StatusChip status={metric.status} />
        ) : (
          <span className="text-[10px] text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2.5 pr-4">
        <span className="text-[11px] leading-relaxed text-muted-foreground">{metric.interpretation}</span>
      </td>
      <td className="py-2.5 text-center">
        <DataQualityBadge quality={metric.quality} />
      </td>
    </tr>
  );
}

// ── FinalAnalystSummaryCard ───────────────────────────────────────────────────

interface FinalAnalystSummaryCardProps {
  overallScore: number;
  overallLabel: string;
  summary: string;
  bull: string;
  bear: string;
  watch: string[];
  contradiction: string | null;
}

function FinalAnalystSummaryCard({
  overallScore,
  overallLabel,
  summary,
  bull,
  bear,
  watch,
  contradiction,
}: FinalAnalystSummaryCardProps) {
  const labelColor =
    overallScore >= 80 ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
    overallScore >= 60 ? "bg-emerald-50/60 text-emerald-600 border-emerald-200/60" :
    overallScore >= 40 ? "bg-amber-50 text-amber-700 border-amber-200" :
    "bg-red-50 text-red-600 border-red-200";

  return (
    <div className="rounded-xl border border-border bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
        <div className="h-2 w-2 rounded-full bg-primary" />
        <h3 className="font-heading text-sm font-semibold">Analyst Summary</h3>
        <span className={cn(
          "ml-auto inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
          labelColor
        )}>
          {overallLabel}
        </span>
      </div>

      <div className="p-5 space-y-4">
        {/* Score + summary row */}
        <div className="flex items-start gap-4">
          <div className="shrink-0 w-32">
            <ScoreGauge score={overallScore} size="lg" />
            <div className="mt-1 text-[10px] text-muted-foreground text-center">Overall Score</div>
          </div>
          <p className="text-sm leading-relaxed text-foreground/80">{summary}</p>
        </div>

        {/* Bull / Bear */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border-l-4 border-emerald-400 bg-emerald-50/50 px-4 py-3">
            <div className="mb-1.5 flex items-center gap-1.5">
              <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">Bull Case</span>
            </div>
            <p className="text-xs leading-relaxed text-foreground/75">{bull}</p>
          </div>
          <div className="rounded-lg border-l-4 border-red-400 bg-red-50/50 px-4 py-3">
            <div className="mb-1.5 flex items-center gap-1.5">
              <TrendingDown className="h-3.5 w-3.5 text-red-500" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-red-600">Bear Case</span>
            </div>
            <p className="text-xs leading-relaxed text-foreground/75">{bear}</p>
          </div>
        </div>

        {/* Key metrics to watch */}
        <div>
          <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Key Metrics to Watch</div>
          <ul className="space-y-1">
            {watch.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-foreground/70">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/50" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Contradiction warning */}
        {contradiction && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <div>
              <div className="mb-0.5 text-[10px] font-bold uppercase tracking-widest text-amber-700">Signal Contradiction</div>
              <p className="text-xs leading-relaxed text-amber-800">{contradiction}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Bridge function ───────────────────────────────────────────────────────────

function bridgeFromOverview(data: CompanyOverviewResponse): StockMetricsInput {
  const fc = data.financial_check;
  const hs = data.health_score;
  return {
    ticker: data.symbol,
    companyName: data.name,
    sector: data.sector ?? null,
    marketCap: data.market_cap ?? null,
    price: data.price ?? null,
    revenueYoy: fc.revenue_yoy ?? null,
    revenue3yCagr: fc.revenue_3y_cagr ?? null,
    grossMargin: fc.gross_margin ?? null,
    operatingMargin: fc.operating_margin ?? null,
    netMargin: fc.net_margin ?? null,
    roe: fc.roe ?? null,
    freeCashFlow: fc.free_cash_flow ?? null,
    fcfMargin: fc.fcf_margin ?? null,
    fcfConversion: fc.fcf_conversion ?? null,
    cash: fc.cash ?? null,
    netDebt: fc.net_debt ?? null,
    debtToEquity: fc.debt_to_equity ?? null,
    currentRatio: fc.current_ratio ?? null,
    interestCoverage: null,
    peRatio: hs.pe_ratio ?? fc.pe_ratio ?? null,
    pegRatio: hs.peg_ratio ?? null,
    evEbitda: hs.ev_ebitda ?? null,
    fcfYield: hs.fcf_yield ?? fc.fcf_yield ?? null,
    psRatio: fc.ps_ratio ?? null,
    pbRatio: fc.pb_ratio ?? null,
    dividendYield: fc.dividend_yield ?? null,
    perf1m: null,
    perf3m: null,
    perf6m: null,
    perf12m: null,
    ma50: null,
    ma200: null,
    rsVsSector: null,
    epsRevisionTrend: null,
    shortInterest: null,
    revenueSeries: (fc.revenue_series ?? []).map((r) => ({
      date: r.date,
      revenue: r.revenue ?? null,
    })),
    marginSeries: fc.margin_series ?? [],
    fcfSeries: (fc.fcf_series ?? []).map((r) => ({
      date: r.date,
      fcf: r.fcf ?? null,
    })),
  };
}

// ── Trend loading skeleton ────────────────────────────────────────────────────

function TrendLoadingCard() {
  return (
    <div className="rounded-xl border border-border bg-white p-5 shadow-sm space-y-3 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-3 w-24 rounded bg-muted" />
        <div className="h-5 w-16 rounded-full bg-muted" />
      </div>
      <div className="h-6 w-12 rounded bg-muted" />
      <div className="h-1.5 w-full rounded-full bg-muted" />
      <div className="h-4 w-3/4 rounded bg-muted" />
      <div className="space-y-1.5">
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-4/5 rounded bg-muted" />
      </div>
    </div>
  );
}

// ── Main exported component ───────────────────────────────────────────────────

interface Props {
  data: CompanyOverviewResponse;
}

function mergeTrend(m: StockMetricsInput, td: StockTrendData): StockMetricsInput {
  return {
    ...m,
    price: td.latest_price ?? m.price,
    perf1m:  td.perf_1m  ?? null,
    perf3m:  td.perf_3m  ?? null,
    perf6m:  td.perf_6m  ?? null,
    perf12m: td.perf_12m ?? null,
    ma50:    td.ma_50    ?? null,
    ma200:   td.ma_200   ?? null,
    // rs vs SPY 3M as a proxy for rsVsSector
    rsVsSector: td.rs_vs_spy_3m ?? null,
    // Sparkline from price_series_90d mapped to revenue-style shape
    revenueSeries: td.price_series_90d.map(p => ({
      date: p.date,
      revenue: p.price,
    })),
  };
}

export function EvaluationDashboard({ data }: Props) {
  const baseMetrics = bridgeFromOverview(data);
  const [trendData, setTrendData] = useState<StockTrendData | null>(null);
  const [trendLoading, setTrendLoading] = useState(true);

  useEffect(() => {
    setTrendLoading(true);
    getStockTrend(data.symbol)
      .then(setTrendData)
      .catch(() => setTrendData(null))
      .finally(() => setTrendLoading(false));
  }, [data.symbol]);

  // Merge live trend data into metrics when available
  const m = trendData ? mergeTrend(baseMetrics, trendData) : baseMetrics;

  const healthScore    = calculateStockHealthScore(m);
  const valuationScore = calculateStockValuationScore(m);
  const trendScore     = calculateStockTrendScore(m);
  const overallScore   = getFinalScore(healthScore, valuationScore, trendScore);
  const overallLabel   = getFinalLabel(overallScore);

  const health      = interpretStockHealth(m, healthScore);
  const valuation   = interpretStockValuation(m, valuationScore);
  const trend       = interpretStockTrend(m, trendScore);
  const contradiction = buildContradictionWarning(healthScore, valuationScore, trendScore);
  const { summary, bull, bear, watch } = buildAnalystSummary(m, health, valuation, trend, overallScore, overallLabel);

  return (
    <div className="space-y-5">
      {/* Three scorecards */}
      <div className="grid gap-4 lg:grid-cols-3">
        <QuestionScorecardCard qs={health}    label="Asset Health"  accent="emerald" />
        <QuestionScorecardCard qs={valuation} label="Valuation"     accent="blue" />
        {trendLoading ? (
          <TrendLoadingCard />
        ) : (
          <QuestionScorecardCard qs={trend} label="Market Trend" accent="violet" />
        )}
      </div>

      {/* Metric detail panels */}
      <MetricDetailPanelSection qs={health}    label="Asset Health — Detailed Metrics" />
      <MetricDetailPanelSection qs={valuation} label="Valuation — Detailed Metrics" />
      {!trendLoading && (
        <MetricDetailPanelSection qs={trend} label="Market Trend — Detailed Metrics" />
      )}

      {/* Final analyst summary — wait for trend before showing final score */}
      {!trendLoading && (
        <FinalAnalystSummaryCard
          overallScore={overallScore}
          overallLabel={overallLabel}
          summary={summary}
          bull={bull}
          bear={bear}
          watch={watch}
          contradiction={contradiction}
        />
      )}
    </div>
  );
}
