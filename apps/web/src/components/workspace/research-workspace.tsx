"use client";

import { useMemo, useState, type ChangeEvent } from "react";
import {
  ArrowRight,
  Bot,
  CircleAlert,
  FileText,
  FlaskConical,
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
  parseStrategy,
  parseStrategyMarkdown,
  reviewSandbox,
  runBacktest,
  runRobustness,
} from "@/lib/api";
import {
  demoMarkdownStrategy,
  demoStrategies,
  type BacktestResult,
  type DataQualityReport,
  type ExplanationResponse,
  type RobustnessJobResponse,
  type SandboxReviewResponse,
  type StrategyMarkdownParseResponse,
  type StrategyJson,
} from "@/lib/contracts";
import { useLocale } from "@/lib/locale-context";
import { LanguageSwitcher } from "@/components/language-switcher";
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

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type ComparisonRow = {
  label: string;
  current: number;
  previous: number;
};

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
      ? "border-emerald-500/50 text-emerald-400"
      : verdict === "worse" || verdict === "weak" || verdict === "breaks_down" || verdict === "untrusted"
      ? "border-rose-500/50 text-rose-400"
      : "text-muted-foreground";
  return <Badge variant="outline" className={`capitalize text-xs ${color}`}>{verdict.replace(/_/g, " ")}</Badge>;
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
  labels: { totalReturn: string; sharpe: string; maxDrawdown: string; trades: string },
): ComparisonRow[] {
  if (!current || !previous) return [];
  return [
    { label: labels.totalReturn, current: current.metrics.total_return, previous: previous.metrics.total_return },
    { label: labels.sharpe, current: current.metrics.sharpe_ratio, previous: previous.metrics.sharpe_ratio },
    { label: labels.maxDrawdown, current: current.metrics.max_drawdown, previous: previous.metrics.max_drawdown },
    { label: "Win Rate", current: current.metrics.win_rate, previous: previous.metrics.win_rate },
    { label: "Turnover", current: current.metrics.turnover, previous: previous.metrics.turnover },
  ];
}

export function ResearchWorkspace() {
  const { locale, t } = useLocale();

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

  const comparisonRows = useMemo(
    () => buildComparison(backtestResult, previousResult, { totalReturn: t.totalReturn, sharpe: t.sharpe, maxDrawdown: t.maxDrawdown, trades: t.trades }),
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

  async function handleInterpretStrategy(nextPrompt?: string) {
    const activePrompt = nextPrompt ?? prompt;
    setIsParsing(true);
    setErrorMessage(null);
    setChat((current) => [...current, { role: "user", content: activePrompt }]);

    try {
      const parsed = await parseStrategy(activePrompt, strategy, backtestResult?.backtest_id ?? null, locale);
      setChat((current) => [...current, { role: "assistant", content: parsed.assistant_message }]);
      setStrategy(parsed.strategy_json);
      if (parsed.strategy_json) fetchQualityForSymbols(parsed.strategy_json.universe);
      setMarkdownParseResult(null);
      setValidationIssues(parsed.missing_fields);
      setClarifications(parsed.clarification_questions);
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
      { role: "assistant", content: `Loaded: ${displayPrompt}. Review the strategy and click Run Backtest.` },
    ]);
    fetchQualityForSymbols(demo.strategy.universe);
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
        <header className="flex flex-col gap-3 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge className="bg-primary/15 text-primary hover:bg-primary/15">{t.appName}</Badge>
              <Badge variant="outline">{t.localMvp}</Badge>
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">{t.workspaceTitle}</h1>
              <p className="max-w-3xl text-sm text-muted-foreground">{t.workspaceDesc}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <div className="rounded-md border border-border px-3 py-1.5">{t.noLiveTrading}</div>
            <div className="rounded-md border border-border px-3 py-1.5">{t.priceBasedOnly}</div>
            <div className="rounded-md border border-border px-3 py-1.5">{t.deterministicEngine}</div>
            <LanguageSwitcher />
          </div>
        </header>

        {errorMessage ? (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <CircleAlert className="mt-0.5 h-4 w-4" />
            <span>{errorMessage}</span>
          </div>
        ) : null}

        {/* Demo picker */}
        <section className="rounded-lg border border-border bg-card/70 p-4">
          <div className="mb-3">
            <div className="text-sm font-medium">{t.demosTitle}</div>
            <p className="text-xs text-muted-foreground">{t.demosSubtitle}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {demoStrategies.map((demo) => (
              <button
                key={demo.label}
                type="button"
                onClick={() => handleLoadDemo(demo)}
                className="rounded-md border border-border bg-background px-3 py-2 text-left text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
              >
                {locale === "zh" ? demo.labelZh : demo.label}
              </button>
            ))}
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="grid gap-6">
            {/* Chat Builder */}
            <section className="rounded-lg border border-border bg-card/70">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-primary" />
                  <h2 className="text-sm font-medium">{t.chatBuilderTitle}</h2>
                </div>
                <Badge variant="outline">{t.strategyParser}</Badge>
              </div>
              <div className="space-y-4 p-4">
                <div className="flex flex-wrap gap-2">
                  {t.demoPrompts.map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setPrompt(item)}
                      className="rounded-md border border-border bg-background px-2.5 py-1.5 text-left text-xs text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
                    >
                      {item}
                    </button>
                  ))}
                </div>
                <Textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  className="min-h-36 resize-none"
                  placeholder={t.chatPlaceholder}
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
                        "rounded-lg border px-3 py-2 text-sm",
                        message.role === "assistant"
                          ? "border-border bg-background"
                          : "border-primary/25 bg-primary/10",
                      )}
                    >
                      <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                        {message.role === "assistant" ? t.aiLabel : t.youLabel}
                      </div>
                      <p className="whitespace-pre-wrap leading-6">{message.content}</p>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </section>

            {/* Strategy Doc */}
            <section className="rounded-lg border border-border bg-card/70">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  <h2 className="text-sm font-medium">{t.strategyDocTitle}</h2>
                </div>
                <Badge variant="outline">{t.markdownIntake}</Badge>
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
            <section className="rounded-lg border border-border bg-card/70 p-4">
              <div className="mb-3 flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-medium">{t.validationTitle}</h2>
              </div>
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
            </section>
          </div>

          <div className="grid gap-6">
            {/* Strategy Preview */}
            <section className="rounded-lg border border-border bg-card/70">
              <div className="flex flex-col gap-3 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-sm font-medium">{t.strategyPreviewTitle}</h2>
                  <p className="text-xs text-muted-foreground">{t.strategyPreviewDesc}</p>
                </div>
                <Button onClick={handleRunBacktest} disabled={!strategy || isRunning}>
                  {isRunning ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />{t.runningBacktest}</>
                  ) : (
                    <><Play className="h-4 w-4" />{t.runBacktest}</>
                  )}
                </Button>
              </div>
              {strategy ? (
                <div className="grid gap-6 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.strategyName}</span>
                      <Input
                        value={strategy.strategy_name}
                        onChange={(event) => updateStrategyField("strategy_name", event.target.value)}
                      />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.benchmark}</span>
                      <Input
                        value={strategy.benchmark}
                        onChange={(event) => updateStrategyField("benchmark", event.target.value.toUpperCase())}
                      />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.startDate}</span>
                      <Input
                        type="date"
                        value={strategy.start_date}
                        onChange={(event) => updateStrategyField("start_date", event.target.value)}
                      />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.endDate}</span>
                      <Input
                        type="date"
                        value={strategy.end_date}
                        onChange={(event) => updateStrategyField("end_date", event.target.value)}
                      />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.initialCapital}</span>
                      <Input
                        type="number"
                        value={strategy.initial_capital}
                        onChange={(event) => updateStrategyField("initial_capital", Number(event.target.value))}
                      />
                    </label>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-muted-foreground">{t.universe}</span>
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
                        <div className="mt-2 space-y-1">
                          {strategy.universe.map((sym) => {
                            const q = qualityReports[sym];
                            if (!q) return null;
                            return (
                              <div key={sym} className="flex flex-wrap items-start gap-2 rounded-md border border-border bg-background px-3 py-2 text-xs">
                                <Badge variant={q.status === "blocked" ? "destructive" : q.status === "warning" ? "outline" : "outline"}
                                  className={q.status === "warning" ? "border-yellow-500/50 text-yellow-400" : q.status === "ready" ? "border-emerald-500/50 text-emerald-400" : ""}>
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
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.transactionCost}</span>
                      <Input
                        type="number"
                        value={strategy.transaction_cost_bps}
                        onChange={(event) => updateStrategyField("transaction_cost_bps", Number(event.target.value))}
                      />
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="text-muted-foreground">{t.slippage}</span>
                      <Input
                        type="number"
                        value={strategy.slippage_bps}
                        onChange={(event) => updateStrategyField("slippage_bps", Number(event.target.value))}
                      />
                    </label>
                  </div>
                  <div className="space-y-4">
                    <div className="space-y-3">
                      <div className="text-sm font-medium">{t.strategyJson}</div>
                      <pre className="max-h-[280px] overflow-auto rounded-lg border border-border bg-background p-3 text-xs leading-6 text-muted-foreground">
                        {JSON.stringify(strategy, null, 2)}
                      </pre>
                    </div>
                    {markdownParseResult ? (
                      <>
                        <div className="rounded-lg border border-border bg-background p-3">
                          <div className="text-sm font-medium">{t.sourceSummary}</div>
                          <p className="mt-2 text-xs leading-6 text-muted-foreground">
                            {markdownParseResult.source_summary}
                          </p>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="rounded-lg border border-border bg-background p-3">
                            <div className="text-sm font-medium">{t.assumptionsTitle}</div>
                            <ul className="mt-2 space-y-2 text-xs leading-5 text-muted-foreground">
                              {markdownParseResult.assumption_log.length ? (
                                markdownParseResult.assumption_log.map((item) => (
                                  <li key={item}>• {item}</li>
                                ))
                              ) : (
                                <li>{t.noAssumptions}</li>
                              )}
                            </ul>
                          </div>
                          <div className="rounded-lg border border-border bg-background p-3">
                            <div className="text-sm font-medium">{t.ambiguitiesTitle}</div>
                            <ul className="mt-2 space-y-2 text-xs leading-5 text-muted-foreground">
                              {markdownParseResult.ambiguities.length ? (
                                markdownParseResult.ambiguities.map((item) => (
                                  <li key={item}>• {item}</li>
                                ))
                              ) : (
                                <li>{t.noAmbiguities}</li>
                              )}
                            </ul>
                          </div>
                        </div>
                        <div className="rounded-lg border border-border bg-background p-3">
                          <div className="mb-2 text-sm font-medium">{t.extractionTrace}</div>
                          <ScrollArea className="h-[220px]">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>{t.field}</TableHead>
                                  <TableHead>{t.status}</TableHead>
                                  <TableHead>{t.value}</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {markdownParseResult.extracted_fields.map((f) => (
                                  <TableRow key={f.field}>
                                    <TableCell>{f.field}</TableCell>
                                    <TableCell><Badge variant="outline">{f.status}</Badge></TableCell>
                                    <TableCell className="text-xs text-muted-foreground">{f.value}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </ScrollArea>
                        </div>
                      </>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="p-8 text-sm text-muted-foreground">{t.parseFirst}</div>
              )}
            </section>

            {/* Results Tabs */}
            <section className="rounded-lg border border-border bg-card/70 p-4">
              <Tabs defaultValue="dashboard" className="space-y-4">
                <TabsList className="grid w-full grid-cols-5">
                  <TabsTrigger value="dashboard">{t.tabBacktest}</TabsTrigger>
                  <TabsTrigger value="explanation">{t.tabExplanation}</TabsTrigger>
                  <TabsTrigger value="sandbox">{t.tabSandbox}</TabsTrigger>
                  <TabsTrigger value="robustness">{t.tabRobustness}</TabsTrigger>
                  <TabsTrigger value="comparison">{t.tabComparison}</TabsTrigger>
                </TabsList>

                <TabsContent value="dashboard" className="space-y-6">
                  {backtestResult ? (
                    <>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                        {[
                          [t.totalReturn, formatPercent(backtestResult.metrics.total_return)],
                          [t.sharpe, backtestResult.metrics.sharpe_ratio.toFixed(2)],
                          [t.maxDrawdown, formatPercent(backtestResult.metrics.max_drawdown)],
                          [t.excessVsBenchmark, formatPercent(backtestResult.metrics.excess_return_vs_benchmark)],
                          [t.trades, String(backtestResult.metrics.number_of_trades)],
                          ...(backtestResult.metrics.buy_and_hold_return != null
                            ? [["Buy & Hold", formatPercent(backtestResult.metrics.buy_and_hold_return)]]
                            : []),
                        ].map(([label, value]) => (
                          <div key={label} className="rounded-lg border border-border bg-background px-4 py-3">
                            <div className="text-xs text-muted-foreground">{label}</div>
                            <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
                          </div>
                        ))}
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
                          <h3 className="mb-4 text-sm font-medium">{t.metricsDetail}</h3>
                          <div className="space-y-2 text-sm">
                            {Object.entries(backtestResult.metrics).map(([key, value]) => (
                              <div key={key} className="flex items-center justify-between gap-4">
                                <span className="text-muted-foreground">{key.replaceAll("_", " ")}</span>
                                <span className="font-medium">
                                  {typeof value === "number" ? formatNumber(value) : value}
                                </span>
                              </div>
                            ))}
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
                    </>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                      {t.backtestEmpty}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="explanation" className="space-y-4">
                  {explanation ? (
                    <>
                      <section className="rounded-lg border border-border bg-background p-4">
                        <h3 className="text-sm font-medium">{explanation.strategy_summary}</h3>
                        <p className="mt-3 text-sm leading-6 text-muted-foreground">
                          {explanation.performance_explanation}
                        </p>
                      </section>
                      <div className="grid gap-4 lg:grid-cols-2">
                        {explanationSections.map(({ title, items }) => (
                          <section key={title} className="rounded-lg border border-border bg-background p-4">
                            <h3 className="text-sm font-medium">{title}</h3>
                            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                              {(items as string[]).map((item) => (
                                <li key={item}>• {item}</li>
                              ))}
                            </ul>
                          </section>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">{explanation.disclaimer}</p>
                    </>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                      {t.explanationEmpty}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="sandbox" className="space-y-4">
                  {sandboxReview ? (
                    <>
                      {/* Verdict header */}
                      <section className="rounded-lg border border-border bg-background p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className="bg-primary/15 text-primary hover:bg-primary/15 capitalize">
                            {sandboxReview.review_verdict}
                          </Badge>
                          <Badge variant={
                            sandboxReview.overfitting_risk === "high" ? "destructive"
                            : sandboxReview.overfitting_risk === "medium" ? "outline"
                            : "outline"
                          } className={sandboxReview.overfitting_risk === "medium" ? "border-yellow-500/50 text-yellow-400" : ""}>
                            {t.overfittingRiskLabel}: {sandboxReview.overfitting_risk}
                          </Badge>
                          <div className="text-sm text-muted-foreground">
                            {t.trustScore}{" "}
                            <span className="font-semibold text-foreground">
                              {sandboxReview.trust_score}/100
                            </span>
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {t.confidenceLevel}{" "}
                            <span className="font-semibold text-foreground">
                              {sandboxReview.confidence_level}
                            </span>
                          </div>
                        </div>
                        <p className="mt-4 text-sm leading-6 text-muted-foreground">
                          {sandboxReview.overfitting_risk_explanation}
                        </p>
                      </section>

                      {/* Trust / distrust + all concerns */}
                      <div className="grid gap-4 lg:grid-cols-2">
                        {sandboxConcernSections.map(({ title, items }) => (
                          <section key={title} className="rounded-lg border border-border bg-background p-4">
                            <h3 className="text-sm font-medium">{title}</h3>
                            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                              {items.map((item) => (
                                <li key={item}>• {item}</li>
                              ))}
                            </ul>
                          </section>
                        ))}
                      </div>

                      {/* Next steps */}
                      {sandboxNextSteps.length > 0 && (
                        <div className="grid gap-4 lg:grid-cols-2">
                          {sandboxNextSteps.map(({ title, items }) => (
                            <section key={title} className="rounded-lg border border-border bg-background p-4">
                              <h3 className="text-sm font-medium">{title}</h3>
                              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                                {items.map((item) => (
                                  <li key={item}>• {item}</li>
                                ))}
                              </ul>
                            </section>
                          ))}
                        </div>
                      )}

                      <p className="text-sm text-rose-300">{sandboxReview.final_warning}</p>
                    </>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                      {t.sandboxEmpty}
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

                <TabsContent value="comparison" className="space-y-4">
                  {comparisonRows.length ? (
                    <section className="rounded-lg border border-border bg-background p-4">
                      <div className="mb-4 flex items-center gap-2">
                        <ArrowRight className="h-4 w-4 text-primary" />
                        <h3 className="text-sm font-medium">{t.comparisonTitle}</h3>
                      </div>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t.metric}</TableHead>
                            <TableHead className="text-right">{t.current}</TableHead>
                            <TableHead className="text-right">{t.previous}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {comparisonRows.map(({ label, current, previous }) => (
                            <TableRow key={label}>
                              <TableCell>{label}</TableCell>
                              <TableCell className="text-right">{formatNumber(current)}</TableCell>
                              <TableCell className="text-right">{formatNumber(previous)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </section>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
                      {t.comparisonEmpty}
                    </div>
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
