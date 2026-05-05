"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, ShieldCheck } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface QAIssue {
  severity: "P0" | "P1" | "P2";
  title: string;
  area: string;
  is_confirmed: boolean;
  reproduction_steps: string[];
  expected_behavior: string;
  actual_behavior: string;
  risk_to_user_trust: string;
  suggested_fix: string;
}

interface QAReviewResponse {
  executive_verdict: string;
  issues: QAIssue[];
  regression_test_checklist: string[];
  release_recommendation: "ship" | "hold" | "ship_with_caution";
  release_recommendation_rationale: string;
  missing_evidence: string[];
}

interface QAReviewRequest {
  product: string;
  review_type: string;
  area_to_review: string;
  current_user_flow: string;
  recent_change: string;
  known_concerns: string;
  available_evidence: string;
  locale: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_USER_FLOW = `1. User lands on the website
2. User selects or enters a stock/commodity ticker
3. User asks AI to create a strategy (chat or markdown upload)
4. User reviews the proposed strategy in the Strategy Preview panel
5. User runs a historical backtest
6. User views performance results (equity curve, metrics, trade log)
7. User reads AI explanation of the results
8. User reads sandbox review / challenge layer`;

const REVIEW_TYPES = [
  "Full product flow",
  "Specific page",
  "Recent code change",
  "Backtest output",
  "Ticker data issue",
  "Release readiness",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function severityColor(s: string) {
  if (s === "P0") return "border-rose-500/70 text-rose-400 bg-rose-500/10";
  if (s === "P1") return "border-yellow-500/70 text-yellow-400 bg-yellow-500/10";
  return "border-blue-500/70 text-blue-400 bg-blue-500/10";
}

function recommendationColor(r: string) {
  if (r === "ship") return "border-emerald-500/70 text-emerald-400 bg-emerald-500/10";
  if (r === "hold") return "border-rose-500/70 text-rose-400 bg-rose-500/10";
  return "border-yellow-500/70 text-yellow-400 bg-yellow-500/10";
}

function recommendationLabel(r: string) {
  if (r === "ship") return "Ship";
  if (r === "hold") return "Hold";
  return "Ship with Caution";
}

async function submitQAReview(req: QAReviewRequest): Promise<QAReviewResponse> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";
  const res = await fetch(`${base}/api/qa/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`QA review failed: ${res.status}`);
  return res.json();
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QAPage() {
  const [form, setForm] = useState<QAReviewRequest>({
    product: "Livermore Investment Analytics Tool",
    review_type: "Full product flow",
    area_to_review: "End-to-end user flow: ticker → strategy → backtest → explanation → sandbox",
    current_user_flow: DEFAULT_USER_FLOW,
    recent_change: "",
    known_concerns: "",
    available_evidence: "",
    locale: "en",
  });

  const [result, setResult] = useState<QAReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(key: keyof QAReviewRequest, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await submitQAReview(form);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const p0 = result?.issues.filter((i) => i.severity === "P0") ?? [];
  const p1 = result?.issues.filter((i) => i.severity === "P1") ?? [];
  const p2 = result?.issues.filter((i) => i.severity === "P2") ?? [];

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8 space-y-8">

        {/* Header */}
        <div className="space-y-2 border-b border-border pb-6">
          <div className="flex items-center gap-2">
            <Badge className="bg-primary/15 text-primary hover:bg-primary/15">Livermore</Badge>
            <Badge variant="outline">QA Agent</Badge>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">QA Review</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Submit a QA review request. The agent examines the product flow, identifies P0/P1/P2
            issues with reproduction steps and fixes, and gives a release recommendation.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Row 1: review type + locale */}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm">
              <span className="text-muted-foreground font-medium">Review Type</span>
              <select
                value={form.review_type}
                onChange={(e) => update("review_type", e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {REVIEW_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <label className="space-y-1.5 text-sm">
              <span className="text-muted-foreground font-medium">Report Language</span>
              <select
                value={form.locale}
                onChange={(e) => update("locale", e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="en">English</option>
                <option value="zh">中文</option>
              </select>
            </label>
          </div>

          {/* Area to review */}
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Area to Review</span>
            <input
              type="text"
              value={form.area_to_review}
              onChange={(e) => update("area_to_review", e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="e.g. ticker selection flow, backtest result page, sandbox review layer"
            />
          </label>

          {/* User flow */}
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Current User Flow</span>
            <textarea
              value={form.current_user_flow}
              onChange={(e) => update("current_user_flow", e.target.value)}
              rows={9}
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-6 text-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          {/* Recent change */}
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Recent Change <span className="text-muted-foreground/60">(optional)</span></span>
            <textarea
              value={form.recent_change}
              onChange={(e) => update("recent_change", e.target.value)}
              rows={4}
              placeholder="Paste what changed — a code diff, feature description, or deploy notes"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          {/* Known concerns */}
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Known Concerns <span className="text-muted-foreground/60">(optional)</span></span>
            <textarea
              value={form.known_concerns}
              onChange={(e) => update("known_concerns", e.target.value)}
              rows={3}
              placeholder="Any bugs, confusing behavior, logs, or user feedback you already know about"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          {/* Available evidence */}
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground font-medium">Available Evidence <span className="text-muted-foreground/60">(optional)</span></span>
            <textarea
              value={form.available_evidence}
              onChange={(e) => update("available_evidence", e.target.value)}
              rows={4}
              placeholder="Screenshots, analytics, error logs, backtest results, API responses, or code diff summaries"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y"
            />
          </label>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" disabled={loading} className="w-full sm:w-auto">
            {loading
              ? <><Loader2 className="h-4 w-4 animate-spin" />Running QA Review…</>
              : <><ShieldCheck className="h-4 w-4" />Run QA Review</>}
          </Button>
        </form>

        {/* Results */}
        {result && (
          <div className="space-y-6 border-t border-border pt-8">

            {/* Verdict + recommendation */}
            <div className="rounded-lg border border-border bg-card/70 p-5 space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <Badge className={`capitalize ${recommendationColor(result.release_recommendation)}`}>
                  {recommendationLabel(result.release_recommendation)}
                </Badge>
                <div className="flex gap-2">
                  {p0.length > 0 && <Badge variant="outline" className="border-rose-500/70 text-rose-400">{p0.length} P0</Badge>}
                  {p1.length > 0 && <Badge variant="outline" className="border-yellow-500/70 text-yellow-400">{p1.length} P1</Badge>}
                  {p2.length > 0 && <Badge variant="outline" className="border-blue-500/70 text-blue-400">{p2.length} P2</Badge>}
                  {result.issues.length === 0 && <Badge variant="outline" className="border-emerald-500/70 text-emerald-400">No issues</Badge>}
                </div>
              </div>
              <p className="text-sm leading-6 text-foreground">{result.executive_verdict}</p>
              <p className="text-xs text-muted-foreground">{result.release_recommendation_rationale}</p>
            </div>

            {/* Issue list */}
            {result.issues.length > 0 && (
              <div className="space-y-4">
                <h2 className="text-sm font-medium">Issues ({result.issues.length})</h2>
                {result.issues.map((issue, i) => (
                  <div key={i} className="rounded-lg border border-border bg-background p-4 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className={`font-mono ${severityColor(issue.severity)}`}>
                        {issue.severity}
                      </Badge>
                      {!issue.is_confirmed && (
                        <Badge variant="outline" className="text-muted-foreground text-xs">Hypothesis</Badge>
                      )}
                      <span className="text-sm font-medium">{issue.title}</span>
                      <span className="text-xs text-muted-foreground">{issue.area}</span>
                    </div>

                    <div className="grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Expected</div>
                        <p className="leading-5">{issue.expected_behavior}</p>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Actual</div>
                        <p className="leading-5 text-rose-300">{issue.actual_behavior}</p>
                      </div>
                    </div>

                    <div>
                      <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Reproduction Steps</div>
                      <ol className="space-y-0.5 text-sm text-muted-foreground">
                        {issue.reproduction_steps.map((step, j) => (
                          <li key={j}>{j + 1}. {step}</li>
                        ))}
                      </ol>
                    </div>

                    <div className="grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Risk to User Trust</div>
                        <p className="leading-5 text-yellow-300">{issue.risk_to_user_trust}</p>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Suggested Fix</div>
                        <p className="leading-5 text-emerald-300">{issue.suggested_fix}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Regression checklist */}
            {result.regression_test_checklist.length > 0 && (
              <div className="rounded-lg border border-border bg-background p-4 space-y-2">
                <h2 className="text-sm font-medium">Regression Test Checklist</h2>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {result.regression_test_checklist.map((item, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-0.5 text-muted-foreground/40">☐</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Missing evidence */}
            {result.missing_evidence.length > 0 && (
              <div className="rounded-lg border border-border bg-background p-4 space-y-2">
                <h2 className="text-sm font-medium">Missing Evidence</h2>
                <p className="text-xs text-muted-foreground mb-2">Providing this would resolve open hypotheses and improve confidence.</p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {result.missing_evidence.map((item, i) => (
                    <li key={i}>• {item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
