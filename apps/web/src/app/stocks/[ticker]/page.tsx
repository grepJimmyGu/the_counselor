"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, XCircle, Minus } from "lucide-react";
import { getCompanyOverview } from "@/lib/api";
import type { CompanyOverviewResponse } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricLabel } from "@/components/ui/metric-label";
import { BusinessModelSection } from "./_business-model-section";
import type { Route } from "next";
import { SentimentTab } from "./_sentiment-tab";
import { WatchlistButton } from "@/components/community/watchlist-button";
import { VoteBar } from "@/components/community/vote-bar";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function ScoreBar({ score, invert = false }: { score: number; invert?: boolean }) {
  const color = invert
    ? score > 70 ? "bg-[var(--loss)]" : score > 40 ? "bg-[var(--warning-amber)]" : "bg-[var(--profit)]"
    : score >= 70 ? "bg-[var(--profit)]" : score >= 40 ? "bg-[var(--warning-amber)]" : "bg-[var(--loss)]";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className="w-8 font-mono text-xs font-semibold">{score}</span>
    </div>
  );
}

function MetricRow({ label, value, highlight }: { label: string; value: string; highlight?: "profit" | "loss" | null }) {
  return (
    <div className="flex items-center justify-between border-b border-border/40 py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("font-mono text-sm font-medium",
        highlight === "profit" ? "text-[var(--profit)]" : highlight === "loss" ? "text-[var(--loss)]" : ""
      )}>
        {value}
      </span>
    </div>
  );
}

// ── PRD-08c: Piotroski signal grid ────────────────────────────────────────────

const PIOTROSKI_TOOLTIPS: Record<string, string> = {
  roa_positive: "Return on Assets — net income divided by total assets. Positive means the company earns more than it costs to run its asset base.",
  cash_quality: "Cash Earnings Quality — operating cash flow exceeds net income. Companies where cash exceeds reported profit are less likely to be using aggressive accounting.",
  roa_improving: "Improving Profitability — ROA is rising year over year, indicating the business is becoming more efficient with its assets.",
  cfo_improving: "Operating Cash Flow Growth — the company is generating more cash per unit of assets than last year.",
  leverage_falling: "Falling Leverage — the company reduced its debt-to-equity ratio, lowering financial risk.",
  liquidity_improving: "Improving Liquidity — the current ratio rose, meaning the company can more comfortably cover short-term obligations.",
  no_dilution: "No Share Dilution — share count did not increase, protecting existing shareholders from ownership dilution.",
  gross_margin_improving: "Expanding Gross Margin — the company retained a larger share of each dollar of revenue after direct costs.",
  asset_turnover_improving: "Improving Asset Efficiency — revenue per dollar of assets rose, indicating better operational productivity.",
};

const PIOTROSKI_LABELS: Record<string, string> = {
  roa_positive: "ROA positive",
  cash_quality: "Cash quality",
  roa_improving: "ROA improving",
  cfo_improving: "CFO growth",
  leverage_falling: "Leverage down",
  liquidity_improving: "Liquidity up",
  no_dilution: "No dilution",
  gross_margin_improving: "Gross margin",
  asset_turnover_improving: "Asset turnover",
};

type SignalKey = keyof typeof PIOTROSKI_LABELS;

function PiotroskiSignal({ signalKey, value }: { signalKey: SignalKey; value: boolean | null | undefined }) {
  const label = PIOTROSKI_LABELS[signalKey];
  const tooltip = PIOTROSKI_TOOLTIPS[signalKey];
  return (
    <div className={cn(
      "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
      value === true ? "bg-emerald-50 text-emerald-700" :
      value === false ? "bg-red-50 text-red-600" :
      "bg-muted/50 text-muted-foreground"
    )}>
      {value === true ? (
        <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-600" />
      ) : value === false ? (
        <XCircle className="h-3 w-3 shrink-0 text-red-500" />
      ) : (
        <Minus className="h-3 w-3 shrink-0" />
      )}
      <MetricLabel label={label} tooltip={tooltip} labelClassName="text-xs" />
    </div>
  );
}

// ── Altman Z gauge ────────────────────────────────────────────────────────────

function AltmanZGauge({ z, label }: { z: number; label: string }) {
  // Map Z to position on a 0-100% track: distress <1.81, grey 1.81-2.99, safe >2.99
  // We clamp to [0, 5] for display
  const clamped = Math.min(Math.max(z, 0), 5);
  const pos = (clamped / 5) * 100;
  const color = label === "Safe" ? "bg-[var(--profit)]" : label === "Distress" ? "bg-[var(--loss)]" : "bg-[var(--warning-amber)]";

  return (
    <div className="space-y-1.5">
      <div className="relative h-3 overflow-visible rounded-full bg-gradient-to-r from-red-200 via-amber-200 to-emerald-200">
        <div
          className={cn("absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-md", color)}
          style={{ left: `${pos}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>Distress (&lt;1.81)</span>
        <span>Grey</span>
        <span>Safe (&gt;2.99)</span>
      </div>
    </div>
  );
}

// ── QSV insight panel ─────────────────────────────────────────────────────────

function InsightPanel({ label, color, insight }: { label: string; color: string; insight: string | null | undefined }) {
  if (!insight) return null;
  return (
    <div className={cn("rounded-lg border p-4", color)}>
      <div className="mb-2 text-[10px] font-bold uppercase tracking-widest opacity-70">{label}</div>
      <p className="text-xs leading-relaxed text-foreground/80">{insight}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "overview" | "sentiment";

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = (searchParams.get("tab") as Tab) || "overview";

  const [data, setData] = useState<CompanyOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFinDetails, setShowFinDetails] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    getCompanyOverview(ticker.toUpperCase())
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load company data"))
      .finally(() => setLoading(false));
  }, [ticker]);

  const setTab = (tab: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.push(`/stocks/${ticker}?${params.toString()}` as Route);
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-6">
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </main>
    );
  }

  if (error || !data) {
    const isNotConfigured = error?.includes("403") || error?.includes("not configured");
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-12 text-center">
          <p className="text-base font-medium text-foreground">
            {isNotConfigured ? "Fundamental data unavailable" : "Unable to load company data"}
          </p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {isNotConfigured
              ? "The FMP API key may not be configured or may need a Starter plan."
              : error || "The company may not exist or the backend is unreachable. Try again."}
          </p>
          <div className="mt-5 flex items-center justify-center gap-3">
            <button
              onClick={() => { setError(null); setLoading(true); getCompanyOverview(ticker.toUpperCase()).then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false)); }}
              className="text-sm font-medium text-primary hover:underline"
            >
              Retry
            </button>
            <span className="text-muted-foreground">·</span>
            <Link href={"/stocks" as Route} className="text-sm text-muted-foreground hover:text-foreground hover:underline">← Back to Screener</Link>
          </div>
        </div>
      </main>
    );
  }

  const fc = data.financial_check;
  const bm = data.business_map;
  const mp = data.market_position;
  const hs = data.health_score;

  const signalKeys: SignalKey[] = [
    "roa_positive", "cash_quality", "roa_improving",
    "cfo_improving", "leverage_falling", "liquidity_improving",
    "no_dilution", "gross_margin_improving", "asset_turnover_improving",
  ];

  const piotroskiLabelColor =
    hs.piotroski_label === "Strong" ? "text-emerald-600" :
    hs.piotroski_label === "Good" ? "text-emerald-500" :
    hs.piotroski_label === "Neutral" ? "text-amber-500" :
    hs.piotroski_label === "Weak" ? "text-red-500" :
    "text-muted-foreground";

  const altmanLabelColor =
    hs.altman_z_label === "Safe" ? "text-emerald-600" :
    hs.altman_z_label === "Grey Zone" ? "text-amber-500" :
    hs.altman_z_label === "Distress" ? "text-red-500" :
    "text-muted-foreground";

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-6 px-4 py-6 md:px-6 lg:px-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Link href={"/stocks" as Route} className="hover:text-foreground transition-colors">Stocks</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono font-medium text-foreground">{data.symbol}</span>
        </div>

        {/* Company header */}
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-5 shadow-sm sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-2xl font-bold">{data.symbol}</span>
              {data.price && <span className="font-mono text-xl font-semibold">${data.price.toFixed(2)}</span>}
            </div>
            <div className="mt-1 text-base text-muted-foreground">{data.name}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.sector && <Badge variant="outline" className="text-xs">{data.sector}</Badge>}
              {data.industry && <Badge variant="outline" className="text-xs">{data.industry}</Badge>}
              {data.exchange && <Badge variant="outline" className="font-mono text-xs">{data.exchange}</Badge>}
              {data.market_cap && <Badge variant="outline" className="font-mono text-xs">{fmtMoney(data.market_cap)} mkt cap</Badge>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={`/workspace?prompt=Backtest a strategy on ${data.symbol}` as Route}>
                Run Backtest on {data.symbol}
              </Link>
            </Button>
            <WatchlistButton symbol={data.symbol} />
          </div>
        </div>

        {/* Tab nav */}
        <div className="flex gap-1 rounded-lg border border-border bg-muted/30 p-1">
          {(["overview", "sentiment"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setTab(tab)}
              className={cn(
                "flex-1 rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-all",
                activeTab === tab
                  ? "bg-white shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab === "overview" ? "Overview" : "News & Sentiment"}
            </button>
          ))}
        </div>

        {/* Sentiment tab */}
        {activeTab === "sentiment" && <SentimentTab symbol={ticker.toUpperCase()} />}

        {/* Overview tab content */}
        {activeTab === "overview" && <>

        {/* ── TIER 2: Financial Health Check ─────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-primary" />
            <h2 className="font-heading text-sm font-semibold">Financial Health Check</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">Piotroski · Altman Z</Badge>
          </div>
          <div className="p-5 space-y-5">

            {/* Score cards row */}
            <div className="grid gap-4 sm:grid-cols-2">

              {/* Piotroski F-Score card */}
              <div className="rounded-xl border border-border bg-muted/20 p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <MetricLabel
                    label="Piotroski F-Score"
                    tooltip="The Piotroski F-Score is a 9-point financial quality screen developed by Stanford accounting professor Joseph Piotroski. It identifies financially strengthening companies using nine binary signals across profitability, capital structure, and operating efficiency. Scores of 7–9 indicate strong fundamental health."
                    labelClassName="text-sm font-semibold"
                  />
                  <div className="text-right">
                    {hs.piotroski_score != null ? (
                      <>
                        <span className={cn("font-mono text-2xl font-bold", piotroskiLabelColor)}>
                          {hs.piotroski_score}
                        </span>
                        <span className="font-mono text-sm text-muted-foreground">/9</span>
                        <div className={cn("text-xs font-semibold", piotroskiLabelColor)}>{hs.piotroski_label}</div>
                      </>
                    ) : (
                      <span className="text-sm text-muted-foreground">N/A</span>
                    )}
                  </div>
                </div>

                {/* Signal grid */}
                <div className="grid grid-cols-3 gap-1.5">
                  {signalKeys.map((k) => (
                    <PiotroskiSignal
                      key={k}
                      signalKey={k}
                      value={hs.piotroski_signals[k]}
                    />
                  ))}
                </div>

                {/* Industry percentile */}
                {hs.sector_piotroski_pct != null && hs.sector_piotroski_n != null && (
                  <div className="rounded-md bg-white/60 px-3 py-2 text-xs text-muted-foreground border border-border/40">
                    <span className="font-semibold text-foreground">
                      Top {Math.round(100 - hs.sector_piotroski_pct)}%
                    </span>
                    {" "}among {hs.sector_piotroski_n} {data.sector ?? ""} companies tracked
                  </div>
                )}
              </div>

              {/* Altman Z-Score card */}
              <div className="rounded-xl border border-border bg-muted/20 p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <MetricLabel
                    label="Altman Z-Score"
                    tooltip="The Altman Z-Score, developed by NYU professor Edward Altman in 1968, predicts the probability of corporate bankruptcy within two years. It combines five financial ratios weighted by their predictive power. Scores above 2.99 indicate low distress risk; below 1.81 signals elevated financial risk. Not applicable to financial sector companies."
                    labelClassName="text-sm font-semibold"
                  />
                  <div className="text-right">
                    {hs.altman_z_score != null ? (
                      <>
                        <span className={cn("font-mono text-2xl font-bold", altmanLabelColor)}>
                          {hs.altman_z_score.toFixed(2)}
                        </span>
                        <div className={cn("text-xs font-semibold", altmanLabelColor)}>{hs.altman_z_label}</div>
                      </>
                    ) : (
                      <div className="text-sm text-muted-foreground">N/A</div>
                    )}
                  </div>
                </div>

                {hs.altman_z_score != null ? (
                  <AltmanZGauge z={hs.altman_z_score} label={hs.altman_z_label} />
                ) : hs.altman_z_na_reason ? (
                  <p className="text-xs text-muted-foreground">{hs.altman_z_na_reason}</p>
                ) : null}

                {/* Valuation snapshot */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 pt-1 border-t border-border/40">
                  {hs.ev_ebitda != null && (
                    <div className="flex items-center justify-between">
                      <MetricLabel
                        label="EV/EBITDA"
                        tooltip="Enterprise Value divided by EBITDA — a valuation multiple used to compare companies across capital structures. Lower generally indicates cheaper relative to peers."
                        labelClassName="text-[11px] text-muted-foreground"
                      />
                      <span className="font-mono text-xs font-medium">{hs.ev_ebitda.toFixed(1)}x</span>
                    </div>
                  )}
                  {hs.fcf_yield != null && (
                    <div className="flex items-center justify-between">
                      <MetricLabel
                        label="FCF Yield"
                        tooltip="Free Cash Flow Yield — free cash flow per share divided by price per share. Higher yield means more cash generation relative to market price."
                        labelClassName="text-[11px] text-muted-foreground"
                      />
                      <span className="font-mono text-xs font-medium">{pct(hs.fcf_yield)}</span>
                    </div>
                  )}
                  {hs.pe_ratio != null && (
                    <div className="flex items-center justify-between">
                      <MetricLabel
                        label="P/E"
                        tooltip="Price-to-Earnings ratio — how much investors pay for each dollar of earnings. High P/E may imply growth expectations or overvaluation; low P/E may indicate value or declining prospects."
                        labelClassName="text-[11px] text-muted-foreground"
                      />
                      <span className="font-mono text-xs font-medium">{hs.pe_ratio.toFixed(1)}x</span>
                    </div>
                  )}
                  {hs.peg_ratio != null && (
                    <div className="flex items-center justify-between">
                      <MetricLabel
                        label="PEG"
                        tooltip="Price/Earnings-to-Growth ratio — P/E divided by the EPS growth rate. A PEG below 1 may indicate the stock is undervalued relative to its growth; above 2 suggests the growth is fully priced in."
                        labelClassName="text-[11px] text-muted-foreground"
                      />
                      <span className="font-mono text-xs font-medium">{hs.peg_ratio.toFixed(2)}x</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* QSV Insight panels */}
            {(hs.insight_quality || hs.insight_safety || hs.insight_value) && (
              <div className="grid gap-3 sm:grid-cols-3">
                <InsightPanel
                  label="Q — Quality"
                  color="border-emerald-200 bg-emerald-50/50"
                  insight={hs.insight_quality}
                />
                <InsightPanel
                  label="S — Safety"
                  color="border-blue-200 bg-blue-50/50"
                  insight={hs.insight_safety}
                />
                <InsightPanel
                  label="V — Value"
                  color="border-violet-200 bg-violet-50/50"
                  insight={hs.insight_value}
                />
              </div>
            )}

          </div>
        </section>

        {/* ── Existing Financial Detail (expandable) ──────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <button
            onClick={() => setShowFinDetails((v) => !v)}
            className="flex w-full items-center gap-2 border-b border-border px-5 py-3.5 text-left transition-colors hover:bg-muted/20"
          >
            <div className={cn(
              "h-2 w-2 rounded-full",
              fc.financial_validation_score >= 60 ? "bg-[var(--profit)]" :
              fc.financial_validation_score >= 40 ? "bg-[var(--warning-amber)]" : "bg-[var(--loss)]"
            )} />
            <h2 className="font-heading text-sm font-semibold">Financial Metrics</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">
              Score {fc.financial_validation_score} · {showFinDetails ? "collapse" : "expand"}
            </Badge>
          </button>

          {showFinDetails && (
            <div className="p-5">
              {/* Warnings */}
              {fc.warnings.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {fc.warnings.map((w) => (
                    <div key={w} className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                      <AlertTriangle className="h-3 w-3" />
                      {w}
                    </div>
                  ))}
                </div>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* Growth + Profitability */}
                <div className="space-y-4">
                  <div className="rounded-lg border border-border p-4">
                    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Growth</h3>
                    <MetricRow label="Revenue YoY" value={pct(fc.revenue_yoy)} highlight={fc.revenue_yoy != null ? (fc.revenue_yoy > 0 ? "profit" : "loss") : null} />
                    <MetricRow label="Revenue 3Y CAGR" value={pct(fc.revenue_3y_cagr)} highlight={fc.revenue_3y_cagr != null ? (fc.revenue_3y_cagr > 0 ? "profit" : "loss") : null} />
                    <MetricRow label="EPS YoY" value={pct(fc.eps_yoy)} highlight={fc.eps_yoy != null ? (fc.eps_yoy > 0 ? "profit" : "loss") : null} />
                    {fc.growth_summary && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{fc.growth_summary}</p>}
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Profitability</h3>
                    <MetricRow label="Gross Margin" value={pct(fc.gross_margin)} />
                    <MetricRow label="Operating Margin" value={pct(fc.operating_margin)} highlight={fc.operating_margin != null ? (fc.operating_margin > 0 ? "profit" : "loss") : null} />
                    <MetricRow label="Net Margin" value={pct(fc.net_margin)} highlight={fc.net_margin != null ? (fc.net_margin > 0 ? "profit" : "loss") : null} />
                    <MetricRow label="ROE" value={fc.roe != null ? `${(fc.roe * 100).toFixed(1)}%` : "—"} />
                  </div>
                </div>
                {/* Cash Flow + Balance Sheet + Valuation */}
                <div className="space-y-4">
                  <div className="rounded-lg border border-border p-4">
                    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cash Flow</h3>
                    <MetricRow label="Free Cash Flow" value={fmtMoney(fc.free_cash_flow)} highlight={fc.free_cash_flow != null ? (fc.free_cash_flow > 0 ? "profit" : "loss") : null} />
                    <MetricRow label="FCF Margin" value={pct(fc.fcf_margin)} />
                    <MetricRow label="FCF Conversion" value={fc.fcf_conversion != null ? `${(fc.fcf_conversion * 100).toFixed(0)}%` : "—"} />
                    {fc.cash_flow_summary && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{fc.cash_flow_summary}</p>}
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Balance Sheet</h3>
                    <MetricRow label="Cash" value={fmtMoney(fc.cash)} highlight="profit" />
                    <MetricRow label="Net Debt" value={fmtMoney(fc.net_debt)} highlight={fc.net_debt != null ? (fc.net_debt < 0 ? "profit" : fc.net_debt > 0 ? "loss" : null) : null} />
                    <MetricRow label="Debt / Equity" value={fc.debt_to_equity != null ? `${fc.debt_to_equity.toFixed(2)}x` : "—"} />
                    <MetricRow label="Current Ratio" value={fc.current_ratio != null ? fc.current_ratio.toFixed(2) : "—"} />
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Valuation</h3>
                    <MetricRow label="P/E" value={fc.pe_ratio != null ? `${fc.pe_ratio.toFixed(1)}x` : "—"} />
                    <MetricRow label="P/S" value={fc.ps_ratio != null ? `${fc.ps_ratio.toFixed(1)}x` : "—"} />
                    <MetricRow label="P/B" value={fc.pb_ratio != null ? `${fc.pb_ratio.toFixed(1)}x` : "—"} />
                    <MetricRow label="FCF Yield" value={fc.fcf_yield != null ? pct(fc.fcf_yield) : "—"} />
                    {fc.valuation_summary && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{fc.valuation_summary}</p>}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ── TIER 3: Business Model ────────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-primary" />
            <h2 className="font-heading text-sm font-semibold">Business Model</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">
              {bm.confidence} · {data.revenue_segments.segment_names.length > 0 ? `${data.revenue_segments.segment_names.length} segments` : "FMP data"}
            </Badge>
          </div>
          <div className="p-5">
            <BusinessModelSection seg={data.revenue_segments} bm={bm} />
          </div>
        </section>

        {/* ── Section: Market Position ───────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-[var(--warning-amber)]" />
            <h2 className="font-heading text-sm font-semibold">Market Position</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">Partial · {mp.confidence}</Badge>
          </div>
          <div className="p-5 space-y-3">
            {mp.market_category && (
              <div className="text-sm font-medium">{mp.market_category}</div>
            )}
            {mp.key_competitors.length > 0 && (
              <div>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Peers</div>
                <div className="flex flex-wrap gap-1.5">
                  {mp.key_competitors.map((c) => (
                    <Link key={c} href={`/stocks/${c}` as Route}>
                      <Badge variant="outline" className="cursor-pointer font-mono text-xs hover:border-primary/40 transition-colors">{c}</Badge>
                    </Link>
                  ))}
                </div>
              </div>
            )}
            {(mp.market_growth_label || mp.competitive_position_label || mp.market_size_estimate !== "estimate unavailable") && (
              <div className="grid gap-2 sm:grid-cols-3">
                {mp.market_size_estimate && mp.market_size_estimate !== "estimate unavailable" && mp.market_size_estimate !== "Not disclosed" && (
                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Market Size</div>
                    <div className="mt-1 text-xs font-medium">{mp.market_size_estimate}</div>
                  </div>
                )}
                {mp.market_growth_label && (
                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Market Growth</div>
                    <div className="mt-1 text-xs font-medium capitalize">{mp.market_growth_label}</div>
                  </div>
                )}
                {mp.competitive_position_label && (
                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Position</div>
                    <div className="mt-1 text-xs font-medium capitalize">{mp.competitive_position_label}</div>
                  </div>
                )}
              </div>
            )}
            {mp.key_growth_drivers && mp.key_growth_drivers.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Growth Drivers</div>
                <ul className="space-y-0.5 text-xs text-foreground/70">
                  {mp.key_growth_drivers.map((d: string) => <li key={d} className="flex gap-1.5"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />{d}</li>)}
                </ul>
              </div>
            )}
            {mp.key_risks && mp.key_risks.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Key Risks</div>
                <ul className="space-y-0.5 text-xs text-foreground/70">
                  {mp.key_risks.map((r: string) => <li key={r} className="flex gap-1.5"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />{r}</li>)}
                </ul>
              </div>
            )}
            {mp.confidence === "partial" && (
              <div className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
                Market size, competitive position, and growth drivers sourced from 10-K filing when available
              </div>
            )}
          </div>
        </section>

        {/* Community sentiment */}
        <section className="rounded-xl border border-border bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-heading text-sm font-semibold">Community Sentiment</h2>
          <VoteBar symbol={data.symbol} />
        </section>

        {/* Disclaimer */}
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/70" />
          {data.disclaimer}
        </div>

        </> /* end overview tab */}

      </div>
    </main>
  );
}
