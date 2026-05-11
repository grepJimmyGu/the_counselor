"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import { getCompanyOverview } from "@/lib/api";
import type { CompanyOverviewResponse } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Route } from "next";

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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [data, setData] = useState<CompanyOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    getCompanyOverview(ticker.toUpperCase())
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load company data"))
      .finally(() => setLoading(false));
  }, [ticker]);

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
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-12 text-center">
          <p className="text-muted-foreground">{error || "Company not found"}</p>
          <Link href={"/stocks" as Route} className="mt-4 inline-block text-sm text-primary hover:underline">← Back to Screener</Link>
        </div>
      </main>
    );
  }

  const fc = data.financial_check;
  const bm = data.business_map;
  const mp = data.market_position;

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
            <Button disabled size="sm" title="Sign in to add — coming soon">Watchlist</Button>
          </div>
        </div>

        {/* Score strip */}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Financial Score</div>
            <div className="mt-2"><ScoreBar score={fc.financial_validation_score} /></div>
            <div className="mt-1 text-xs text-muted-foreground">{fc.financial_validation_label}</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Valuation Risk</div>
            <div className="mt-2"><ScoreBar score={fc.valuation_risk_score} invert /></div>
            <div className="mt-1 text-xs text-muted-foreground">{fc.valuation_risk_score > 70 ? "High" : fc.valuation_risk_score > 40 ? "Moderate" : "Reasonable"}</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Overall (financial only)</div>
            <div className="mt-2"><ScoreBar score={fc.overall_score} /></div>
            <div className="mt-1 text-xs text-muted-foreground">Business analysis pending — PRD-08b</div>
          </div>
        </div>

        {/* Warnings */}
        {fc.warnings.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {fc.warnings.map((w) => (
              <div key={w} className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                <AlertTriangle className="h-3 w-3" />
                {w}
              </div>
            ))}
          </div>
        )}

        {/* Two-column layout: sections */}
        <div className="space-y-5">

          {/* ── Section 1: Business Map ─────────────────────────────────── */}
          <section className="rounded-xl border border-border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
              <div className="h-2 w-2 rounded-full bg-primary" />
              <h2 className="font-heading text-sm font-semibold">Business Map</h2>
              <Badge variant="outline" className="ml-auto text-[10px] font-mono">Partial · {bm.confidence}</Badge>
            </div>
            <div className="p-5 space-y-4">
              {bm.one_line_summary && (
                <p className="text-sm leading-relaxed text-foreground/80">{bm.one_line_summary}</p>
              )}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Value Chain Role</div>
                  <div className="mt-1 text-sm font-semibold">{bm.primary_value_chain_role || "—"}</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Cyclicality</div>
                  <div className="mt-1 text-xs leading-relaxed text-foreground/70">{bm.cyclicality_implication || "—"}</div>
                </div>
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Margin Implication</div>
                  <div className="mt-1 text-xs leading-relaxed text-foreground/70">{bm.margin_implication || "—"}</div>
                </div>
              </div>
              <div className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
                Revenue model, customer types, pricing power: data pending — available when 10-K/10-Q analysis is added
              </div>
            </div>
          </section>

          {/* ── Section 2: Market Position ──────────────────────────────── */}
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
              <div className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-2.5 text-xs text-muted-foreground">
                Market size, growth, competitive position, market share, growth drivers, risks: data pending — available when 10-K/10-Q analysis is added
              </div>
            </div>
          </section>

          {/* ── Section 3: Financial Check ──────────────────────────────── */}
          <section className="rounded-xl border border-border bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
              <div className={cn("h-2 w-2 rounded-full", fc.financial_validation_score >= 60 ? "bg-[var(--profit)]" : fc.financial_validation_score >= 40 ? "bg-[var(--warning-amber)]" : "bg-[var(--loss)]")} />
              <h2 className="font-heading text-sm font-semibold">Financial Check</h2>
              <Badge variant="outline" className="ml-auto text-[10px] font-mono">{fc.confidence} · FMP data</Badge>
            </div>
            <div className="p-5">
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
          </section>
        </div>

        {/* Disclaimer */}
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/70" />
          {data.disclaimer}
        </div>

      </div>
    </main>
  );
}
