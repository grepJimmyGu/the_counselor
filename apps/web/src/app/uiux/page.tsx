"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, Palette } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface UXIssue {
  issue: string;
  why_it_matters: string;
  severity: "High" | "Medium" | "Low";
  suggested_fix: string;
}

interface MissingStates {
  empty_state: string;
  loading_state: string;
  error_state: string;
  invalid_ticker: string;
  failed_backtest: string;
  no_data: string;
}

interface DesignBrief {
  goal: string;
  scope: string;
  components_affected: string[];
  acceptance_criteria: string[];
  what_not_to_change: string[];
}

interface UXReviewResponse {
  ux_verdict: string;
  biggest_confusion_risk: string;
  biggest_trust_risk: string;
  top_issues: UXIssue[];
  layout_changes: string[];
  copy_changes: string[];
  missing_states: MissingStates;
  mobile_concerns: string;
  design_brief: DesignBrief;
  what_not_to_change: string[];
}

interface UXReviewRequest {
  product_context: string;
  current_ui: string;
  proposed_change: string;
  question: string;
  locale: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const LIVERMORE_CURRENT_UI = `Livermore (谋士) — AI-powered investment analytics and backtesting tool. Dark theme, Next.js frontend.

Layout:
- Top bar: Demo picker with quick-start cards split into Equities (AAPL momentum; RSI mean reversion; breakout) and Commodities (GLD/SLV rotation; crude/nat-gas momentum; grain diversification)
- Left column (stacked): Chat Builder (conversational strategy input) → Strategy Doc (markdown upload) → Validation State (JSON parse + data quality badges)
- Right column: Strategy Preview (editable ticker, date range, rebalance period, benchmark) + tabbed Results: Backtest | Explanation | Sandbox Review | Robustness | Comparison
- Backtest tab: equity curve chart, key metrics (total return, Sharpe, max drawdown, win rate), trade log, credibility warnings if metrics are unusually strong
- Explanation tab: AI narrative of why the strategy performed as it did
- Sandbox Review tab: skeptical AI critique — challenges assumptions, flags overfitting and data risks
- Robustness tab: sensitivity sweeps over lookback/rebalance parameters with heatmap
- Separate /qa page: internal QA review agent (not user-facing)

Users: retail investors and quant researchers, non-developers. EN + ZH locales.`;

// ── Helpers ───────────────────────────────────────────────────────────────────

function verdictColor(v: string) {
  if (v === "Strong")                      return "border-emerald-500/70 text-emerald-400 bg-emerald-500/10";
  if (v === "Risky" || v === "Not ready")  return "border-rose-500/70 text-rose-400 bg-rose-500/10";
  return "border-yellow-500/70 text-yellow-400 bg-yellow-500/10";
}

function severityColor(s: string) {
  if (s === "High")   return "border-rose-500/70 text-rose-400 bg-rose-500/10";
  if (s === "Medium") return "border-yellow-500/70 text-yellow-400 bg-yellow-500/10";
  return "border-blue-500/70 text-blue-400 bg-blue-500/10";
}

function stateColor(val: string) {
  if (!val || val.toLowerCase().includes("missing") || val.toLowerCase().includes("not present"))
    return "text-rose-300";
  if (val.toLowerCase().includes("needs") || val.toLowerCase().includes("improve"))
    return "text-yellow-300";
  return "text-muted-foreground";
}

async function submitUXReview(req: UXReviewRequest): Promise<UXReviewResponse> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";
  const res = await fetch(`${base}/api/uiux/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`UX review failed: ${res.status}`);
  return res.json();
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-medium text-foreground">{children}</h2>;
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-border bg-background p-4 space-y-2 ${className}`}>
      {children}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UXReviewPage() {
  const [form, setForm] = useState<UXReviewRequest>({
    product_context: "",
    current_ui: LIVERMORE_CURRENT_UI,
    proposed_change: "",
    question: "",
    locale: "en",
  });

  const [result, setResult] = useState<UXReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(key: keyof UXReviewRequest, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await submitUXReview(form));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const STATE_LABELS: { key: keyof MissingStates; label: string }[] = [
    { key: "empty_state",    label: "Empty state" },
    { key: "loading_state",  label: "Loading state" },
    { key: "error_state",    label: "Error state" },
    { key: "invalid_ticker", label: "Invalid ticker" },
    { key: "failed_backtest",label: "Failed backtest" },
    { key: "no_data",        label: "No data" },
  ];

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8 space-y-8">

        {/* Header */}
        <div className="space-y-2 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/15 text-primary hover:bg-primary/15">Livermore</Badge>
            <Badge variant="outline">UX Expert</Badge>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">UI/UX Review</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Describe a proposed UI change and get a structured expert review focused on clarity,
            trust, and whether users can complete the core flow without being misled by backtest results.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">

          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Current UI State</span>
            <textarea
              value={form.current_ui}
              onChange={(e) => update("current_ui", e.target.value)}
              rows={8}
              required
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Proposed Change</span>
            <textarea
              value={form.proposed_change}
              onChange={(e) => update("proposed_change", e.target.value)}
              rows={4}
              required
              placeholder="e.g. Add 5 research template cards below the demo picker, each opening a pre-structured markdown memo in Strategy Doc"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">UX Question</span>
            <input
              type="text"
              value={form.question}
              onChange={(e) => update("question", e.target.value)}
              required
              placeholder="e.g. Should research templates live alongside demo strategies, or get a dedicated entry point?"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>

          <label className="space-y-1.5 text-sm block">
            <span className="text-muted-foreground font-medium">Report Language</span>
            <select
              value={form.locale}
              onChange={(e) => update("locale", e.target.value)}
              className="w-full sm:w-48 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="en">English</option>
              <option value="zh">中文</option>
            </select>
          </label>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" disabled={loading} className="w-full sm:w-auto">
            {loading
              ? <><Loader2 className="h-4 w-4 animate-spin" />Running UX Review…</>
              : <><Palette className="h-4 w-4" />Run UX Review</>}
          </Button>
        </form>

        {/* Results */}
        {result && (
          <div className="space-y-6 border-t border-border pt-8">

            {/* 1. Verdict */}
            <div className="rounded-lg border border-border bg-card/70 p-5 space-y-3">
              <Badge className={`${verdictColor(result.ux_verdict)}`}>
                {result.ux_verdict}
              </Badge>
              <div className="grid gap-4 sm:grid-cols-2 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Biggest Confusion Risk</div>
                  <p className="leading-5 text-yellow-300">{result.biggest_confusion_risk}</p>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Biggest Trust Risk</div>
                  <p className="leading-5 text-rose-300">{result.biggest_trust_risk}</p>
                </div>
              </div>
            </div>

            {/* 2. Top Issues */}
            {result.top_issues.length > 0 && (
              <div className="space-y-3">
                <SectionTitle>Top Issues ({result.top_issues.length})</SectionTitle>
                {result.top_issues.map((issue, i) => (
                  <Card key={i}>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`font-mono ${severityColor(issue.severity)}`}>
                        {issue.severity}
                      </Badge>
                      <span className="text-sm font-medium">{issue.issue}</span>
                    </div>
                    <div className="grid gap-3 text-sm sm:grid-cols-2 pt-1">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Why it matters</div>
                        <p className="leading-5 text-muted-foreground">{issue.why_it_matters}</p>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Suggested fix</div>
                        <p className="leading-5 text-emerald-300">{issue.suggested_fix}</p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}

            {/* 3. Layout + Copy changes */}
            <div className="grid gap-4 sm:grid-cols-2">
              {result.layout_changes.length > 0 && (
                <Card>
                  <SectionTitle>Layout Changes</SectionTitle>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    {result.layout_changes.map((c, i) => (
                      <li key={i} className="flex gap-2"><span className="text-primary shrink-0">→</span>{c}</li>
                    ))}
                  </ul>
                </Card>
              )}
              {result.copy_changes.length > 0 && (
                <Card>
                  <SectionTitle>Copy Changes</SectionTitle>
                  <ul className="space-y-1.5 text-sm text-muted-foreground">
                    {result.copy_changes.map((c, i) => (
                      <li key={i} className="flex gap-2"><span className="text-primary shrink-0">→</span>{c}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>

            {/* 4. Missing States */}
            <div className="space-y-3">
              <SectionTitle>Missing States</SectionTitle>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {STATE_LABELS.map(({ key, label }) => (
                  <div key={key} className="rounded-md border border-border bg-background px-3 py-2.5 space-y-1">
                    <div className="text-xs text-muted-foreground font-medium">{label}</div>
                    <p className={`text-xs leading-4 ${stateColor(result.missing_states[key])}`}>
                      {result.missing_states[key] || "—"}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* 5. Mobile Concerns */}
            {result.mobile_concerns && (
              <Card>
                <SectionTitle>Mobile Concerns</SectionTitle>
                <p className="text-sm text-muted-foreground leading-5">{result.mobile_concerns}</p>
              </Card>
            )}

            {/* 6. Design Brief */}
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-5 space-y-4">
              <SectionTitle>Implementation-Ready Design Brief</SectionTitle>
              <div className="grid gap-4 sm:grid-cols-2 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Goal</div>
                  <p className="leading-5">{result.design_brief.goal}</p>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Scope</div>
                  <p className="leading-5">{result.design_brief.scope}</p>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Components Affected</div>
                  <ul className="space-y-1 text-muted-foreground">
                    {result.design_brief.components_affected.map((c, i) => <li key={i}>• {c}</li>)}
                  </ul>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Acceptance Criteria</div>
                  <ul className="space-y-1 text-muted-foreground">
                    {result.design_brief.acceptance_criteria.map((c, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-muted-foreground/40 shrink-0">☐</span>{c}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* 7. What Not to Change */}
            {result.what_not_to_change.length > 0 && (
              <Card>
                <SectionTitle>What Not to Change</SectionTitle>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  {result.what_not_to_change.map((c, i) => (
                    <li key={i} className="flex gap-2"><span className="text-emerald-400 shrink-0">✓</span>{c}</li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
