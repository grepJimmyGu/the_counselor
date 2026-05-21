"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  AlertTriangle, ArrowRight, Bot, Loader2, Play,
  LineChart, Settings2,
} from "lucide-react";

import {
  anonymousBacktestRun,
  explainStrategy,
  getRobustnessJob,
  getSavedStrategy,
  runBacktest,
  runRobustness,
  reviewSandbox,
  saveStrategy,
} from "@/lib/api";
import {
  researchTemplates,
  type BacktestResult,
  type ResearchTemplate,
  type SavedStrategy,
  type ExplanationResponse,
  type RobustnessJobResponse,
  type SandboxReviewResponse,
  type StrategyJson,
} from "@/lib/contracts";
import { useLocale } from "@/lib/locale-context";
import { useEntitlements } from "@/lib/useEntitlements";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DrawdownChart, EquityCurveChart } from "@/components/workspace/charts";
import { MonthlyHeatmap } from "@/components/workspace/monthly-heatmap";
import { BacktestLoading } from "@/components/strategy-builder/backtest-loading";
import { StrategyBuilderModal } from "@/components/strategy-builder/strategy-builder-modal";
import { PublishModal } from "@/components/PublishModal";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatPercent(v: number) { return `${(v * 100).toFixed(2)}%`; }
function formatNumber(v: number)  { return v.toLocaleString(undefined, { maximumFractionDigits: 2 }); }

function VerdictBadge({ verdict }: { verdict: string }) {
  const color =
    verdict === "better" || verdict === "strong" || verdict === "robust" || verdict === "promising"
      ? "border-emerald-400 text-emerald-700 bg-emerald-50"
      : verdict === "worse" || verdict === "weak" || verdict === "breaks_down" || verdict === "untrusted"
      ? "border-rose-400 text-rose-700 bg-rose-50"
      : "border-border text-muted-foreground";
  return <Badge variant="outline" className={`capitalize text-xs font-medium ${color}`}>{verdict.replace(/_/g, " ")}</Badge>;
}

function RobustnessTable({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-background p-4">
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      <div className="overflow-x-auto"><Table>{children}</Table></div>
    </div>
  );
}

// ── Run history ───────────────────────────────────────────────────────────────

type RunHistoryEntry = {
  id: string; runAt: string; strategyName: string;
  universe: string[]; startDate: string; endDate: string;
  strategy: StrategyJson; result: BacktestResult;
  explanation: ExplanationResponse | null;
  sandboxReview: SandboxReviewResponse | null;
};

const RUN_HISTORY_KEY = "livermore_run_history";
const LIBRARY_KEY = "livermore_saved_strategies";

type LibraryEntry = { slug: string; name: string; savedAt: string };

// ── Component ─────────────────────────────────────────────────────────────────

export function ResearchWorkspace() {
  const { t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status: sessionStatus } = useSession();
  // Routing source-of-truth: NextAuth's resolved status, NOT the backend
  // token. Three states matter:
  //   - "loading"        → session cookie not yet decoded; defer routing.
  //   - "authenticated"  → real user; hit the authed endpoint.
  //   - "unauthenticated"→ no cookie; hit the anonymous endpoint.
  // We previously used `!backendToken` here, which misroutes
  // signed-in-but-stale-JWT users to /api/anonymous/* and triggers
  // "Sign up to build custom strategy" — the May 20 evening regression.
  const sessionUserId = session?.user?.id;
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;
  const isAnonymous = sessionStatus === "unauthenticated";
  // Loading state — NextAuth still resolving the cookie. The autorun=true
  // URL-param flow fires backtest 100ms after mount; without this guard a
  // signed-in user might race and get routed to anonymous.
  const isSessionLoading = sessionStatus === "loading";
  // Signed in but backendToken never got minted into the JWT cookie
  // (self-healing branch in auth.ts either failed silently or this is
  // an old JWT from before the fix). The user must sign out + back in
  // to get a fresh JWT with a populated backendToken.
  const needsSessionRefresh = sessionStatus === "authenticated" && !backendToken;

  // Stage 3: read the viewer's tier-aware caps so we can hide UI for locked
  // features (peer_ticker is Quant-only) and keep the experience consistent
  // with what the backend will allow.
  const { entitlements } = useEntitlements();
  const canUsePeerTicker = entitlements?.robustness_tests?.includes("peer_ticker") ?? false;

  const [strategy, setStrategy] = useState<StrategyJson | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [sandboxReview, setSandboxReview] = useState<SandboxReviewResponse | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("metrics");
  const [runHistory, setRunHistory] = useState<RunHistoryEntry[]>([]);
  const [savedLibrary, setSavedLibrary] = useState<LibraryEntry[]>([]);
  const [savedSlug, setSavedSlug] = useState<string | null>(null);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveIsPublic, setSaveIsPublic] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveStep, setSaveStep] = useState<"name" | "visibility">("name");
  const [peerTickers, setPeerTickers] = useState("");
  const [robustnessJob, setRobustnessJob] = useState<RobustnessJobResponse | null>(null);
  const [isRunningRobustness, setIsRunningRobustness] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [tradeLogExpanded, setTradeLogExpanded] = useState(false);

  const activeTemplate: ResearchTemplate | undefined = strategy
    ? researchTemplates.find(t => t.strategy.strategy_type === strategy.strategy_type && t.availability === "ready")
    : undefined;

  // ── Load from sessionStorage or URL params ────────────────────────────────
  useEffect(() => {
    try {
      const stored: LibraryEntry[] = JSON.parse(localStorage.getItem(LIBRARY_KEY) ?? "[]");
      setSavedLibrary(stored);
    } catch { /* ignore */ }
    try {
      const storedHistory: RunHistoryEntry[] = JSON.parse(localStorage.getItem(RUN_HISTORY_KEY) ?? "[]");
      setRunHistory(storedHistory);
    } catch { /* ignore */ }

    const fromBuilder = searchParams.get("fromBuilder");
    const autorun = searchParams.get("autorun") === "true";

    if (fromBuilder) {
      const pending = sessionStorage.getItem("pendingStrategy");
      if (pending) {
        try {
          const parsed: StrategyJson = JSON.parse(pending);
          sessionStorage.removeItem("pendingStrategy");
          setStrategy(parsed);
          router.replace("/workspace", { scroll: false });
          if (autorun) {
            setTimeout(() => void handleRunBacktestWith(parsed), 100);
          }
        } catch { /* ignore */ }
      }
      return;
    }

    // Legacy: template deep-link params
    const templateId = searchParams.get("templateId");
    const path = searchParams.get("path");
    const ticker = searchParams.get("ticker");
    const tickers = searchParams.get("tickers");
    const promptParam = searchParams.get("prompt");

    if (promptParam) {
      router.replace("/workspace", { scroll: false });
      return;
    }

    if (!templateId || !path) return;
    const template = researchTemplates.find(t => t.id === templateId);
    if (!template) return;

    const resolvedTickers = tickers
      ? tickers.split(",").map(t => t.trim().toUpperCase()).filter(Boolean)
      : ticker ? [ticker.toUpperCase()] : template.defaultTickers;

    const loaded = { ...template.strategy, universe: resolvedTickers };
    setStrategy(loaded);
    router.replace("/workspace", { scroll: false });
    if (autorun) {
      setTimeout(() => void handleRunBacktestWith(loaded), 100);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Backtest runner ───────────────────────────────────────────────────────
  async function handleRunBacktestWith(strat: StrategyJson) {
    if (isSessionLoading) {
      setErrorMessage("Account session still loading — please retry in a moment.");
      return;
    }
    if (needsSessionRefresh) {
      // The session banner below already explains this; surface the same
      // message inline so a click on Run gives immediate feedback.
      setErrorMessage(
        "Your account session needs to be refreshed. Click \"Refresh session\" below the header to sign out and back in, then retry."
      );
      return;
    }
    setIsRunning(true);
    setErrorMessage(null);
    setSavedSlug(null);
    setBacktestResult(null);
    setExplanation(null);
    setSandboxReview(null);
    try {
      const result = isAnonymous
        ? await anonymousBacktestRun({
            // Anonymous endpoint requires a non-empty template_id (Pydantic
            // min_length=1). Use the active template's id when known so
            // telemetry can attribute the run; otherwise mark it as a custom
            // build — as of 2026-05-22 anonymous viewers get ONE backtest
            // (template OR custom). After that, runs_exhausted fires.
            template_id: activeTemplate?.id ?? "custom",
            strategy_json: strat,
          })
        : await runBacktest(strat, {
            backendToken,
            // Pass templateId so require_entitlement (deps_entitlement.py:92)
            // skips the universe/history caps for template runs. Without this,
            // a Scout running the bundled 30-ticker momentum template would
            // 402 universe_too_large once gating is on — contradicting the
            // "templates always unlimited" copy.
            templateId: activeTemplate?.id,
          });
      setBacktestResult(result);
      const [explainerPayload, reviewerPayload] = await Promise.all([
        explainStrategy(strat, result, "en"),
        reviewSandbox(strat, result, [], "en", 1),
      ]);
      setExplanation(explainerPayload);
      setSandboxReview(reviewerPayload);
      const entry: RunHistoryEntry = {
        id: result.backtest_id, runAt: new Date().toISOString(),
        strategyName: strat.strategy_name, universe: strat.universe,
        startDate: strat.start_date, endDate: strat.end_date,
        strategy: strat, result, explanation: explainerPayload, sandboxReview: reviewerPayload,
      };
      setRunHistory(prev => {
        const updated = [entry, ...prev].slice(0, 20);
        localStorage.setItem(RUN_HISTORY_KEY, JSON.stringify(updated));
        return updated;
      });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : t.errorBacktest);
    } finally {
      setIsRunning(false);
    }
  }

  async function handleRunBacktest() {
    if (!strategy) return;
    await handleRunBacktestWith(strategy);
  }

  async function handleRunRobustness() {
    if (!strategy) return;
    setIsRunningRobustness(true);
    setRobustnessJob(null);
    // Defensive: only include peer_ticker if the viewer's tier actually
    // unlocks it. The input is already hidden for non-Quant, but a stale
    // peerTickers state from a tier downgrade shouldn't trigger a 402.
    const peers = canUsePeerTicker
      ? peerTickers.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
      : [];
    try {
      const job = await runRobustness(
        strategy,
        ["parameter_sensitivity", "subperiod", "transaction_cost", "benchmark_comparison", ...(peers.length ? ["peer_ticker"] : [])],
        peers,
        { backendToken },
      );
      setRobustnessJob(job);
      const poll = setInterval(async () => {
        try {
          const updated = await getRobustnessJob(job.run_id);
          setRobustnessJob(updated);
          if (updated.status === "completed" || updated.status === "failed") {
            clearInterval(poll);
            setIsRunningRobustness(false);
          }
        } catch { clearInterval(poll); setIsRunningRobustness(false); }
      }, 2000);
    } catch {
      setIsRunningRobustness(false);
    }
  }

  async function handleSaveStrategy() {
    if (!backtestResult || !saveName.trim()) return;
    // Match the backend's SaveStrategyRequest.title min_length=3 — kept in
    // sync so a Scout saving a 2-char title sees a friendly inline error
    // here instead of a 422 from the backend.
    if (saveName.trim().length < 3) {
      setSaveError("Name must be at least 3 characters.");
      return;
    }
    // Save now requires auth — surface a clear error rather than letting the
    // request 401. Anonymous users hit a different (publish modal) flow.
    if (!backendToken) {
      setSaveError("Please sign in to save strategies.");
      return;
    }
    setIsSaving(true); setSaveError(null);
    try {
      const { slug } = await saveStrategy(
        backendToken,
        backtestResult.backtest_id, saveName.trim(), saveIsPublic,
        backtestResult as unknown as object, strategy?.strategy_type ?? "unknown",
      );
      setSavedSlug(slug);
      setShowSaveDialog(false); setSaveStep("name"); setSaveError(null);
      const entry: LibraryEntry = { slug, name: saveName.trim(), savedAt: new Date().toISOString() };
      const updated = [entry, ...savedLibrary].slice(0, 20);
      setSavedLibrary(updated);
      localStorage.setItem(LIBRARY_KEY, JSON.stringify(updated));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.toLowerCase().includes("already saved")) {
        setShowSaveDialog(false); setSaveStep("name");
        const existing = savedLibrary.find(e => e.name === saveName.trim());
        if (existing) setSavedSlug(existing.slug);
      } else {
        setSaveError(msg || "Save failed — please try again.");
      }
    } finally { setIsSaving(false); }
  }

  function handleRestoreFromHistory(entry: RunHistoryEntry) {
    setStrategy(entry.strategy);
    setBacktestResult(entry.result);
    setExplanation(entry.explanation);
    setSandboxReview(entry.sandboxReview);
    setRobustnessJob(null);
    setSavedSlug(null);
    setShowSaveDialog(false);
    setActiveTab("metrics");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ── Derived ───────────────────────────────────────────────────────────────
  const explanationSections = explanation
    ? [
        { title: t.strengths, items: explanation.strengths },
        { title: t.weaknesses, items: explanation.weaknesses },
        { title: t.marketRegimeNotes, items: explanation.market_regime_notes },
        { title: t.suggestedIterations, items: explanation.suggested_iterations },
      ]
    : [];

  const sandboxConcernSections = sandboxReview
    ? [
        { title: t.reasonsToTrust, items: sandboxReview.main_reasons_to_trust },
        { title: t.reasonsToDistrust, items: sandboxReview.main_reasons_to_distrust },
        { title: t.benchmarkConcerns, items: sandboxReview.benchmark_concerns },
        { title: t.regimeDependence, items: sandboxReview.regime_dependence_concerns },
        { title: t.sensitivityConcerns, items: sandboxReview.parameter_sensitivity_concerns },
        { title: t.transactionCostConcerns, items: sandboxReview.transaction_cost_concerns },
        { title: t.sampleSizeConcerns, items: sandboxReview.sample_size_concerns },
        { title: t.dataQualityConcerns, items: sandboxReview.data_quality_concerns },
      ].filter(s => s.items?.length > 0)
    : [];

  const sandboxNextSteps = sandboxReview
    ? [
        { title: t.robustnessTests, items: sandboxReview.required_next_tests },
        { title: t.suggestedNextTests, items: sandboxReview.suggested_next_experiments },
      ].filter(s => s.items?.length > 0)
    : [];

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-background">
      <StrategyBuilderModal
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        initialTemplate={activeTemplate}
      />

      {strategy && backtestResult && (
        <PublishModal
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          strategy={strategy}
          result={backtestResult}
          backendToken={backendToken}
        />
      )}

      <div className="mx-auto max-w-[1400px] px-4 py-6 md:px-6 lg:px-8 space-y-6">

        {/* ── Header ──────────────────────────────────────────────────── */}
        <header className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            {strategy ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="font-heading text-xl font-bold tracking-tight truncate">
                    {strategy.strategy_name}
                  </h1>
                  <Badge variant="outline" className="shrink-0 text-xs font-mono capitalize">
                    {strategy.strategy_type.replace(/_/g, " ")}
                  </Badge>
                  {backtestResult && (
                    <span className="text-xs text-muted-foreground">
                      Run {new Date().toLocaleDateString()}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {strategy.universe.slice(0, 5).join(", ")}{strategy.universe.length > 5 ? ` +${strategy.universe.length - 5} more` : ""}{" "}
                  · {strategy.start_date} → {strategy.end_date}
                </p>
              </>
            ) : (
              <h1 className="font-heading text-xl font-bold tracking-tight">Workspace</h1>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setBuilderOpen(true)} className="gap-1.5">
              <Settings2 className="h-4 w-4" />
              {strategy ? "Modify Strategy" : "Build Strategy"}
            </Button>
            {strategy && (
              <Button onClick={handleRunBacktest} disabled={isRunning} size="sm" className="gap-1.5">
                {isRunning
                  ? <><Loader2 className="h-4 w-4 animate-spin" />Running…</>
                  : <><Play className="h-4 w-4" />Run Backtest</>
                }
              </Button>
            )}
          </div>
        </header>

        {/* ── Session-refresh banner ─────────────────────────────────────
            Fires when NextAuth reports the user is signed in but the JWT
            cookie predates the May 20 auth fix (no backendToken). One click
            signs them out so they can sign back in and get a fresh JWT.  */}
        {needsSessionRefresh && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>
                Your account session is out of date and we can&apos;t reach the backend with it.
                Sign out and back in to refresh — your saved work is unaffected.
              </span>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void signOut({ callbackUrl: "/login" })}
            >
              Refresh session
            </Button>
          </div>
        )}

        {/* ── Error ───────────────────────────────────────────────────── */}
        {errorMessage && (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* ── Empty state ──────────────────────────────────────────────── */}
        {!strategy && !isRunning && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-24 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Bot className="h-7 w-7 text-primary" />
            </div>
            <h2 className="mt-4 font-heading text-lg font-semibold">No strategy loaded</h2>
            <p className="mt-2 max-w-xs text-sm text-muted-foreground">
              Open the strategy builder to choose a template or describe your own idea.
            </p>
            <Button className="mt-6 gap-2" onClick={() => setBuilderOpen(true)}>
              Open Strategy Builder <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* ── Loading animation ────────────────────────────────────────── */}
        {isRunning && strategy && (
          <BacktestLoading strategy={strategy} isRunning={isRunning} />
        )}

        {/* ── Results — top section ────────────────────────────────────── */}
        {backtestResult && !isRunning && (
          <>
            {/* Metric cards — semantic left-border accent */}
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
              {[
                { label: "Total Return",  value: formatPercent(backtestResult.metrics.total_return),                   raw: backtestResult.metrics.total_return,                   type: "pnl"   as const },
                { label: "Ann. Return",   value: formatPercent(backtestResult.metrics.annualized_return),               raw: backtestResult.metrics.annualized_return,               type: "pnl"   as const },
                { label: "Sharpe",        value: backtestResult.metrics.sharpe_ratio.toFixed(2),                        raw: backtestResult.metrics.sharpe_ratio,                    type: "ratio" as const },
                { label: "Max Drawdown",  value: formatPercent(backtestResult.metrics.max_drawdown),                    raw: backtestResult.metrics.max_drawdown,                    type: "loss"  as const },
                { label: "Win Rate",      value: formatPercent(backtestResult.metrics.win_rate),                        raw: backtestResult.metrics.win_rate,                        type: "pct"   as const },
                { label: "vs Benchmark",  value: formatPercent(backtestResult.metrics.excess_return_vs_benchmark),      raw: backtestResult.metrics.excess_return_vs_benchmark,      type: "pnl"   as const },
              ].map(({ label, value, raw, type }) => {
                const isLoss = type === "loss";
                const isPos = raw > 0;
                const isNeg = raw < 0;
                const valueColor = isLoss
                  ? "text-[var(--loss)]"
                  : isPos ? "text-[var(--profit)]"
                  : isNeg ? "text-[var(--loss)]"
                  : "text-foreground";
                const accentBorder = isLoss
                  ? "border-l-rose-500/60"
                  : isPos ? "border-l-emerald-500/60"
                  : isNeg ? "border-l-rose-500/60"
                  : "border-l-border";
                return (
                  <div key={label} className={cn(
                    "rounded-xl border border-border bg-card px-4 py-3 border-l-4 transition-shadow duration-150 hover:shadow-sm",
                    accentBorder,
                  )}>
                    <div className="text-xs font-medium text-muted-foreground">{label}</div>
                    <div className={cn("mt-1.5 font-mono text-xl font-bold tracking-tight", valueColor)}>{value}</div>
                  </div>
                );
              })}
            </div>

            {/* Equity curve */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center gap-2">
                <LineChart className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold">{t.equityCurve}</h2>
              </div>
              <EquityCurveChart result={backtestResult} />
            </div>

            {/* Trade log */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold">{t.tradeLog}</h2>
                <div className="flex items-center gap-3">
                  {backtestResult.warnings.length > 0 && (
                    <Badge variant="outline">{backtestResult.warnings.length} warnings</Badge>
                  )}
                  <button
                    type="button"
                    onClick={() => setTradeLogExpanded(v => !v)}
                    className="cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {tradeLogExpanded ? "Show less" : `Show all ${backtestResult.trade_log.length}`}
                  </button>
                </div>
              </div>
              <ScrollArea className={tradeLogExpanded ? "h-[480px]" : "h-[240px]"}>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t.symbol}</TableHead>
                      <TableHead>{t.entry}</TableHead>
                      <TableHead>{t.exit}</TableHead>
                      <TableHead className="text-right">{t.return}</TableHead>
                      <TableHead className="text-right">{t.holdDays}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {backtestResult.trade_log.map((trade, idx) => (
                      <TableRow
                        key={`${trade.symbol}-${trade.entry_date}-${idx}`}
                        className="cursor-default transition-colors duration-100 hover:bg-muted/40"
                      >
                        <TableCell className="font-mono text-xs font-semibold">{trade.symbol}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{trade.entry_date}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{trade.exit_date}</TableCell>
                        <TableCell className={cn("text-right text-xs font-mono font-semibold", trade.return_pct >= 0 ? "text-[var(--profit)]" : "text-[var(--loss)]")}>
                          {formatPercent(trade.return_pct)}
                        </TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">{trade.holding_period_days}d</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </div>

            {/* Save row */}
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">{t.backtestDisclaimer}</p>
              <div className="flex shrink-0 items-center gap-2">
                {!savedSlug && (
                  <Button variant="outline" size="sm" onClick={() => { setSaveName(strategy?.strategy_name ?? ""); setSaveStep("name"); setSaveIsPublic(true); setSaveError(null); setShowSaveDialog(true); }}>
                    Save
                  </Button>
                )}
                {backendToken && backtestResult && strategy && (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => setPublishOpen(true)}
                  >
                    Publish to community
                  </Button>
                )}
                {savedSlug && (
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(`${window.location.origin}/strategies/${savedSlug}`)}
                    className="cursor-pointer text-xs text-primary hover:underline"
                  >
                    {t.savedCopyLink}
                  </button>
                )}
              </div>
            </div>

            {/* Save dialog */}
            {showSaveDialog && (
              <div className="rounded-xl border border-border bg-card p-5 space-y-3">
                {saveStep === "name" ? (
                  <div className="space-y-2">
                    <p className="text-sm font-semibold">Name this strategy</p>
                    <div className="flex gap-2">
                      <input
                        autoFocus type="text" value={saveName}
                        onChange={e => setSaveName(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter" && saveName.trim()) setSaveStep("visibility"); if (e.key === "Escape") setShowSaveDialog(false); }}
                        placeholder={t.saveNamePlaceholder} maxLength={80}
                        className="flex-1 rounded-md border border-border bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <Button size="sm" disabled={!saveName.trim()} onClick={() => setSaveStep("visibility")}>Next →</Button>
                      <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>{t.saveCancel}</Button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm font-semibold">Who can see &ldquo;{saveName}&rdquo;?</p>
                    <div className="grid grid-cols-2 gap-2">
                      {[{ pub: true, label: "Public", desc: "Visible in community." }, { pub: false, label: "Private", desc: "Only via direct link." }].map(({ pub, label, desc }) => (
                        <button key={label} type="button" onClick={() => setSaveIsPublic(pub)}
                          className={cn("rounded-lg border p-3 text-left transition-all cursor-pointer", saveIsPublic === pub ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border bg-white hover:border-primary/40")}>
                          <div className="text-sm font-semibold">{label}</div>
                          <div className="text-xs text-muted-foreground">{desc}</div>
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => { setSaveStep("name"); setSaveError(null); }}>← Back</Button>
                      <Button size="sm" disabled={isSaving} onClick={handleSaveStrategy}>
                        {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : `Save as ${saveIsPublic ? "Public" : "Private"}`}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => { setShowSaveDialog(false); setSaveError(null); }}>{t.saveCancel}</Button>
                    </div>
                    {saveError && <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{saveError}</p>}
                  </div>
                )}
              </div>
            )}

            {/* ── Bottom tabs ────────────────────────────────────────── */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="metrics">Detailed Metrics</TabsTrigger>
                <TabsTrigger value="review">Review</TabsTrigger>
                <TabsTrigger value="robustness">{t.tabRobustness}</TabsTrigger>
                <TabsTrigger value="history">
                  History{runHistory.length > 0 && <span className="ml-1.5 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-mono text-primary">{runHistory.length}</span>}
                </TabsTrigger>
              </TabsList>

              {/* Detailed Metrics */}
              <TabsContent value="metrics" className="mt-6 space-y-6">
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="rounded-xl border border-border bg-card p-5">
                    <h3 className="mb-4 text-sm font-semibold">{t.keyMetrics}</h3>
                    <div className="space-y-2.5">
                      {([
                        { label: t.annualizedReturn, key: "annualized_return", pct: true },
                        { label: t.sharpeRatioLabel, key: "sharpe_ratio",       pct: false },
                        { label: t.sortinoRatio,     key: "sortino_ratio",      pct: false },
                        { label: t.calmarRatio,      key: "calmar_ratio",       pct: false },
                        { label: t.winRateLabel,     key: "win_rate",           pct: true },
                        { label: t.avgTradeReturn,   key: "avg_trade_return",   pct: true },
                        { label: t.numOfTrades,      key: "number_of_trades",   pct: false },
                        { label: t.alphaVsBenchmark, key: "excess_return_vs_benchmark", pct: true },
                        { label: t.buyAndHoldReturn, key: "buy_and_hold_return",pct: true },
                        { label: "Turnover",         key: "turnover",           pct: false },
                      ] as { label: string; key: string; pct: boolean }[]).map(({ label, key, pct }) => {
                        const raw = (backtestResult.metrics as unknown as Record<string, number>)[key];
                        if (raw == null) return null;
                        const valueClass = raw > 0 ? "text-[var(--profit)] font-semibold" : raw < 0 ? "text-[var(--loss)] font-semibold" : "font-medium";
                        return (
                          <div key={key} className="flex items-center justify-between gap-4 border-b border-border/50 pb-2 last:border-0">
                            <span className="text-sm text-muted-foreground">{label}</span>
                            <span className={cn("font-mono text-sm", valueClass)}>{pct ? formatPercent(raw) : formatNumber(raw)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-card p-5">
                    <h3 className="mb-4 text-sm font-semibold">{t.annualReturns}</h3>
                    <Table>
                      <TableHeader><TableRow><TableHead>{t.year}</TableHead><TableHead className="text-right">{t.return}</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {backtestResult.annual_returns.map(item => (
                          <TableRow key={item.year}>
                            <TableCell>{item.year}</TableCell>
                            <TableCell className={cn("text-right font-mono", item.return_pct >= 0 ? "text-[var(--profit)]" : "text-[var(--loss)]")}>
                              {formatPercent(item.return_pct)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-card p-5">
                  <h3 className="mb-4 text-sm font-medium">{t.drawdownCurve}</h3>
                  <DrawdownChart result={backtestResult} />
                </div>
                <div className="rounded-xl border border-border bg-card p-5">
                  <h3 className="mb-4 text-sm font-medium">{t.monthlyHeatmap}</h3>
                  <MonthlyHeatmap result={backtestResult} />
                </div>
              </TabsContent>

              {/* Review */}
              <TabsContent value="review" className="mt-6">
                {!explanation && !sandboxReview ? (
                  <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">{t.reviewRunFirst}</div>
                ) : (
                  <div className="grid gap-4 lg:grid-cols-2">
                    <section className="rounded-xl border border-border bg-card shadow-sm">
                      <div className="border-b border-border px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 rounded-full bg-primary" />
                          <h3 className="font-heading text-sm font-semibold">{t.strategyExplanationTitle}</h3>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">{t.strategyExplanationDesc}</p>
                      </div>
                      <div className="space-y-4 p-5">
                        {explanation ? (
                          <>
                            <div>
                              <p className="text-sm font-semibold">{explanation.strategy_summary}</p>
                              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{explanation.performance_explanation}</p>
                            </div>
                            {explanationSections.map(({ title, items }) => (
                              <div key={title}>
                                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                <ul className="space-y-1.5">
                                  {(items as string[]).map(item => (
                                    <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
                                      {item}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                            {explanation.disclaimer && <p className="text-xs text-muted-foreground border-t border-border pt-3">{explanation.disclaimer}</p>}
                          </>
                        ) : <p className="text-sm text-muted-foreground">{t.explanationNotAvailable}</p>}
                      </div>
                    </section>

                    <section className="rounded-xl border border-border bg-card shadow-sm">
                      <div className="border-b border-border px-5 py-3.5">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span className="h-2 w-2 rounded-full bg-[var(--warning-amber)]" />
                            <h3 className="font-heading text-sm font-semibold">{t.aiReviewTitle}</h3>
                          </div>
                          {sandboxReview && (
                            <div className="flex items-center gap-2">
                              <Badge className={cn("capitalize text-xs font-semibold",
                                sandboxReview.review_verdict === "promising" ? "bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                                : sandboxReview.review_verdict === "untrusted" ? "bg-rose-50 text-rose-700 border-rose-300 hover:bg-rose-50"
                                : "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-50"
                              )}>{sandboxReview.review_verdict}</Badge>
                              <span className="text-xs font-mono text-muted-foreground">{sandboxReview.trust_score}/100</span>
                            </div>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">{t.aiReviewDesc}</p>
                      </div>
                      <div className="space-y-4 p-5">
                        {sandboxReview ? (
                          <>
                            <div className="flex flex-wrap gap-2">
                              <Badge variant={sandboxReview.overfitting_risk === "high" ? "destructive" : "outline"}
                                className={cn("text-xs", sandboxReview.overfitting_risk === "medium" ? "border-amber-300 text-amber-700 bg-amber-50" : sandboxReview.overfitting_risk === "low" ? "border-emerald-300 text-emerald-700 bg-emerald-50" : "")}>
                                {t.overfitRiskLabel} {sandboxReview.overfitting_risk}
                              </Badge>
                              <Badge variant="outline" className="text-xs capitalize">{t.confidenceLabel} {sandboxReview.confidence_level}</Badge>
                            </div>
                            <p className="text-sm leading-relaxed text-muted-foreground">{sandboxReview.overfitting_risk_explanation}</p>
                            {sandboxConcernSections.map(({ title, items }) => (
                              <div key={title}>
                                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                <ul className="space-y-1.5">
                                  {items.map(item => (
                                    <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--warning-amber)]" />
                                      {item}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                            {sandboxNextSteps.map(({ title, items }) => (
                              <div key={title}>
                                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                <ul className="space-y-1.5">
                                  {items.map(item => (
                                    <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" />
                                      {item}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                            {sandboxReview.final_warning && <p className="border-t border-border pt-3 text-xs text-[var(--loss)]">{sandboxReview.final_warning}</p>}
                          </>
                        ) : <p className="text-sm text-muted-foreground">{t.reviewNotAvailable}</p>}
                      </div>
                    </section>
                  </div>
                )}
              </TabsContent>

              {/* Robustness */}
              <TabsContent value="robustness" className="mt-6 space-y-4">
                <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-end">
                  {/* peer_ticker is a Quant-only robustness test. For lower
                      tiers, hide the input — the backend would otherwise 402
                      `robustness_test_locked` once gating is live. */}
                  {canUsePeerTicker ? (
                    <div className="flex-1 space-y-1">
                      <label className="text-xs text-muted-foreground">{t.peerTickersLabel}</label>
                      <input
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder={t.peerTickersPlaceholder}
                        value={peerTickers}
                        onChange={e => setPeerTickers(e.target.value)}
                        disabled={isRunningRobustness}
                      />
                    </div>
                  ) : (
                    <div className="flex-1 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                      Peer-ticker comparison is a Quant feature.{" "}
                      <a href="/pricing" className="underline hover:text-foreground">
                        Upgrade
                      </a>{" "}
                      to compare your strategy against custom benchmark tickers.
                    </div>
                  )}
                  <Button onClick={handleRunRobustness} disabled={!strategy || isRunningRobustness}>
                    {isRunningRobustness ? <><Loader2 className="h-4 w-4 animate-spin" />{t.runningRobustness}</> : t.runRobustness}
                  </Button>
                </div>
                {!robustnessJob && <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">{t.robustnessEmpty}</div>}
                {robustnessJob?.status === "failed" && <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{t.robustnessFailed} {robustnessJob.error}</div>}
                {robustnessJob && (robustnessJob.status === "pending" || robustnessJob.status === "running") && (
                  <div className="flex items-center gap-2 rounded-lg border border-border p-4 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />{t.runningRobustness}
                  </div>
                )}
                {robustnessJob?.status === "completed" && robustnessJob.results && (() => {
                  const r = robustnessJob.results;
                  return (
                    <div className="space-y-4">
                      {r.summary && <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm"><span className="font-medium">{t.robustnessSummary}: </span>{r.summary}</div>}
                      {r.parameter_sensitivity.length > 0 && (
                        <RobustnessTable title={t.paramSensitivityTitle}>
                          <TableHeader><TableRow><TableHead>{t.colParamSet}</TableHead><TableHead className="text-right">{t.colTotalReturn}</TableHead><TableHead className="text-right">{t.colSharpe}</TableHead><TableHead className="text-right">{t.colMaxDrawdown}</TableHead><TableHead>{t.colVerdict}</TableHead></TableRow></TableHeader>
                          <TableBody>{r.parameter_sensitivity.map((row, i) => (<TableRow key={i}><TableCell className="font-mono text-xs">{Object.entries(row.parameter_set).map(([k,v]) => `${k}=${v}`).join(", ")}</TableCell><TableCell className="text-right">{formatPercent(row.total_return)}</TableCell><TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell><TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell><TableCell><VerdictBadge verdict={row.verdict} /></TableCell></TableRow>))}</TableBody>
                        </RobustnessTable>
                      )}
                      {r.subperiod.length > 0 && (
                        <RobustnessTable title={t.subperiodTitle}>
                          <TableHeader><TableRow><TableHead>{t.colPeriod}</TableHead><TableHead>{t.colStart}</TableHead><TableHead>{t.colEnd}</TableHead><TableHead className="text-right">{t.colTotalReturn}</TableHead><TableHead className="text-right">{t.colSharpe}</TableHead><TableHead className="text-right">{t.colMaxDrawdown}</TableHead><TableHead>{t.colVerdict}</TableHead></TableRow></TableHeader>
                          <TableBody>{r.subperiod.map((row, i) => (<TableRow key={i}><TableCell className="font-medium">{row.period}</TableCell><TableCell className="text-xs text-muted-foreground">{row.start_date}</TableCell><TableCell className="text-xs text-muted-foreground">{row.end_date}</TableCell><TableCell className="text-right">{formatPercent(row.total_return)}</TableCell><TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell><TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell><TableCell><VerdictBadge verdict={row.verdict} /></TableCell></TableRow>))}</TableBody>
                        </RobustnessTable>
                      )}
                      {r.transaction_cost.length > 0 && (
                        <RobustnessTable title={t.txCostTitle}>
                          <TableHeader><TableRow><TableHead>{t.colCostBps}</TableHead><TableHead className="text-right">{t.colTotalReturn}</TableHead><TableHead className="text-right">{t.colSharpe}</TableHead><TableHead className="text-right">{t.colMaxDrawdown}</TableHead><TableHead>{t.colVerdict}</TableHead></TableRow></TableHeader>
                          <TableBody>{r.transaction_cost.map((row, i) => (<TableRow key={i}><TableCell>{row.cost_bps}</TableCell><TableCell className="text-right">{formatPercent(row.total_return)}</TableCell><TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell><TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell><TableCell><VerdictBadge verdict={row.verdict} /></TableCell></TableRow>))}</TableBody>
                        </RobustnessTable>
                      )}
                      {r.benchmark_comparison.length > 0 && (
                        <RobustnessTable title={t.benchmarkCompTitle}>
                          <TableHeader><TableRow><TableHead>{t.colName}</TableHead><TableHead className="text-right">{t.colTotalReturn}</TableHead><TableHead className="text-right">{t.colSharpe}</TableHead><TableHead className="text-right">{t.colMaxDrawdown}</TableHead><TableHead className="text-right">{t.colExcess}</TableHead></TableRow></TableHeader>
                          <TableBody>{r.benchmark_comparison.map((row, i) => (<TableRow key={i}><TableCell className="font-medium">{row.name} <span className="text-xs text-muted-foreground">({row.symbol})</span></TableCell><TableCell className="text-right">{formatPercent(row.total_return)}</TableCell><TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell><TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell><TableCell className="text-right">{formatPercent(row.excess_return_vs_strategy)}</TableCell></TableRow>))}</TableBody>
                        </RobustnessTable>
                      )}
                    </div>
                  );
                })()}
              </TabsContent>

              {/* History */}
              <TabsContent value="history" className="mt-6 space-y-3">
                {runHistory.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">{t.historyEmpty}</div>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground">{t.historyCount(runHistory.length)}</p>
                      <button type="button" onClick={() => { setRunHistory([]); localStorage.removeItem(RUN_HISTORY_KEY); }}
                        className="cursor-pointer text-xs text-muted-foreground hover:text-destructive transition-colors">
                        {t.clearHistory}
                      </button>
                    </div>
                    <div className="space-y-2">
                      {runHistory.map((entry, idx) => {
                        const ret = entry.result.metrics.total_return;
                        const sharpe = entry.result.metrics.sharpe_ratio;
                        const dd = entry.result.metrics.max_drawdown;
                        const isActive = backtestResult?.backtest_id === entry.id;
                        return (
                          <div key={entry.id} className={cn("rounded-xl border p-4 transition-colors", isActive ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:border-primary/20")}>
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  {isActive && <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" />}
                                  <span className="font-heading text-sm font-semibold truncate">{entry.strategyName}</span>
                                  {idx === 0 && !isActive && <Badge variant="outline" className="text-[10px] shrink-0">{t.historyLatest}</Badge>}
                                </div>
                                <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                                  <span className="font-mono">{entry.universe.slice(0,3).join(", ")}{entry.universe.length > 3 ? `+${entry.universe.length-3}` : ""}</span>
                                  <span>{entry.startDate} → {entry.endDate}</span>
                                </div>
                                {!isActive && (
                                  <button type="button" onClick={() => handleRestoreFromHistory(entry)}
                                    className="mt-2 cursor-pointer rounded-md border border-primary/30 bg-primary/5 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/10">
                                    {t.historyRestore}
                                  </button>
                                )}
                              </div>
                              <div className="flex shrink-0 gap-4 text-right text-xs">
                                <div><div className="text-[10px] text-muted-foreground">Return</div><div className={cn("font-mono font-semibold", ret >= 0 ? "text-[var(--profit)]" : "text-[var(--loss)]")}>{formatPercent(ret)}</div></div>
                                <div><div className="text-[10px] text-muted-foreground">Sharpe</div><div className={cn("font-mono font-semibold", sharpe >= 1 ? "text-[var(--profit)]" : sharpe < 0 ? "text-[var(--loss)]" : "text-foreground")}>{sharpe.toFixed(2)}</div></div>
                                <div><div className="text-[10px] text-muted-foreground">Max DD</div><div className="font-mono font-semibold text-[var(--loss)]">{formatPercent(dd)}</div></div>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </main>
  );
}
