"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CircleAlert,
  FileText,
  FlaskConical,
  HelpCircle,
  LineChart,
  Loader2,
  Play,
  Upload,
  WandSparkles,
} from "lucide-react";

import {
  explainStrategy,
  getDataQuality,
  getRobustnessJob,
  getSavedStrategy,
  parseStrategy,
  parseStrategyMarkdown,
  reviewSandbox,
  runBacktest,
  runRobustness,
  saveStrategy,
} from "@/lib/api";
import {
  commodityDemoStrategies,
  demoMarkdownStrategy,
  demoStrategies,
  researchTemplates,
  type BacktestResult,
  type ResearchTemplate,
  type SavedStrategy,
  type DataQualityReport,
  type ExplanationResponse,
  type RobustnessJobResponse,
  type SandboxReviewResponse,
  type StrategyMarkdownParseResponse,
  type StrategyJson,
} from "@/lib/contracts";
import { useLocale } from "@/lib/locale-context";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DrawdownChart, EquityCurveChart } from "@/components/workspace/charts";
import { DataStatusBadge } from "@/components/workspace/data-status-badge";
import { MonthlyHeatmap } from "@/components/workspace/monthly-heatmap";
import { TickerSearch } from "@/components/workspace/ticker-search";
import { CapabilityGlossary } from "@/components/home/capability-glossary";

type ChatMessage = {
  role: "user" | "assistant" | "clarification";
  content: string;
};

type ComparisonRow = {
  label: string;
  current: number;
  previous: number;
};

type LibraryEntry = {
  slug: string;
  name: string;
  savedAt: string;
};

type RunHistoryEntry = {
  id: string;
  runAt: string;
  strategyName: string;
  universe: string[];
  startDate: string;
  endDate: string;
  strategy: StrategyJson;
  chat: ChatMessage[];
  result: BacktestResult;
  explanation: ExplanationResponse | null;
  sandboxReview: SandboxReviewResponse | null;
};

const LIBRARY_KEY = "livermore_saved_strategies";
const RUN_HISTORY_KEY = "livermore_run_history";

function RobustnessTable({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-background p-4">
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      <div className="overflow-x-auto">
        <Table>{children}</Table>
      </div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const color =
    verdict === "better" || verdict === "strong" || verdict === "robust" || verdict === "promising"
      ? "border-emerald-400 text-emerald-700 bg-emerald-50"
      : verdict === "worse" || verdict === "weak" || verdict === "breaks_down" || verdict === "untrusted"
      ? "border-rose-400 text-rose-700 bg-rose-50"
      : "border-border text-muted-foreground";
  return <Badge variant="outline" className={`capitalize text-xs font-medium ${color}`}>{verdict.replace(/_/g, " ")}</Badge>;
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function buildComparison(
  current: BacktestResult | null,
  previous: BacktestResult | null,
  labels: { totalReturn: string; sharpe: string; maxDrawdown: string; trades: string; winRate: string; turnover: string },
): ComparisonRow[] {
  if (!current || !previous) return [];
  return [
    { label: labels.totalReturn, current: current.metrics.total_return, previous: previous.metrics.total_return },
    { label: labels.sharpe, current: current.metrics.sharpe_ratio, previous: previous.metrics.sharpe_ratio },
    { label: labels.maxDrawdown, current: current.metrics.max_drawdown, previous: previous.metrics.max_drawdown },
    { label: labels.winRate, current: current.metrics.win_rate, previous: previous.metrics.win_rate },
    { label: labels.turnover, current: current.metrics.turnover, previous: previous.metrics.turnover },
  ];
}

function buildSavedComparison(
  current: BacktestResult | null,
  saved: SavedStrategy | null,
  labels: { totalReturn: string; sharpe: string; maxDrawdown: string; winRate: string; turnover: string },
): ComparisonRow[] {
  if (!current || !saved) return [];
  const m = saved.metrics as unknown as Record<string, number>;
  return [
    { label: labels.totalReturn, current: current.metrics.total_return, previous: m.total_return ?? 0 },
    { label: labels.sharpe, current: current.metrics.sharpe_ratio, previous: m.sharpe_ratio ?? 0 },
    { label: labels.maxDrawdown, current: current.metrics.max_drawdown, previous: m.max_drawdown ?? 0 },
    { label: labels.winRate, current: current.metrics.win_rate, previous: m.win_rate ?? 0 },
    { label: labels.turnover, current: current.metrics.turnover, previous: m.turnover ?? 0 },
  ];
}

function getQuickReplies(questions: string[]): string[] {
  const text = questions.join(" ").toLowerCase();
  if (/period|timeframe|lookback|how long|days|week|month|duration/.test(text))
    return ["Past 1 week", "Past 1 month", "Past 3 months", "Past 6 months", "Past 1 year"];
  if (/threshold|how much|percent|%|up by|down by|magnitude|amount/.test(text))
    return ["Any positive move", "More than 2%", "More than 5%", "More than 10%"];
  if (/exit|sell|close|when to|stop loss|take profit/.test(text))
    return ["When signal reverses", "After 1 month", "5% stop loss", "10% stop loss", "No explicit exit"];
  if (/universe|ticker|symbol|stock|asset|which/.test(text))
    return [];
  if (/top|how many|n assets|positions/.test(text))
    return ["Top 1 asset", "Top 2 assets", "Top 3 assets"];
  if (/rebalance|frequency|how often/.test(text))
    return ["Daily", "Weekly", "Monthly", "Quarterly"];
  return ["Use sensible defaults", "1 month lookback", "Exit on signal reversal", "Keep it simple"];
}

export function ResearchWorkspace() {
  const { locale, t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const strategyPreviewRef = useRef<HTMLElement>(null);

  const [prompt, setPrompt] = useState<string>(t.demoPrompts[0]);
  const [strategyDoc, setStrategyDoc] = useState(demoMarkdownStrategy);
  const [strategyDocName, setStrategyDocName] = useState("research-memo.md");
  const [chat, setChat] = useState<ChatMessage[]>([
    { role: "assistant", content: t.chatWelcome },
  ]);
  const [strategy, setStrategy] = useState<StrategyJson | null>(null);
  const [previousResult, setPreviousResult] = useState<BacktestResult | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [sandboxReview, setSandboxReview] = useState<SandboxReviewResponse | null>(null);
  const [markdownParseResult, setMarkdownParseResult] = useState<StrategyMarkdownParseResponse | null>(null);
  const [validationIssues, setValidationIssues] = useState<string[]>([]);
  const [clarifications, setClarifications] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [isParsingMarkdown, setIsParsingMarkdown] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [iterationCount, setIterationCount] = useState(0);
  const [qualityReports, setQualityReports] = useState<Record<string, DataQualityReport>>({});
  const [robustnessJob, setRobustnessJob] = useState<RobustnessJobResponse | null>(null);
  const [isRunningRobustness, setIsRunningRobustness] = useState(false);
  const [peerTickers, setPeerTickers] = useState("");
  const [activeTemplate, setActiveTemplate] = useState<ResearchTemplate | null>(null);
  const [templateReviewCallout, setTemplateReviewCallout] = useState(false);
  const [showEtfProxyCaveat, setShowEtfProxyCaveat] = useState(false);
  const [savedSlug, setSavedSlug] = useState<string | null>(null);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [savedLibrary, setSavedLibrary] = useState<LibraryEntry[]>([]);
  const [compareMode, setCompareMode] = useState<"previous" | string>("previous");
  const [savedCompareResult, setSavedCompareResult] = useState<SavedStrategy | null>(null);
  const [isLoadingCompare, setIsLoadingCompare] = useState(false);
  const [runHistory, setRunHistory] = useState<RunHistoryEntry[]>([]);
  const [showJsonPreview, setShowJsonPreview] = useState(false);
  const [activeTab, setActiveTab] = useState("results");
  const [autoRunPending, setAutoRunPending] = useState(false);
  // Interactive clarification
  const [pendingContext, setPendingContext] = useState<string | null>(null);
  const [clarificationTurnCount, setClarificationTurnCount] = useState(0);

  const comparisonRows = useMemo(
    () => buildComparison(backtestResult, previousResult, { totalReturn: t.totalReturn, sharpe: t.sharpe, maxDrawdown: t.maxDrawdown, trades: t.trades, winRate: t.winRate, turnover: t.turnover }),
    [backtestResult, previousResult, t],
  );

  const explanationSections: { title: string; items: string[] }[] = explanation
    ? [
        { title: t.strengths, items: explanation.strengths },
        { title: t.weaknesses, items: explanation.weaknesses },
        { title: t.marketRegimeNotes, items: explanation.market_regime_notes },
        { title: t.suggestedIterations, items: explanation.suggested_iterations },
      ]
    : [];

  const sandboxConcernSections: { title: string; items: string[] }[] = sandboxReview
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

  const sandboxNextSteps: { title: string; items: string[] }[] = sandboxReview
    ? [
        { title: t.robustnessTests, items: sandboxReview.required_next_tests },
        { title: t.suggestedNextTests, items: sandboxReview.suggested_next_experiments },
      ].filter(s => s.items?.length > 0)
    : [];

  function fetchQualityForSymbols(symbols: string[]) {
    symbols.forEach((sym) => {
      if (!qualityReports[sym]) {
        getDataQuality(sym)
          .then((r) => setQualityReports((prev) => ({ ...prev, [sym]: r })))
          .catch(() => {});
      }
    });
  }

  async function handleInterpretStrategy(nextPrompt?: string, { autoRun = false } = {}) {
    const activePrompt = nextPrompt ?? prompt;

    // Build contextual prompt: embed original intent when clarifications are pending
    const contextualPrompt = pendingContext
      ? `Original strategy request: ${pendingContext}\n\nFollow-up answer: ${activePrompt}`
      : activePrompt;

    setIsParsing(true);
    setErrorMessage(null);
    // Show the user's raw answer in chat (not the full context string)
    setChat((current) => [...current, { role: "user", content: activePrompt }]);

    try {
      const parsed = await parseStrategy(contextualPrompt, strategy, backtestResult?.backtest_id ?? null, locale);
      const state = parsed.clarification_state ?? "ready";

      if (state === "needs_parameters") {
        // Store original intent on first clarification turn
        if (!pendingContext) setPendingContext(activePrompt);
        const nextCount = clarificationTurnCount + 1;
        setClarificationTurnCount(nextCount);

        // Show assistant message
        setChat((current) => [...current, { role: "assistant", content: parsed.assistant_message }]);

        // Show approximation note if provided
        if (parsed.approximation_note) {
          setChat((current) => [...current, {
            role: "assistant",
            content: `ℹ️ ${parsed.approximation_note}`,
          }]);
        }

        // Inject each clarification question as its own amber chat bubble
        parsed.clarification_questions.forEach((q) => {
          setChat((current) => [...current, { role: "clarification", content: q }]);
        });

        setClarifications(parsed.clarification_questions);
        setValidationIssues(parsed.missing_fields);

        // Safety cap: after 3 turns show give-up message and reset
        if (nextCount >= 3) {
          setChat((current) => [...current, {
            role: "assistant",
            content: t.clarificationGiveUp,
          }]);
          setPendingContext(null);
          setClarificationTurnCount(0);
          setClarifications([]);
        }

      } else {
        // Ready or not_supported — clear clarification state
        setPendingContext(null);
        setClarificationTurnCount(0);
        setClarifications([]);

        setChat((current) => [...current, { role: "assistant", content: parsed.assistant_message }]);

        // Show approximation note if the strategy was proxied
        if (parsed.approximation_note) {
          setChat((current) => [...current, {
            role: "assistant",
            content: `ℹ️ ${parsed.approximation_note}`,
          }]);
        }

        setStrategy(parsed.strategy_json);
        if (parsed.strategy_json) fetchQualityForSymbols(parsed.strategy_json.universe);
        setMarkdownParseResult(null);
        setValidationIssues(parsed.missing_fields);

        if (autoRun && parsed.strategy_json && !parsed.missing_fields.length) {
          setAutoRunPending(true);
        }
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t.errorInterpret);
    } finally {
      setIsParsing(false);
    }
  }

  async function handleParseMarkdownStrategy() {
    setIsParsingMarkdown(true);
    setErrorMessage(null);

    try {
      const parsed = await parseStrategyMarkdown(strategyDoc, strategyDocName, locale);
      setMarkdownParseResult(parsed);
      setStrategy(parsed.strategy_json);
      if (parsed.strategy_json) fetchQualityForSymbols(parsed.strategy_json.universe);
      setValidationIssues(parsed.missing_fields);
      setClarifications(parsed.clarification_questions);
      setChat((current) => [
        ...current,
        { role: "assistant", content: `[${strategyDocName}] ${parsed.assistant_message}` },
      ]);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t.errorParseMemo);
    } finally {
      setIsParsingMarkdown(false);
    }
  }

  async function handleMarkdownFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setStrategyDocName(file.name);
    setStrategyDoc(await file.text());
    event.target.value = "";
  }

  async function handleRunBacktest() {
    if (!strategy) return;
    setIsRunning(true);
    setErrorMessage(null);
    setSavedSlug(null);
    setShowSaveDialog(false);
    setSaveName("");
    try {
      setPreviousResult(backtestResult);
      const nextIteration = iterationCount + 1;
      setIterationCount(nextIteration);
      const result = await runBacktest(strategy);
      setBacktestResult(result);
      const [explainerPayload, reviewerPayload] = await Promise.all([
        explainStrategy(strategy, result, locale),
        reviewSandbox(strategy, result, previousResult ? [previousResult.backtest_id] : [], locale, nextIteration),
      ]);
      setExplanation(explainerPayload);
      setSandboxReview(reviewerPayload);
      // Save to run history
      const historyEntry: RunHistoryEntry = {
        id: result.backtest_id,
        runAt: new Date().toISOString(),
        strategyName: strategy.strategy_name,
        universe: strategy.universe,
        startDate: strategy.start_date,
        endDate: strategy.end_date,
        strategy,
        chat,
        result,
        explanation: explainerPayload,
        sandboxReview: reviewerPayload,
      };
      setRunHistory((prev) => {
        const updated = [historyEntry, ...prev].slice(0, 20);
        localStorage.setItem(RUN_HISTORY_KEY, JSON.stringify(updated));
        return updated;
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : t.errorBacktest);
    } finally {
      setIsRunning(false);
    }
  }

  function updateStrategyField<K extends keyof StrategyJson>(key: K, value: StrategyJson[K]) {
    setStrategy((current) => (current ? { ...current, [key]: value } : current));
    if (key === "universe") fetchQualityForSymbols(value as string[]);
  }

  function handleLoadDemo(demo: typeof demoStrategies[number]) {
    const displayPrompt = locale === "zh" ? demo.labelZh : demo.label;
    setStrategy(demo.strategy);
    setPrompt(demo.prompt);
    setRobustnessJob(null);
    setBacktestResult(null);
    setExplanation(null);
    setSandboxReview(null);
    setMarkdownParseResult(null);
    setValidationIssues([]);
    setClarifications([]);
    setChat([
      { role: "assistant", content: t.chatWelcome },
      { role: "user", content: demo.prompt },
      { role: "assistant", content: t.loadedDemo(displayPrompt) },
    ]);
    fetchQualityForSymbols(demo.strategy.universe);
  }

  function handleLoadTemplate(template: ResearchTemplate, tickers: string[]) {
    const modified = { ...template.strategy, universe: tickers };
    setStrategy(modified);
    setPrompt("");
    setRobustnessJob(null);
    setBacktestResult(null);
    setExplanation(null);
    setSandboxReview(null);
    setMarkdownParseResult(null);
    setValidationIssues([]);
    setClarifications([]);
    setChat([
      { role: "assistant", content: t.chatWelcome },
      { role: "assistant", content: t.templateLoaded(template.name) },
    ]);
    setActiveTemplate(template);
    setTemplateReviewCallout(true);
    setShowEtfProxyCaveat(template.availability === "proxy");
    fetchQualityForSymbols(tickers);
    setTimeout(() => strategyPreviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  }

  function handleBuildFromTemplate(template: ResearchTemplate, tickers: string[]) {
    const tickerStr = tickers.join(", ");
    const seed = template.chatSeed
      .replace("{tickers}", tickerStr)
      .replace("{ticker}", tickerStr);
    setPrompt(seed);
    setActiveTemplate(template);
    setTemplateReviewCallout(false);
    setShowEtfProxyCaveat(false);
    setChat([
      { role: "assistant", content: t.chatWelcome },
      { role: "assistant", content: t.templateBuild(template.name) },
    ]);
  }

  async function handleSelectCompare(mode: string) {
    setCompareMode(mode);
    if (mode === "previous") { setSavedCompareResult(null); return; }
    setIsLoadingCompare(true);
    try {
      const result = await getSavedStrategy(mode);
      setSavedCompareResult(result);
    } catch {
      setSavedCompareResult(null);
      // stale slug — silently remove from library
      const cleaned = savedLibrary.filter((e) => e.slug !== mode);
      setSavedLibrary(cleaned);
      localStorage.setItem(LIBRARY_KEY, JSON.stringify(cleaned));
    } finally {
      setIsLoadingCompare(false);
    }
  }

  async function handleSaveStrategy() {
    if (!backtestResult || !saveName.trim()) return;
    setIsSaving(true);
    try {
      const { slug } = await saveStrategy(backtestResult.backtest_id, saveName.trim());
      setSavedSlug(slug);
      setShowSaveDialog(false);
      const entry: LibraryEntry = { slug, name: saveName.trim(), savedAt: new Date().toISOString() };
      const updated = [entry, ...savedLibrary].slice(0, 20);
      setSavedLibrary(updated);
      localStorage.setItem(LIBRARY_KEY, JSON.stringify(updated));
    } catch {
      // leave dialog open so user can retry
    } finally {
      setIsSaving(false);
    }
  }

  useEffect(() => {
    try {
      const stored: LibraryEntry[] = JSON.parse(localStorage.getItem(LIBRARY_KEY) ?? "[]");
      setSavedLibrary(stored);
    } catch {
      // ignore corrupt localStorage
    }
    try {
      const storedHistory: RunHistoryEntry[] = JSON.parse(localStorage.getItem(RUN_HISTORY_KEY) ?? "[]");
      setRunHistory(storedHistory);
    } catch {
      // ignore corrupt localStorage
    }
  }, []);

  useEffect(() => {
    // Handle ?prompt= from homepage strategy teaser
    const promptParam = searchParams.get("prompt");
    const autorun = searchParams.get("autorun") === "true";
    if (promptParam) {
      const decoded = decodeURIComponent(promptParam);
      setPrompt(decoded);
      router.replace("/workspace", { scroll: false });
      if (autorun) {
        void handleInterpretStrategy(decoded, { autoRun: true });
      }
      return;
    }

    const templateId = searchParams.get("templateId");
    const path = searchParams.get("path");
    const ticker = searchParams.get("ticker");
    const tickers = searchParams.get("tickers");
    if (!templateId || !path) return;

    const template = researchTemplates.find((t) => t.id === templateId);
    if (!template) return;

    const resolvedTickers = tickers
      ? tickers.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean)
      : ticker
      ? [ticker.toUpperCase()]
      : template.defaultTickers;

    if (path === "load") {
      handleLoadTemplate(template, resolvedTickers);
      if (autorun) setAutoRunPending(true);
    }
    if (path === "build") handleBuildFromTemplate(template, resolvedTickers);

    // Clear params from URL so a refresh doesn't re-trigger
    router.replace("/workspace", { scroll: false });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fire backtest once strategy is ready after an auto-run trigger
  useEffect(() => {
    if (!autoRunPending || !strategy || isRunning || isParsing) return;
    const timer = setTimeout(() => {
      setAutoRunPending(false);
      setActiveTab("results");
      void handleRunBacktest();
    }, 300);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunPending, strategy, isRunning, isParsing]);

  function handleRestoreFromHistory(entry: RunHistoryEntry) {
    setStrategy(entry.strategy);
    setChat(entry.chat);
    setBacktestResult(entry.result);
    setExplanation(entry.explanation);
    setSandboxReview(entry.sandboxReview);
    setPreviousResult(null);
    setRobustnessJob(null);
    setSavedSlug(null);
    setShowSaveDialog(false);
    setActiveTab("results");
    setTimeout(() => strategyPreviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  }

  async function handleRunRobustness() {
    if (!strategy) return;
    setIsRunningRobustness(true);
    setRobustnessJob(null);
    const peers = peerTickers.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
    try {
      const job = await runRobustness(
        strategy,
        ["parameter_sensitivity", "subperiod", "transaction_cost", "benchmark_comparison", ...(peers.length ? ["peer_ticker"] : [])],
        peers,
      );
      setRobustnessJob(job);
      // Poll until done
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

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6 px-4 py-4 md:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="mt-1 h-10 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Badge className="bg-primary/15 font-mono text-primary hover:bg-primary/15">{t.appName}</Badge>
              </div>
              <h1 className="font-heading text-3xl font-semibold tracking-tight">{t.workspaceTitle}</h1>
              <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{t.workspaceDesc}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {[t.noLiveTrading, t.priceBasedOnly, t.deterministicEngine].map((label) => (
              <div key={label} className="rounded-full border border-border/60 bg-muted/40 px-3 py-1 text-[11px] font-medium tracking-wide text-muted-foreground">
                {label}
              </div>
            ))}
          </div>
        </header>

        {errorMessage ? (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <CircleAlert className="mt-0.5 h-4 w-4" />
            <span>{errorMessage}</span>
          </div>
        ) : null}

        {/* Demo picker */}
        <section className="rounded-lg border border-border bg-card/50">
          <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
            <div>
              <span className="text-sm font-medium">{t.demosTitle}</span>
              <span className="ml-2 text-xs text-muted-foreground">{t.demosSubtitle}</span>
            </div>
          </div>
          <div className="flex flex-wrap divide-y divide-border/40 sm:divide-x sm:divide-y-0">
            {[
              { label: t.equitiesLabel, demos: demoStrategies, accent: "text-[var(--profit)]", dot: "bg-[var(--profit)]" },
              { label: t.commoditiesLabel, demos: commodityDemoStrategies, accent: "text-[var(--warning-amber)]", dot: "bg-[var(--warning-amber)]" },
            ].map(({ label, demos, accent, dot }) => (
              <div key={label} className="flex-1 p-3">
                <div className="mb-2 flex items-center gap-1.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
                  <span className={`text-[11px] font-semibold uppercase tracking-widest ${accent}`}>{label}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {demos.map((demo) => (
                    <button
                      key={demo.label}
                      type="button"
                      onClick={() => handleLoadDemo(demo)}
                      className="cursor-pointer rounded-md border border-border/60 bg-background/60 px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors duration-200 hover:border-primary/50 hover:bg-primary/5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {locale === "zh" ? demo.labelZh : demo.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="grid gap-6">
            {/* Chat Builder */}
            <section className="overflow-hidden rounded-lg border border-border bg-card/70">
              <div className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-3">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-primary" />
                  <h2 className="font-heading text-base font-semibold">{t.chatBuilderTitle}</h2>
                </div>
                <Badge variant="outline" className="font-mono text-xs">{t.strategyParser}</Badge>
              </div>
              <div className="space-y-4 p-4">
                <div className="flex flex-wrap gap-2">
                  {t.demoPrompts.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setPrompt(item)}
                      className="cursor-pointer rounded-md border border-border bg-background px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors duration-200 hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {item}
                    </button>
                  ))}
                </div>
                <Textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  className="min-h-36 resize-none"
                  placeholder={pendingContext ? t.clarificationAnswerPlaceholder : t.chatPlaceholder}
                />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs text-muted-foreground">{t.chatSupported}</span>
                  <Button onClick={() => handleInterpretStrategy()} disabled={isParsing}>
                    {isParsing ? (
                      <><Loader2 className="h-4 w-4 animate-spin" />{t.interpreting}</>
                    ) : (
                      <><WandSparkles className="h-4 w-4" />{t.interpret}</>
                    )}
                  </Button>
                </div>
              </div>
              <Separator />
              <ScrollArea className="h-[320px] px-4 py-4">
                <div className="space-y-3">
                  {chat.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={cn(
                        "rounded-lg border px-3 py-2.5 text-sm",
                        message.role === "assistant"
                          ? "border-border/60 bg-background"
                          : message.role === "clarification"
                          ? "border-amber-300 bg-amber-50/70 ml-2"
                          : "border-primary/30 bg-primary/8 ml-4",
                      )}
                    >
                      <div className={cn(
                        "mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest",
                        message.role === "assistant" ? "text-primary/70"
                        : message.role === "clarification" ? "text-amber-600"
                        : "text-muted-foreground"
                      )}>
                        {message.role === "assistant"
                          ? <><Bot className="h-3 w-3" />{t.aiLabel}</>
                          : message.role === "clarification"
                          ? <><HelpCircle className="h-3 w-3" />{t.clarificationLabel}</>
                          : <><ArrowRight className="h-3 w-3" />{t.youLabel}</>
                        }
                      </div>
                      <p className="whitespace-pre-wrap leading-6 text-foreground/90">{message.content}</p>
                    </div>
                  ))}
                </div>
              </ScrollArea>

              {/* Quick-reply chips — shown when clarification questions are pending */}
              {clarifications.length > 0 && (() => {
                const chips = getQuickReplies(clarifications);
                if (!chips.length) return null;
                return (
                  <div className="border-t border-amber-200 bg-amber-50/60 px-4 py-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-amber-600">
                      {t.quickRepliesLabel}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {chips.map((chip) => (
                        <button
                          key={chip}
                          type="button"
                          disabled={isParsing}
                          onClick={() => { setPrompt(chip); void handleInterpretStrategy(chip); }}
                          className="cursor-pointer rounded-full border border-amber-300 bg-white px-3 py-1 text-xs font-medium text-amber-700 transition-colors duration-150 hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                        >
                          {chip}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </section>

            {/* Strategy Doc */}
            <section className="overflow-hidden rounded-lg border border-border bg-card/70">
              <div className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-3">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  <h2 className="font-heading text-base font-semibold">{t.strategyDocTitle}</h2>
                </div>
                <Badge variant="outline" className="font-mono text-[10px]">{t.markdownIntake}</Badge>
              </div>
              <div className="space-y-4 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-sm font-medium">{strategyDocName}</div>
                    <p className="text-xs text-muted-foreground">{t.strategyDocDesc}</p>
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
                    <Upload className="h-3.5 w-3.5" />
                    {t.uploadMd}
                    <input
                      type="file"
                      accept=".md,text/markdown,text/plain"
                      className="hidden"
                      onChange={handleMarkdownFileChange}
                    />
                  </label>
                </div>
                <Textarea
                  value={strategyDoc}
                  onChange={(event) => setStrategyDoc(event.target.value)}
                  className="min-h-64 resize-y font-mono text-xs leading-6"
                  placeholder={t.chatPlaceholder}
                />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs text-muted-foreground">{t.strategyDocHint}</span>
                  <Button onClick={handleParseMarkdownStrategy} disabled={isParsingMarkdown}>
                    {isParsingMarkdown ? (
                      <><Loader2 className="h-4 w-4 animate-spin" />{t.parsingMemo}</>
                    ) : (
                      <><FileText className="h-4 w-4" />{t.parseMemo}</>
                    )}
                  </Button>
                </div>
                {markdownParseResult ? (
                  <div className="rounded-md border border-border bg-background p-3 text-sm text-muted-foreground">
                    <p>{markdownParseResult.source_summary}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Badge variant="outline">
                        {markdownParseResult.extracted_fields.length} {t.extractedFields}
                      </Badge>
                      <Badge variant="outline">
                        {markdownParseResult.assumption_log.length} {t.assumptions}
                      </Badge>
                      <Badge variant={markdownParseResult.ambiguities.length ? "destructive" : "outline"}>
                        {markdownParseResult.ambiguities.length} {t.ambiguities}
                      </Badge>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>

            {/* Validation State */}
            <section className="overflow-hidden rounded-lg border border-border bg-card/70">
              <div className="flex items-center gap-2 border-b border-border bg-muted/20 px-4 py-3">
                <FlaskConical className="h-4 w-4 text-primary" />
                <h2 className="font-heading text-base font-semibold">{t.validationTitle}</h2>
              </div>
              <div className="p-4">
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <Badge variant={validationIssues.length ? "destructive" : "outline"}>
                    {validationIssues.length ? t.needsAttention : t.readyToBacktest}
                  </Badge>
                  {clarifications.length ? (
                    <Badge variant="outline">
                      {clarifications.length} {t.clarificationPrompts}
                    </Badge>
                  ) : null}
                </div>
                {validationIssues.length ? (
                  <ul className="space-y-2 text-muted-foreground">
                    {validationIssues.map((issue) => (
                      <li key={issue}>• {issue}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground">{t.parserReady}</p>
                )}
                {clarifications.length ? (
                  <div className="rounded-md border border-border bg-background p-3 text-muted-foreground">
                    {clarifications.map((question) => (
                      <p key={question}>{question}</p>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            </section>

            {/* Compact capability glossary sidebar */}
            <CapabilityGlossary compact />
          </div>

          <div className="grid gap-6">
            {/* Template callouts */}
            {templateReviewCallout && (
              <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-sm text-yellow-300/80">
                Template loaded with default parameters. Review the rules and universe before running a backtest.
              </div>
            )}
            {showEtfProxyCaveat && activeTemplate?.etfProxyCaveat && (
              <div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-sm text-yellow-300/80">
                {activeTemplate.etfProxyCaveat}
              </div>
            )}

            {/* Strategy Preview */}
            <section ref={strategyPreviewRef} className="rounded-lg border border-border bg-card/70">
              <div className="flex flex-col gap-3 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-sm font-medium">{t.strategyPreviewTitle}</h2>
                  <p className="text-xs text-muted-foreground">{t.strategyPreviewDesc}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button onClick={handleRunBacktest} disabled={!strategy || isRunning}>
                    {isRunning ? (
                      <><Loader2 className="h-4 w-4 animate-spin" />{t.runningBacktest}</>
                    ) : (
                      <><Play className="h-4 w-4" />{t.runBacktest}</>
                    )}
                  </Button>
                  {backtestResult && !savedSlug && (
                    <Button variant="outline" size="sm" onClick={() => { setSaveName(strategy?.strategy_name ?? ""); setShowSaveDialog(true); }}>
                      Save Strategy
                    </Button>
                  )}
                  {savedSlug && (
                    <button
                      onClick={() => navigator.clipboard.writeText(`${window.location.origin}/strategies/${savedSlug}`)}
                      aria-label="Copy shareable strategy link"
                      className="cursor-pointer text-xs text-primary transition-colors duration-200 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                    >
                      {t.savedCopyLink}
                    </button>
                  )}
                </div>
              </div>
              {showSaveDialog && (
                <div className="flex items-center gap-2 border-b border-border px-4 py-3 bg-muted/30">
                  <input
                    autoFocus
                    type="text"
                    value={saveName}
                    onChange={(e) => setSaveName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleSaveStrategy(); if (e.key === "Escape") setShowSaveDialog(false); }}
                    placeholder={t.saveNamePlaceholder}
                    maxLength={80}
                    className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <Button size="sm" disabled={!saveName.trim() || isSaving} onClick={handleSaveStrategy}>
                    {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t.saveButtonLabel}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>{t.saveCancel}</Button>
                </div>
              )}
              {strategy ? (
                <div className="p-3 space-y-3">
                  {/* Compact defaults strip — shown before first backtest */}
                  {!backtestResult && (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                      <span className="font-medium">{t.defaultsTitle}:</span>
                      <span>{t.defaultBenchmark}: <strong>{strategy.benchmark}</strong></span>
                      <span>{strategy.start_date} → {strategy.end_date}</span>
                      <span>{strategy.transaction_cost_bps} bps / {strategy.slippage_bps} bps</span>
                    </div>
                  )}
                  {/* Tight 3-column form grid */}
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    <label className="space-y-1 text-xs">
                      <span className="font-medium text-muted-foreground">{t.strategyName}</span>
                      <Input className="h-8 text-xs"
                        value={strategy.strategy_name}
                        onChange={(event) => updateStrategyField("strategy_name", event.target.value)}
                      />
                    </label>
                    <label className="space-y-1 text-xs">
                      <span className="font-medium text-muted-foreground">{t.benchmark}</span>
                      <Input className="h-8 text-xs font-mono"
                        value={strategy.benchmark}
                        onChange={(event) => updateStrategyField("benchmark", event.target.value.toUpperCase())}
                      />
                    </label>
                    <label className="space-y-1 text-xs">
                      <span className="font-medium text-muted-foreground">{t.initialCapital}</span>
                      <Input className="h-8 text-xs" type="number"
                        value={strategy.initial_capital}
                        onChange={(event) => updateStrategyField("initial_capital", Number(event.target.value))}
                      />
                    </label>
                    <label className="space-y-1 text-xs">
                      <span className="font-medium text-muted-foreground">{t.startDate}</span>
                      <Input className="h-8 text-xs" type="date"
                        value={strategy.start_date}
                        onChange={(event) => updateStrategyField("start_date", event.target.value)}
                      />
                    </label>
                    <label className="space-y-1 text-xs">
                      <span className="font-medium text-muted-foreground">{t.endDate}</span>
                      <Input className="h-8 text-xs" type="date"
                        value={strategy.end_date}
                        onChange={(event) => updateStrategyField("end_date", event.target.value)}
                      />
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="space-y-1 text-xs">
                        <span className="font-medium text-muted-foreground">{t.transactionCost}</span>
                        <Input className="h-8 text-xs" type="number"
                          value={strategy.transaction_cost_bps}
                          onChange={(event) => updateStrategyField("transaction_cost_bps", Number(event.target.value))}
                        />
                      </label>
                      <label className="space-y-1 text-xs">
                        <span className="font-medium text-muted-foreground">{t.slippage}</span>
                        <Input className="h-8 text-xs" type="number"
                          value={strategy.slippage_bps}
                          onChange={(event) => updateStrategyField("slippage_bps", Number(event.target.value))}
                        />
                      </label>
                    </div>
                  </div>
                  {/* Universe row */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-muted-foreground">{t.universe}</span>
                      <div className="flex flex-wrap justify-end gap-1">
                        {strategy.universe.map((sym) => (
                          <DataStatusBadge key={sym} symbol={sym} />
                        ))}
                      </div>
                    </div>
                    <TickerSearch
                      value={strategy.universe}
                      onChange={(universe) => updateStrategyField("universe", universe)}
                      disabled={isRunning}
                    />
                    {strategy.universe.some((sym) => qualityReports[sym]) && (
                      <div className="space-y-1">
                        {strategy.universe.map((sym) => {
                          const q = qualityReports[sym];
                          if (!q) return null;
                          return (
                            <div key={sym} className="flex flex-wrap items-start gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-xs">
                              <Badge variant={q.status === "blocked" ? "destructive" : "outline"}
                                className={cn("text-[10px]", q.status === "warning" ? "border-amber-300 text-amber-700" : q.status === "ready" ? "border-emerald-300 text-emerald-700" : "")}>
                                {sym} · {q.status}
                              </Badge>
                              <span className="text-muted-foreground">{q.row_count} bars · {q.earliest_available_date} → {q.latest_available_date}</span>
                              {[...q.blocking_errors, ...q.warnings].slice(0, 1).map((msg) => (
                                <span key={msg} className="w-full text-muted-foreground">{msg}</span>
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  {/* Collapsible JSON preview */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowJsonPreview((v) => !v)}
                      className="cursor-pointer flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors duration-200"
                    >
                      <ArrowRight className={cn("h-3 w-3 transition-transform duration-200", showJsonPreview && "rotate-90")} />
                      {showJsonPreview ? t.hideJson : t.showJson}
                    </button>
                    {showJsonPreview && (
                      <pre className="mt-2 max-h-[180px] overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
                        {JSON.stringify(strategy, null, 2)}
                      </pre>
                    )}
                  </div>
                  {/* Markdown parse result — collapsible summary */}
                  {markdownParseResult && (
                    <div className="rounded-md border border-border bg-muted/30 p-3 text-xs space-y-1.5">
                      <p className="text-muted-foreground">{markdownParseResult.source_summary}</p>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline" className="text-[10px]">{markdownParseResult.extracted_fields.length} {t.extractedFields}</Badge>
                        <Badge variant="outline" className="text-[10px]">{markdownParseResult.assumption_log.length} {t.assumptions}</Badge>
                        <Badge variant={markdownParseResult.ambiguities.length ? "destructive" : "outline"} className="text-[10px]">
                          {markdownParseResult.ambiguities.length} {t.ambiguities}
                        </Badge>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">{t.parseFirst}</div>
              )}
            </section>

            {/* Results Tabs */}
            <section className="rounded-lg border border-border bg-card/70 p-4">
              <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="results">{t.tabBacktest}</TabsTrigger>
                  <TabsTrigger value="review">{t.tabReview}</TabsTrigger>
                  <TabsTrigger value="robustness">{t.tabRobustness}</TabsTrigger>
                  <TabsTrigger value="history">
                    {t.tabHistory}{runHistory.length > 0 && <span className="ml-1.5 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-mono text-primary">{runHistory.length}</span>}
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="results" className="space-y-6">
                  {!backtestResult && strategy && templateReviewCallout && !isRunning && (
                    <div className="flex flex-col items-center justify-center py-16 text-center space-y-2">
                      <p className="text-sm text-muted-foreground">{t.strategyLoaded}</p>
                      <p className="text-xs text-muted-foreground/60 max-w-xs">
                        Review the rules on the left, adjust the universe and date range for your hypothesis,
                        then run the backtest.
                      </p>
                    </div>
                  )}
                  {isRunning && (
                    <div className="space-y-6" aria-busy="true" aria-label="Running backtest…">
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <div key={i} className="rounded-lg border border-border bg-background px-4 py-3">
                            <div className="h-3 w-20 animate-pulse rounded bg-muted" />
                            <div className="mt-3 h-7 w-16 animate-pulse rounded bg-muted" />
                          </div>
                        ))}
                      </div>
                      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                        <div className="rounded-lg border border-border bg-background p-4">
                          <div className="mb-4 h-4 w-24 animate-pulse rounded bg-muted" />
                          <div className="h-48 animate-pulse rounded bg-muted" />
                        </div>
                        <div className="rounded-lg border border-border bg-background p-4">
                          <div className="mb-4 h-4 w-20 animate-pulse rounded bg-muted" />
                          <div className="space-y-3">
                            {Array.from({ length: 8 }).map((_, i) => (
                              <div key={i} className="flex justify-between">
                                <div className="h-3 w-28 animate-pulse rounded bg-muted" />
                                <div className="h-3 w-16 animate-pulse rounded bg-muted" />
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  {backtestResult && !isRunning ? (
                    <>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                        {[
                          { label: t.totalReturn, value: formatPercent(backtestResult.metrics.total_return), raw: backtestResult.metrics.total_return, type: "pnl" },
                          { label: t.sharpe, value: backtestResult.metrics.sharpe_ratio.toFixed(2), raw: backtestResult.metrics.sharpe_ratio, type: "ratio" },
                          { label: t.maxDrawdown, value: formatPercent(backtestResult.metrics.max_drawdown), raw: backtestResult.metrics.max_drawdown, type: "loss" },
                          { label: t.excessVsBenchmark, value: formatPercent(backtestResult.metrics.excess_return_vs_benchmark), raw: backtestResult.metrics.excess_return_vs_benchmark, type: "pnl" },
                          { label: t.trades, value: String(backtestResult.metrics.number_of_trades), raw: null, type: "neutral" },
                          ...(backtestResult.metrics.buy_and_hold_return != null
                            ? [{ label: t.buyAndHold, value: formatPercent(backtestResult.metrics.buy_and_hold_return), raw: backtestResult.metrics.buy_and_hold_return, type: "pnl" as const }]
                            : []),
                        ].map(({ label, value, raw, type }) => {
                          const isPositive = raw != null && raw > 0;
                          const isNegative = raw != null && raw < 0;
                          const isLoss = type === "loss";
                          const valueColor = isLoss
                            ? "text-[var(--loss)]"
                            : isPositive ? "text-[var(--profit)]"
                            : isNegative ? "text-[var(--loss)]"
                            : "text-foreground";
                          const borderColor = isLoss
                            ? "border-[var(--loss)]/20 hover:border-[var(--loss)]/40"
                            : isPositive ? "border-[var(--profit)]/20 hover:border-[var(--profit)]/40"
                            : isNegative ? "border-[var(--loss)]/20 hover:border-[var(--loss)]/40"
                            : "border-border hover:border-primary/30";
                          return (
                            <div key={label} className={`rounded-lg border bg-background px-4 py-3 transition-colors duration-200 hover:bg-card ${borderColor}`}>
                              <div className="text-xs text-muted-foreground">{label}</div>
                              <div className={`mt-2 font-mono text-2xl font-semibold tracking-tight ${valueColor}`}>{value}</div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                        <div className="rounded-lg border border-border bg-background p-4">
                          <div className="mb-4 flex items-center gap-2">
                            <LineChart className="h-4 w-4 text-primary" />
                            <h3 className="text-sm font-medium">{t.equityCurve}</h3>
                          </div>
                          <EquityCurveChart result={backtestResult} />
                        </div>
                        <div className="rounded-lg border border-border bg-background p-4">
                          <h3 className="mb-4 text-sm font-semibold">{t.keyMetrics}</h3>
                          <div className="space-y-2.5">
                            {([
                              { label: t.annualizedReturn, key: "annualized_return", pct: true },
                              { label: t.sharpeRatioLabel, key: "sharpe_ratio", pct: false },
                              { label: t.sortinoRatio, key: "sortino_ratio", pct: false },
                              { label: t.calmarRatio, key: "calmar_ratio", pct: false },
                              { label: t.winRateLabel, key: "win_rate", pct: true },
                              { label: t.avgTradeReturn, key: "avg_trade_return", pct: true },
                              { label: t.numOfTrades, key: "number_of_trades", pct: false },
                              { label: t.alphaVsBenchmark, key: "excess_return_vs_benchmark", pct: true },
                              { label: t.buyAndHoldReturn, key: "buy_and_hold_return", pct: true },
                            ] as { label: string; key: string; pct: boolean }[]).map(({ label, key, pct }) => {
                              const raw = (backtestResult.metrics as unknown as Record<string, number>)[key];
                              if (raw == null) return null;
                              const isPositive = raw > 0;
                              const isNegative = raw < 0;
                              const valueClass = isPositive ? "text-[var(--profit)] font-semibold" : isNegative ? "text-[var(--loss)] font-semibold" : "font-medium";
                              return (
                                <div key={key} className="flex items-center justify-between gap-4 border-b border-border/50 pb-2 last:border-0 last:pb-0">
                                  <span className="text-sm text-muted-foreground">{label}</span>
                                  <span className={`font-mono text-sm ${valueClass}`}>
                                    {pct ? formatPercent(raw) : formatNumber(raw)}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>

                      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
                        <div className="rounded-lg border border-border bg-background p-4">
                          <h3 className="mb-4 text-sm font-medium">{t.drawdownCurve}</h3>
                          <DrawdownChart result={backtestResult} />
                        </div>
                        <div className="rounded-lg border border-border bg-background p-4">
                          <h3 className="mb-4 text-sm font-medium">{t.annualReturns}</h3>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>{t.year}</TableHead>
                                <TableHead className="text-right">{t.return}</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {backtestResult.annual_returns.map((item) => (
                                <TableRow key={item.year}>
                                  <TableCell>{item.year}</TableCell>
                                  <TableCell className="text-right">{formatPercent(item.return_pct)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      <div className="rounded-lg border border-border bg-background p-4">
                        <h3 className="mb-4 text-sm font-medium">{t.monthlyHeatmap}</h3>
                        <MonthlyHeatmap result={backtestResult} />
                      </div>

                      <div className="rounded-lg border border-border bg-background p-4">
                        <div className="mb-4 flex items-center justify-between">
                          <h3 className="text-sm font-medium">{t.tradeLog}</h3>
                          {backtestResult.warnings.length ? (
                            <Badge variant="outline">
                              {backtestResult.warnings.length} {t.warningCount}
                            </Badge>
                          ) : null}
                        </div>
                        <ScrollArea className="h-[320px]">
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
                              {backtestResult.trade_log.map((trade, index) => (
                                <TableRow key={`${trade.symbol}-${trade.entry_date}-${index}`}>
                                  <TableCell>{trade.symbol}</TableCell>
                                  <TableCell>{trade.entry_date}</TableCell>
                                  <TableCell>{trade.exit_date}</TableCell>
                                  <TableCell className="text-right">{formatPercent(trade.return_pct)}</TableCell>
                                  <TableCell className="text-right">{trade.holding_period_days}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </ScrollArea>
                      </div>
                      {/* Disclaimer — always shown after results */}
                      <div className="flex items-start gap-2 rounded-lg border border-border bg-background px-4 py-3 text-xs text-muted-foreground leading-5">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-yellow-500/70" aria-hidden="true" />
                        <span>{t.backtestDisclaimer}</span>
                      </div>
                    </>
                  ) : (
                    !isRunning && (
                      <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                        {t.backtestEmpty}
                      </div>
                    )
                  )}
                </TabsContent>

                {/* Review tab — two-box: Strategy Explanation + AI Review */}
                <TabsContent value="review" className="space-y-0">
                  {!explanation && !sandboxReview ? (
                    <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
                      {t.reviewRunFirst}
                    </div>
                  ) : (
                    <div className="grid gap-4 lg:grid-cols-2">

                      {/* LEFT BOX — Strategy Explanation */}
                      <section className="rounded-xl border border-border bg-white shadow-sm">
                        <div className="border-b border-border px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 rounded-full bg-primary" aria-hidden="true" />
                            <h3 className="font-heading text-sm font-semibold">{t.strategyExplanationTitle}</h3>
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground">{t.strategyExplanationDesc}</p>
                        </div>
                        <div className="space-y-4 p-5">
                          {explanation ? (
                            <>
                              <div>
                                <p className="text-sm font-semibold text-foreground">{explanation.strategy_summary}</p>
                                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{explanation.performance_explanation}</p>
                              </div>
                              {explanationSections.map(({ title, items }) => (
                                <div key={title}>
                                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                  <ul className="space-y-1.5">
                                    {(items as string[]).map((item) => (
                                      <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                                        {item}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                              {explanation.disclaimer && (
                                <p className="text-xs text-muted-foreground border-t border-border pt-3">{explanation.disclaimer}</p>
                              )}
                            </>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t.explanationNotAvailable}</p>
                          )}
                        </div>
                      </section>

                      {/* RIGHT BOX — AI Review */}
                      <section className="rounded-xl border border-border bg-white shadow-sm">
                        <div className="border-b border-border px-5 py-3.5">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-2 rounded-full bg-[var(--warning-amber)]" aria-hidden="true" />
                              <h3 className="font-heading text-sm font-semibold">{t.aiReviewTitle}</h3>
                            </div>
                            {sandboxReview && (
                              <div className="flex items-center gap-2">
                                <Badge className={cn("capitalize text-xs font-semibold",
                                  sandboxReview.review_verdict === "promising"
                                    ? "bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                                    : sandboxReview.review_verdict === "untrusted"
                                    ? "bg-rose-50 text-rose-700 border-rose-300 hover:bg-rose-50"
                                    : "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-50"
                                )}>
                                  {sandboxReview.review_verdict}
                                </Badge>
                                <span className="text-xs text-muted-foreground font-mono">
                                  {sandboxReview.trust_score}/100
                                </span>
                              </div>
                            )}
                          </div>
                          <p className="mt-0.5 text-xs text-muted-foreground">{t.aiReviewDesc}</p>
                        </div>
                        <div className="space-y-4 p-5">
                          {sandboxReview ? (
                            <>
                              {/* Overfit risk + confidence */}
                              <div className="flex flex-wrap gap-2">
                                <Badge variant={sandboxReview.overfitting_risk === "high" ? "destructive" : "outline"}
                                  className={cn("text-xs", sandboxReview.overfitting_risk === "medium" ? "border-amber-300 text-amber-700 bg-amber-50" : sandboxReview.overfitting_risk === "low" ? "border-emerald-300 text-emerald-700 bg-emerald-50" : "")}>
                                  {t.overfitRiskLabel} {sandboxReview.overfitting_risk}
                                </Badge>
                                <Badge variant="outline" className="text-xs capitalize">
                                  {t.confidenceLabel} {sandboxReview.confidence_level}
                                </Badge>
                              </div>
                              {/* Overfit explanation */}
                              <p className="text-sm leading-relaxed text-muted-foreground">{sandboxReview.overfitting_risk_explanation}</p>
                              {/* Concerns */}
                              {sandboxConcernSections.map(({ title, items }) => (
                                <div key={title}>
                                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                  <ul className="space-y-1.5">
                                    {items.map((item) => (
                                      <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--warning-amber)]" aria-hidden="true" />
                                        {item}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                              {/* Improvement suggestions */}
                              {sandboxNextSteps.map(({ title, items }) => (
                                <div key={title}>
                                  <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
                                  <ul className="space-y-1.5">
                                    {items.map((item) => (
                                      <li key={item} className="flex gap-2 text-sm text-foreground/80">
                                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                                        {item}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                              {sandboxReview.final_warning && (
                                <p className="border-t border-border pt-3 text-xs text-[var(--loss)]">{sandboxReview.final_warning}</p>
                              )}
                            </>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t.reviewNotAvailable}</p>
                          )}
                        </div>
                      </section>

                    </div>
                  )}
                </TabsContent>

                <TabsContent value="robustness" className="space-y-4">
                  {/* Controls */}
                  <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4 sm:flex-row sm:items-end">
                    <div className="flex-1 space-y-1">
                      <label className="text-xs text-muted-foreground">{t.peerTickersLabel}</label>
                      <input
                        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder={t.peerTickersPlaceholder}
                        value={peerTickers}
                        onChange={(e) => setPeerTickers(e.target.value)}
                        disabled={isRunningRobustness}
                      />
                    </div>
                    <Button onClick={handleRunRobustness} disabled={!strategy || isRunningRobustness}>
                      {isRunningRobustness
                        ? <><Loader2 className="h-4 w-4 animate-spin" />{t.runningRobustness}</>
                        : t.runRobustness}
                    </Button>
                  </div>

                  {/* Results */}
                  {!robustnessJob && (
                    <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                      {t.robustnessEmpty}
                    </div>
                  )}
                  {robustnessJob?.status === "failed" && (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      {t.robustnessFailed} {robustnessJob.error}
                    </div>
                  )}
                  {robustnessJob && (robustnessJob.status === "pending" || robustnessJob.status === "running") && (
                    <div className="flex items-center gap-2 rounded-lg border border-border p-4 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t.runningRobustness}
                    </div>
                  )}
                  {robustnessJob?.status === "completed" && robustnessJob.results && (() => {
                    const r = robustnessJob.results;
                    return (
                      <div className="space-y-4">
                        {r.summary && (
                          <div className="rounded-lg border border-border bg-background px-4 py-3 text-sm text-muted-foreground">
                            <span className="font-medium text-foreground">{t.robustnessSummary}: </span>{r.summary}
                          </div>
                        )}
                        {r.parameter_sensitivity.length > 0 && (
                          <RobustnessTable title={t.paramSensitivityTitle}>
                            <TableHeader><TableRow>
                              <TableHead>{t.colParamSet}</TableHead>
                              <TableHead className="text-right">{t.colTotalReturn}</TableHead>
                              <TableHead className="text-right">{t.colSharpe}</TableHead>
                              <TableHead className="text-right">{t.colMaxDrawdown}</TableHead>
                              <TableHead>{t.colVerdict}</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>{r.parameter_sensitivity.map((row, i) => (
                              <TableRow key={i}>
                                <TableCell className="font-mono text-xs">{Object.entries(row.parameter_set).map(([k,v]) => `${k}=${v}`).join(", ")}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.total_return)}</TableCell>
                                <TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell>
                                <TableCell><VerdictBadge verdict={row.verdict} /></TableCell>
                              </TableRow>
                            ))}</TableBody>
                          </RobustnessTable>
                        )}
                        {r.subperiod.length > 0 && (
                          <RobustnessTable title={t.subperiodTitle}>
                            <TableHeader><TableRow>
                              <TableHead>{t.colPeriod}</TableHead>
                              <TableHead>{t.colStart}</TableHead>
                              <TableHead>{t.colEnd}</TableHead>
                              <TableHead className="text-right">{t.colTotalReturn}</TableHead>
                              <TableHead className="text-right">{t.colSharpe}</TableHead>
                              <TableHead className="text-right">{t.colMaxDrawdown}</TableHead>
                              <TableHead>{t.colVerdict}</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>{r.subperiod.map((row, i) => (
                              <TableRow key={i}>
                                <TableCell className="font-medium">{row.period}</TableCell>
                                <TableCell className="text-xs text-muted-foreground">{row.start_date}</TableCell>
                                <TableCell className="text-xs text-muted-foreground">{row.end_date}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.total_return)}</TableCell>
                                <TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell>
                                <TableCell><VerdictBadge verdict={row.verdict} /></TableCell>
                              </TableRow>
                            ))}</TableBody>
                          </RobustnessTable>
                        )}
                        {r.transaction_cost.length > 0 && (
                          <RobustnessTable title={t.txCostTitle}>
                            <TableHeader><TableRow>
                              <TableHead>{t.colCostBps}</TableHead>
                              <TableHead className="text-right">{t.colTotalReturn}</TableHead>
                              <TableHead className="text-right">{t.colSharpe}</TableHead>
                              <TableHead className="text-right">{t.colMaxDrawdown}</TableHead>
                              <TableHead>{t.colVerdict}</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>{r.transaction_cost.map((row, i) => (
                              <TableRow key={i}>
                                <TableCell>{row.cost_bps}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.total_return)}</TableCell>
                                <TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell>
                                <TableCell><VerdictBadge verdict={row.verdict} /></TableCell>
                              </TableRow>
                            ))}</TableBody>
                          </RobustnessTable>
                        )}
                        {r.benchmark_comparison.length > 0 && (
                          <RobustnessTable title={t.benchmarkCompTitle}>
                            <TableHeader><TableRow>
                              <TableHead>{t.colName}</TableHead>
                              <TableHead className="text-right">{t.colTotalReturn}</TableHead>
                              <TableHead className="text-right">{t.colSharpe}</TableHead>
                              <TableHead className="text-right">{t.colMaxDrawdown}</TableHead>
                              <TableHead className="text-right">{t.colExcess}</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>{r.benchmark_comparison.map((row, i) => (
                              <TableRow key={i}>
                                <TableCell className="font-medium">{row.name} <span className="text-xs text-muted-foreground">({row.symbol})</span></TableCell>
                                <TableCell className="text-right">{formatPercent(row.total_return)}</TableCell>
                                <TableCell className="text-right">{row.sharpe_ratio.toFixed(2)}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.max_drawdown)}</TableCell>
                                <TableCell className="text-right">{formatPercent(row.excess_return_vs_strategy)}</TableCell>
                              </TableRow>
                            ))}</TableBody>
                          </RobustnessTable>
                        )}
                        {r.peer_ticker.length > 0 && (
                          <RobustnessTable title={t.peerTickerTitle}>
                            <TableHeader><TableRow>
                              <TableHead>{t.colTicker}</TableHead>
                              <TableHead className="text-right">{t.colTotalReturn}</TableHead>
                              <TableHead className="text-right">{t.colSharpe}</TableHead>
                              <TableHead className="text-right">{t.colMaxDrawdown}</TableHead>
                              <TableHead>{t.colVerdict}</TableHead>
                            </TableRow></TableHeader>
                            <TableBody>{r.peer_ticker.map((row, i) => (
                              <TableRow key={i}>
                                <TableCell className="font-medium">{row.ticker}</TableCell>
                                <TableCell className="text-right">{row.verdict === "error" ? "—" : formatPercent(row.total_return)}</TableCell>
                                <TableCell className="text-right">{row.verdict === "error" ? "—" : row.sharpe_ratio.toFixed(2)}</TableCell>
                                <TableCell className="text-right">{row.verdict === "error" ? "—" : formatPercent(row.max_drawdown)}</TableCell>
                                <TableCell><VerdictBadge verdict={row.verdict} /></TableCell>
                              </TableRow>
                            ))}</TableBody>
                          </RobustnessTable>
                        )}
                      </div>
                    );
                  })()}
                </TabsContent>

                {/* History tab — all past runs */}
                <TabsContent value="history" className="space-y-3">
                  {runHistory.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
                      {t.historyEmpty}
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-muted-foreground">{t.historyCount(runHistory.length)}</p>
                        <button
                          type="button"
                          onClick={() => { setRunHistory([]); localStorage.removeItem(RUN_HISTORY_KEY); }}
                          className="cursor-pointer text-xs text-muted-foreground hover:text-destructive transition-colors duration-200"
                        >
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
                            <div key={entry.id} className={cn(
                              "rounded-lg border p-3 transition-colors duration-200",
                              isActive ? "border-primary/40 bg-primary/5" : "border-border bg-background hover:border-primary/20 hover:bg-muted/30"
                            )}>
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2">
                                    {isActive && <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" aria-label="Current run" />}
                                    <span className="font-heading text-sm font-semibold truncate">{entry.strategyName}</span>
                                    {idx === 0 && !isActive && <Badge variant="outline" className="text-[10px] shrink-0">{t.historyLatest}</Badge>}
                                  </div>
                                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                                    <span className="font-mono">{entry.universe.join(", ")}</span>
                                    <span>{entry.startDate} → {entry.endDate}</span>
                                    <span>{new Date(entry.runAt).toLocaleString()}</span>
                                  </div>
                                  {!isActive && (
                                    <button
                                      type="button"
                                      onClick={() => handleRestoreFromHistory(entry)}
                                      className="mt-2 cursor-pointer rounded-md border border-primary/30 bg-primary/5 px-3 py-1 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    >
                                      {t.historyRestore}
                                    </button>
                                  )}
                                  {isActive && (
                                    <span className="mt-2 inline-block text-xs text-primary font-medium">{t.historyCurrentlyViewing}</span>
                                  )}
                                </div>
                                <div className="flex shrink-0 gap-4 text-right text-xs">
                                  <div>
                                    <div className="text-[10px] text-muted-foreground">{t.historyColReturn}</div>
                                    <div className={cn("font-mono font-semibold", ret >= 0 ? "text-[var(--profit)]" : "text-[var(--loss)]")}>
                                      {formatPercent(ret)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] text-muted-foreground">{t.sharpe}</div>
                                    <div className={cn("font-mono font-semibold", sharpe >= 1 ? "text-[var(--profit)]" : sharpe < 0 ? "text-[var(--loss)]" : "text-foreground")}>
                                      {sharpe.toFixed(2)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] text-muted-foreground">{t.historyColMaxDD}</div>
                                    <div className="font-mono font-semibold text-[var(--loss)]">{formatPercent(dd)}</div>
                                  </div>
                                  {entry.sandboxReview && (
                                    <div>
                                      <div className="text-[10px] text-muted-foreground">{t.historyColTrust}</div>
                                      <div className="font-mono font-semibold">{entry.sandboxReview.trust_score}/100</div>
                                    </div>
                                  )}
                                </div>
                              </div>
                              {entry.sandboxReview && (
                                <div className="mt-2 flex items-center gap-2">
                                  <Badge className={cn("text-[10px] capitalize",
                                    entry.sandboxReview.review_verdict === "promising"
                                      ? "bg-[var(--profit-muted)] text-[var(--profit)] hover:bg-[var(--profit-muted)]"
                                      : entry.sandboxReview.review_verdict === "untrusted"
                                      ? "bg-[var(--loss-muted)] text-[var(--loss)] hover:bg-[var(--loss-muted)]"
                                      : "bg-primary/10 text-primary hover:bg-primary/10"
                                  )}>
                                    {entry.sandboxReview.review_verdict}
                                  </Badge>
                                  <span className="text-[10px] text-muted-foreground">{t.historyOverfit} {entry.sandboxReview.overfitting_risk}</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}
                </TabsContent>
              </Tabs>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
