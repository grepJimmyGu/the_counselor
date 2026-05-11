"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Shield,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import type { Route } from "next";
import {
  getSentimentSummary,
  getSentimentNews,
  runSentimentReview,
} from "@/lib/api";
import type {
  NewsArticle,
  SentimentSandboxResponse,
  SentimentSummaryResponse,
} from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// ── Score colors ──────────────────────────────────────────────────────────────

function scoreColor(score: number, invert = false) {
  const hi = invert ? "bg-[var(--loss)]" : "bg-[var(--profit)]";
  const mid = "bg-[var(--warning-amber)]";
  const lo = invert ? "bg-[var(--profit)]" : "bg-[var(--loss)]";
  if (score >= 70) return hi;
  if (score >= 40) return mid;
  return lo;
}

function ScoreBar({ score, invert = false }: { score: number; invert?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", scoreColor(score, invert))}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="w-7 font-mono text-xs font-semibold tabular-nums">{score}</span>
    </div>
  );
}

function TakeawayBadge({ label }: { label: string }) {
  const isPositive = label.toLowerCase().includes("positive") || label.includes("Confirmed");
  const isNegative = label.toLowerCase().includes("risk") || label.includes("Noise") || label.includes("Hype");
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
      isPositive ? "bg-emerald-50 text-emerald-700 border border-emerald-200" :
      isNegative ? "bg-red-50 text-red-700 border border-red-200" :
      "bg-amber-50 text-amber-700 border border-amber-200"
    )}>
      {isPositive ? <TrendingUp className="h-3 w-3" /> : isNegative ? <AlertTriangle className="h-3 w-3" /> : <Zap className="h-3 w-3" />}
      {label}
    </span>
  );
}

function ProviderDot({ status }: { status: string }) {
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full",
      status === "active" ? "bg-emerald-500" :
      status === "rate_limited" ? "bg-amber-400" : "bg-muted-foreground/30"
    )} />
  );
}

function ThemeList({ items, variant }: { items: string[]; variant: "bull" | "bear" }) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-1.5">
      {items.map((t, i) => (
        <span key={i} className={cn(
          "rounded px-2 py-0.5 text-xs",
          variant === "bull" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
        )}>{t}</span>
      ))}
    </div>
  );
}

function SentimentLabel({ label }: { label?: string | null }) {
  if (!label) return <span className="text-muted-foreground">—</span>;
  const isPos = label.toLowerCase().includes("positive") || label.toLowerCase().includes("bullish");
  const isNeg = label.toLowerCase().includes("negative") || label.toLowerCase().includes("bearish") || label.toLowerCase().includes("deteriorating");
  return (
    <span className={cn("font-medium", isPos ? "text-emerald-600" : isNeg ? "text-red-600" : "text-foreground")}>
      {label}
    </span>
  );
}

// ── Article list ──────────────────────────────────────────────────────────────

function ArticleList({ articles }: { articles: NewsArticle[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? articles : articles.slice(0, 5);
  return (
    <div>
      <div className="space-y-2">
        {shown.map((a, i) => (
          <div key={i} className="flex items-start gap-2 rounded-lg border border-border/50 bg-muted/20 p-3">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium leading-tight line-clamp-2">
                {a.url ? (
                  <a href={a.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                    {a.title}
                    <ArrowUpRight className="inline h-3 w-3 ml-0.5 opacity-50" />
                  </a>
                ) : a.title}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>{a.source_name || a.provider}</span>
                {a.published_at && <span>{new Date(a.published_at).toLocaleDateString()}</span>}
                {a.sentiment_label && (
                  <SentimentLabel label={a.sentiment_label} />
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {articles.length > 5 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 flex items-center gap-1 text-xs text-primary hover:underline"
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expanded ? "Show less" : `Show ${articles.length - 5} more`}
        </button>
      )}
    </div>
  );
}

// ── Sandbox review panel ──────────────────────────────────────────────────────

function SandboxPanel({
  symbol,
  summary,
}: {
  symbol: string;
  summary: SentimentSummaryResponse;
}) {
  const [review, setReview] = useState<SentimentSandboxResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const handleRun = async () => {
    setLoading(true);
    setOpen(true);
    try {
      const r = await runSentimentReview(symbol, summary as unknown as object);
      setReview(r);
    } catch {
      setReview({
        review_verdict: "speculative",
        trust_score: 0,
        key_concerns: ["Review failed — please try again."],
        missing_data: [],
        noise_risks: [],
        source_limitations: [],
        required_next_checks: [],
        final_warning: null,
      });
    } finally {
      setLoading(false);
    }
  };

  const verdictColor =
    review?.review_verdict === "trustworthy" ? "text-emerald-600" :
    review?.review_verdict === "promising" ? "text-blue-600" :
    review?.review_verdict === "speculative" ? "text-amber-600" : "text-red-600";

  return (
    <div className="rounded-xl border border-dashed border-border bg-muted/20 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold">AI Sandbox Review</span>
          <Badge variant="outline" className="text-[10px]">Sonnet · On-demand</Badge>
        </div>
        {!open && (
          <Button size="sm" variant="outline" onClick={handleRun} disabled={loading}>
            {loading ? "Running…" : "Run Review"}
          </Button>
        )}
      </div>

      {open && (
        <div className="mt-4 space-y-3">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : review ? (
            <>
              <div className="flex items-center gap-3">
                <span className={cn("text-sm font-bold capitalize", verdictColor)}>{review.review_verdict}</span>
                <ScoreBar score={review.trust_score} />
                <span className="text-xs text-muted-foreground">trust score</span>
              </div>
              {review.key_concerns.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Key Concerns</div>
                  <ul className="space-y-0.5 text-xs text-foreground/80">
                    {review.key_concerns.map((c, i) => <li key={i} className="flex gap-1.5"><XCircle className="h-3 w-3 mt-0.5 shrink-0 text-red-500" />{c}</li>)}
                  </ul>
                </div>
              )}
              {review.required_next_checks.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Next Checks</div>
                  <ul className="space-y-0.5 text-xs text-foreground/80">
                    {review.required_next_checks.map((c, i) => <li key={i} className="flex gap-1.5"><CheckCircle2 className="h-3 w-3 mt-0.5 shrink-0 text-blue-500" />{c}</li>)}
                  </ul>
                </div>
              )}
              {review.final_warning && (
                <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                  <AlertTriangle className="inline h-3 w-3 mr-1" />{review.final_warning}
                </div>
              )}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

// ── Main sentiment tab ────────────────────────────────────────────────────────

export function SentimentTab({ symbol }: { symbol: string }) {
  const [data, setData] = useState<SentimentSummaryResponse | null>(null);
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async (refresh = false) => {
    try {
      const [summary, news] = await Promise.all([
        getSentimentSummary(symbol, refresh),
        getSentimentNews(symbol),
      ]);
      setData(summary);
      setArticles(news);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load sentiment data");
    }
  };

  useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));
  }, [symbol]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData(true).finally(() => setRefreshing(false));
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-border bg-white p-8 text-center">
        <p className="text-sm text-muted-foreground">{error || "No sentiment data available"}</p>
        <Button size="sm" variant="outline" className="mt-3" onClick={() => loadData()}>Retry</Button>
      </div>
    );
  }

  const s = data.scores;
  const cat = data.news_catalyst;
  const sent = data.news_sentiment;
  const comm = data.community_pulse;
  const sig = data.signal_quality_risk;

  return (
    <div className="space-y-5">
      {/* Takeaway card */}
      <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <TakeawayBadge label={data.takeaway.takeaway_label} />
            {data.takeaway.takeaway_summary && (
              <p className="mt-2 text-sm leading-relaxed text-foreground/80">{data.takeaway.takeaway_summary}</p>
            )}
            {data.takeaway.suggested_user_action && (
              <p className="mt-1 text-xs font-medium text-muted-foreground">{data.takeaway.suggested_user_action}</p>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className="text-2xl font-bold font-mono">{s.overall_sentiment_signal_score}</div>
            <div className="text-[10px] text-muted-foreground">/ 100</div>
            <Button
              size="sm"
              variant="ghost"
              className="mt-1 h-6 gap-1 px-2 text-xs"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        </div>

        {/* Provider status */}
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-border/50 pt-3">
          {Object.entries(data.provider_status).map(([name, status]) => (
            <div key={name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <ProviderDot status={status} />
              <span className="capitalize">{name.replace("_", " ")}</span>
              <span className="text-[10px]">({status})</span>
            </div>
          ))}
          {data.as_of_datetime && (
            <span className="ml-auto text-[10px] text-muted-foreground">
              as of {new Date(data.as_of_datetime).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
              <AlertTriangle className="h-3 w-3" />
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Score grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Catalyst", score: s.catalyst_score },
          { label: "Materiality", score: s.catalyst_materiality_score },
          { label: "Source Quality", score: s.information_source_quality_score },
          { label: "News Sentiment", score: s.news_sentiment_score },
          { label: "Community", score: s.community_sentiment_score },
          { label: "Attention", score: s.attention_score },
          { label: "Signal Quality", score: s.signal_quality_score },
          { label: "Risk (inverted)", score: s.risk_score, invert: true },
        ].map(({ label, score, invert }) => (
          <div key={label} className="rounded-lg border border-border bg-white px-3 py-2.5 shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="mt-1.5"><ScoreBar score={score} invert={invert} /></div>
          </div>
        ))}
      </div>

      {/* 4 Section cards */}
      <div className="grid gap-4 lg:grid-cols-2">

        {/* News Catalyst */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <div className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            <span className="text-sm font-semibold">News Catalyst</span>
            {cat.catalyst_materiality_label && (
              <Badge variant="outline" className="ml-auto text-[10px]">{cat.catalyst_materiality_label}</Badge>
            )}
          </div>
          <div className="p-4 space-y-3 text-sm">
            {cat.main_catalyst_summary && (
              <p className="text-sm leading-relaxed">{cat.main_catalyst_summary}</p>
            )}
            <div className="grid grid-cols-2 gap-2">
              {cat.catalyst_type && (
                <div className="rounded-md bg-muted/40 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Type</div>
                  <div className="mt-0.5 text-xs font-medium">{cat.catalyst_type}</div>
                </div>
              )}
              {cat.catalyst_scope && (
                <div className="rounded-md bg-muted/40 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Scope</div>
                  <div className="mt-0.5 text-xs font-medium capitalize">{cat.catalyst_scope.replace("_", " ")}</div>
                </div>
              )}
              {cat.time_horizon && (
                <div className="rounded-md bg-muted/40 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Horizon</div>
                  <div className="mt-0.5 text-xs font-medium capitalize">{cat.time_horizon.replace("_", " ")}</div>
                </div>
              )}
              {cat.information_source_quality_label && (
                <div className="rounded-md bg-muted/40 px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Sources</div>
                  <div className="mt-0.5 text-xs font-medium">{cat.information_source_quality_label}</div>
                </div>
              )}
            </div>
            {cat.expected_business_impact && (
              <p className="text-xs text-muted-foreground">{cat.expected_business_impact}</p>
            )}
            {cat.key_articles.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Key Articles</div>
                {cat.key_articles.slice(0, 3).map((a, i) => (
                  <div key={i} className="text-xs">
                    {a.url ? (
                      <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline line-clamp-1">
                        {a.title}
                      </a>
                    ) : <span className="line-clamp-1">{a.title}</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
              <span>Confidence: {cat.confidence}</span>
            </div>
          </div>
        </section>

        {/* News Sentiment */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <div className={cn("h-1.5 w-1.5 rounded-full",
              sent.news_sentiment_trend === "improving" ? "bg-emerald-500" :
              sent.news_sentiment_trend === "deteriorating" ? "bg-red-500" : "bg-[var(--warning-amber)]"
            )} />
            <span className="text-sm font-semibold">News Sentiment</span>
            {sent.news_sentiment_label && (
              <div className="ml-auto"><SentimentLabel label={sent.news_sentiment_label} /></div>
            )}
          </div>
          <div className="p-4 space-y-3">
            <div className="flex gap-3 text-xs">
              {sent.news_sentiment_trend && (
                <span className="text-muted-foreground">Trend: <span className="font-medium capitalize text-foreground">{sent.news_sentiment_trend}</span></span>
              )}
              {sent.source_diversity && (
                <span className="text-muted-foreground">Sources: <span className="font-medium text-foreground">{sent.source_diversity}</span></span>
              )}
            </div>
            {sent.bullish_news_themes.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Bullish Themes</div>
                <ThemeList items={sent.bullish_news_themes} variant="bull" />
              </div>
            )}
            {sent.bearish_news_themes.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Bearish Themes</div>
                <ThemeList items={sent.bearish_news_themes} variant="bear" />
              </div>
            )}
            {sent.conflicting_news_signals.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Conflicting Signals</div>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {sent.conflicting_news_signals.map((c, i) => <li key={i}>• {c}</li>)}
                </ul>
              </div>
            )}
            <div className="text-[10px] text-muted-foreground">Confidence: {sent.confidence}</div>
          </div>
        </section>

        {/* Community Pulse */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <div className="h-1.5 w-1.5 rounded-full bg-purple-500" />
            <span className="text-sm font-semibold">Community Pulse</span>
            {comm.community_sentiment_label && (
              <Badge variant="outline" className="ml-auto text-[10px]">{comm.community_sentiment_label}</Badge>
            )}
          </div>
          <div className="p-4 space-y-3">
            {comm.confidence === "not_available" || comm.community_sentiment_label === "Not Configured" ? (
              <div className="rounded-md bg-muted/30 px-3 py-4 text-center text-xs text-muted-foreground">
                Community data not configured.<br />
                <Link href={"/sentiment" as Route} className="mt-1 inline-block text-primary hover:underline">
                  Set up Reddit integration →
                </Link>
              </div>
            ) : (
              <>
                {comm.community_attention_trend && (
                  <p className="text-xs text-muted-foreground">
                    Attention: <span className="font-medium capitalize text-foreground">{comm.community_attention_trend}</span>
                    {comm.community_attention_label && ` · ${comm.community_attention_label}`}
                  </p>
                )}
                {comm.bullish_community_themes.length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Bullish</div>
                    <ThemeList items={comm.bullish_community_themes} variant="bull" />
                  </div>
                )}
                {comm.bearish_community_themes.length > 0 && (
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Bearish</div>
                    <ThemeList items={comm.bearish_community_themes} variant="bear" />
                  </div>
                )}
                {comm.dominant_sources.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {comm.dominant_sources.map((s, i) => (
                      <Badge key={i} variant="outline" className="text-[10px]">{s}</Badge>
                    ))}
                  </div>
                )}
              </>
            )}
            <div className="text-[10px] text-muted-foreground">Confidence: {comm.confidence}</div>
          </div>
        </section>

        {/* Signal Quality & Risk */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <div className={cn("h-1.5 w-1.5 rounded-full",
              sig.signal_quality_label?.includes("High") ? "bg-emerald-500" :
              sig.signal_quality_label?.includes("Risk") || sig.signal_quality_label?.includes("Noise") ? "bg-red-500" : "bg-[var(--warning-amber)]"
            )} />
            <span className="text-sm font-semibold">Signal Quality & Risk</span>
            {sig.signal_quality_label && (
              <Badge variant="outline" className="ml-auto text-[10px]">{sig.signal_quality_label}</Badge>
            )}
          </div>
          <div className="p-4 space-y-3 text-xs">
            {sig.materiality_assessment && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Materiality</div>
                <p className="mt-0.5 text-foreground/80">{sig.materiality_assessment}</p>
              </div>
            )}
            {sig.news_community_alignment && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Alignment</div>
                <p className="mt-0.5 text-foreground/80">{sig.news_community_alignment}</p>
              </div>
            )}
            {(sig.crowding_risk || sig.overreaction_risk) && (
              <div className="grid grid-cols-2 gap-2">
                {sig.crowding_risk && (
                  <div className="rounded-md bg-muted/40 px-2.5 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Crowding</div>
                    <div className="mt-0.5 text-xs capitalize">{sig.crowding_risk}</div>
                  </div>
                )}
                {sig.overreaction_risk && (
                  <div className="rounded-md bg-muted/40 px-2.5 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Overreaction</div>
                    <div className="mt-0.5 text-xs capitalize">{sig.overreaction_risk}</div>
                  </div>
                )}
              </div>
            )}
            {sig.headline_risks.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Headline Risks</div>
                <ul className="mt-1 space-y-0.5 text-muted-foreground">
                  {sig.headline_risks.map((r, i) => (
                    <li key={i} className="flex gap-1.5"><AlertTriangle className="h-3 w-3 mt-0.5 shrink-0 text-amber-500" />{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {sig.required_next_checks.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Next Checks</div>
                <ul className="mt-1 space-y-0.5 text-muted-foreground">
                  {sig.required_next_checks.map((c, i) => (
                    <li key={i} className="flex gap-1.5"><CheckCircle2 className="h-3 w-3 mt-0.5 shrink-0 text-blue-400" />{c}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="text-[10px] text-muted-foreground">Confidence: {sig.confidence}</div>
          </div>
        </section>
      </div>

      {/* Raw news list */}
      {articles.length > 0 && (
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <span className="text-sm font-semibold">Source Articles</span>
            <Badge variant="outline" className="text-[10px] font-mono">{articles.length}</Badge>
          </div>
          <div className="p-4">
            <ArticleList articles={articles} />
          </div>
        </section>
      )}

      {/* Sandbox review */}
      <SandboxPanel symbol={symbol} summary={data} />

      {/* Disclaimer */}
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/70" />
        {data.disclaimer}
      </div>
    </div>
  );
}
