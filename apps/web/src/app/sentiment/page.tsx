"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Search,
  XCircle,
  Zap,
} from "lucide-react";
import type { Route } from "next";
import {
  getProvidersStatus,
  getSentimentToolkits,
  runSentimentAnalyze,
} from "@/lib/api";
import type {
  ProvidersStatusResponse,
  SentimentAnalyzeResponse,
  SentimentCandidateResult,
  SentimentToolkit,
} from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// ── Default watchlist for toolkit demos ──────────────────────────────────────

const DEFAULT_SYMBOLS = [
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "UNH",
  "JNJ", "PG", "HD", "MA", "BAC", "XOM", "ABBV", "PFE", "LLY", "COST",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function ProviderStatusBadge({ name, status }: { name: string; status: string }) {
  const isActive = status === "active";
  const isLimited = status === "rate_limited";
  return (
    <div className={cn(
      "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs",
      isActive ? "bg-emerald-50 border border-emerald-200 text-emerald-700" :
      isLimited ? "bg-amber-50 border border-amber-200 text-amber-700" :
      "bg-muted border border-border text-muted-foreground"
    )}>
      {isActive ? <CheckCircle2 className="h-3 w-3" /> : isLimited ? <AlertTriangle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      <span className="capitalize font-medium">{name.replace(/_/g, " ")}</span>
      <span className="opacity-60">({status})</span>
    </div>
  );
}

function ScoreChip({ score }: { score: number }) {
  const color = score >= 70 ? "text-emerald-600 bg-emerald-50 border-emerald-200"
    : score >= 50 ? "text-amber-600 bg-amber-50 border-amber-200"
    : "text-red-600 bg-red-50 border-red-200";
  return (
    <span className={cn("inline-flex items-center justify-center w-9 h-9 rounded-full border font-mono text-sm font-bold", color)}>
      {score}
    </span>
  );
}

function CandidateRow({ c, onNavigate }: { c: SentimentCandidateResult; onNavigate: (sym: string) => void }) {
  const isBull = c.overall_label.includes("Positive") || c.overall_label.includes("Confirmed");
  const isBear = c.overall_label.includes("Risk") || c.overall_label.includes("Noise") || c.overall_label.includes("Hype");
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-white px-4 py-3 shadow-sm hover:border-primary/30 transition-colors">
      <ScoreChip score={c.overall_sentiment_signal_score} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate(c.symbol)}
            className="font-mono text-sm font-bold hover:underline"
          >
            {c.symbol}
          </button>
          <Badge variant="outline" className={cn("text-[10px]",
            isBull ? "border-emerald-200 text-emerald-700" :
            isBear ? "border-red-200 text-red-700" : ""
          )}>
            {c.overall_label}
          </Badge>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          {c.takeaway_label && <span>{c.takeaway_label}</span>}
          {c.catalyst_materiality_label && <span>· {c.catalyst_materiality_label}</span>}
          {c.news_sentiment_label && <span>· {c.news_sentiment_label}</span>}
        </div>
        {c.bullish_themes.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {c.bullish_themes.slice(0, 3).map((t, i) => (
              <span key={i} className="rounded px-1.5 py-0.5 text-[10px] bg-emerald-50 text-emerald-700">{t}</span>
            ))}
          </div>
        )}
      </div>
      <Button
        asChild
        size="sm"
        variant="ghost"
        className="shrink-0"
      >
        <Link href={`/stocks/${c.symbol}?tab=sentiment` as Route}>
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Button>
    </div>
  );
}

// ── Toolkit card ──────────────────────────────────────────────────────────────

function ToolkitCard({
  toolkit,
  onRun,
  running,
}: {
  toolkit: SentimentToolkit;
  onRun: (id: string) => void;
  running: boolean;
}) {
  const isWatchlist = toolkit.name.toLowerCase().includes("watchlist");
  const iconClass = toolkit.id.includes("risk") || toolkit.id.includes("hype")
    ? "text-red-500" : toolkit.id.includes("catalyst") || toolkit.id.includes("confirmed")
    ? "text-emerald-500" : "text-amber-500";

  return (
    <div className="flex flex-col rounded-xl border border-border bg-white p-4 shadow-sm hover:border-primary/30 transition-colors">
      <div className="flex items-start gap-3">
        <div className={cn("mt-0.5 shrink-0", iconClass)}>
          <Zap className="h-4 w-4" />
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{toolkit.name}</div>
          <div className="mt-1 text-xs text-muted-foreground leading-relaxed">{toolkit.description}</div>
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="mt-4"
        onClick={() => onRun(toolkit.id)}
        disabled={running}
      >
        {running ? "Running…" : `Run on top ${DEFAULT_SYMBOLS.length} stocks`}
      </Button>
    </div>
  );
}

// ── Main hub page ─────────────────────────────────────────────────────────────

export default function SentimentHubPage() {
  const router = useRouter();
  const [providers, setProviders] = useState<ProvidersStatusResponse | null>(null);
  const [toolkits, setToolkits] = useState<SentimentToolkit[]>([]);
  const [activeToolkit, setActiveToolkit] = useState<string | null>(null);
  const [results, setResults] = useState<SentimentAnalyzeResponse | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getProvidersStatus().then(setProviders).catch(() => {});
    getSentimentToolkits().then(setToolkits).catch(() => {});
  }, []);

  const handleRunToolkit = async (toolkitId: string) => {
    setRunningId(toolkitId);
    setActiveToolkit(toolkitId);
    setResults(null);
    try {
      const r = await runSentimentAnalyze(DEFAULT_SYMBOLS, toolkitId);
      setResults(r);
    } catch {
      setResults({ candidates: [], provider_status: {}, warnings: ["Failed to run analysis."] });
    } finally {
      setRunningId(null);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = searchQuery.trim().toUpperCase();
    if (sym) router.push(`/stocks/${sym}?tab=sentiment` as Route);
  };

  const activeToolkitName = toolkits.find((t) => t.id === activeToolkit)?.name;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-8 px-4 py-8 md:px-6 lg:px-8">

        {/* Header */}
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
            <Link href={"/" as Route} className="hover:text-foreground transition-colors">Home</Link>
            <span>/</span>
            <span className="text-foreground">News & Sentiment</span>
          </div>
          <h1 className="text-2xl font-bold font-heading">News & Sentiment</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Identify stocks with meaningful news catalysts and gauge community sentiment signals.
          </p>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={inputRef}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Enter ticker (e.g. AAPL)"
              className="w-full rounded-lg border border-border bg-white pl-9 pr-4 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <Button type="submit" size="sm" disabled={!searchQuery.trim()}>
            Analyze →
          </Button>
        </form>

        {/* Provider status */}
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Data Providers</div>
          {providers ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(providers).map(([name, status]) => (
                <ProviderStatusBadge key={name} name={name} status={status} />
              ))}
            </div>
          ) : (
            <div className="flex gap-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-7 w-32 rounded-full" />)}
            </div>
          )}
          {providers?.reddit === "not_configured" && (
            <p className="mt-2 text-xs text-muted-foreground">
              Reddit provider is not configured. Set <code className="font-mono bg-muted px-1 rounded">REDDIT_CLIENT_ID</code> and{" "}
              <code className="font-mono bg-muted px-1 rounded">REDDIT_CLIENT_SECRET</code> to enable community data.
            </p>
          )}
        </div>

        {/* Toolkit cards */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold">Pre-built Toolkits</h2>
              <p className="text-xs text-muted-foreground">Run any toolkit against the top {DEFAULT_SYMBOLS.length} US stocks</p>
            </div>
          </div>
          {toolkits.length === 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-36 rounded-xl" />)}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {toolkits.map((tk) => (
                <ToolkitCard
                  key={tk.id}
                  toolkit={tk}
                  onRun={handleRunToolkit}
                  running={runningId === tk.id}
                />
              ))}
            </div>
          )}
        </div>

        {/* Results */}
        {(results || runningId) && (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold">
                {activeToolkitName || "Results"}
                {results && (
                  <Badge variant="outline" className="ml-2 text-[10px] font-mono">{results.candidates.length} matches</Badge>
                )}
              </h2>
              {results && (
                <Button size="sm" variant="ghost" onClick={() => setResults(null)} className="text-xs text-muted-foreground">
                  Clear
                </Button>
              )}
            </div>

            {results?.warnings && results.warnings.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {results.warnings.map((w, i) => (
                  <div key={i} className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-700">
                    <AlertTriangle className="h-3 w-3" />{w}
                  </div>
                ))}
              </div>
            )}

            {runningId && !results && (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
              </div>
            )}

            {results && results.candidates.length === 0 && (
              <div className="rounded-xl border border-border bg-white p-8 text-center text-sm text-muted-foreground">
                No stocks matched the toolkit criteria in this run.
              </div>
            )}

            {results && results.candidates.length > 0 && (
              <div className="space-y-2">
                {results.candidates.map((c) => (
                  <CandidateRow
                    key={c.symbol}
                    c={c}
                    onNavigate={(sym) => router.push(`/stocks/${sym}?tab=sentiment` as Route)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Disclaimer */}
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/70" />
          This tool provides research candidates, not financial advice. News, social, and community sentiment data may be delayed, incomplete, biased, or noisy. Always verify important events with primary sources.
        </div>

      </div>
    </main>
  );
}
