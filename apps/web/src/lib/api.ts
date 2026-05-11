import type {
  BacktestResult,
  CompanyProfile,
  DataQualityReport,
  DataStatusResponse,
  ExplanationResponse,
  FundamentalSummary,
  KeyMetrics,
  MarketSnapshotItem,
  PriceBarResponse,
  RobustnessJobResponse,
  SavedStrategy,
  SandboxReviewResponse,
  StrategyChatResponse,
  StrategyMarkdownParseResponse,
  StrategyJson,
  SymbolSearchItem,
  WarmupResponse,
} from "@/lib/contracts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        message = payload.detail;
      }
    } catch {}
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function parseStrategy(
  userMessage: string,
  previousStrategyJson?: StrategyJson | null,
  previousBacktestId?: string | null,
  locale = "en",
) {
  return fetchApi<StrategyChatResponse>("/api/chat/strategy", {
    method: "POST",
    body: JSON.stringify({
      user_message: userMessage,
      previous_strategy_json: previousStrategyJson ?? undefined,
      previous_backtest_id: previousBacktestId ?? undefined,
      locale,
    }),
  });
}

export async function parseStrategyMarkdown(
  markdownContent: string,
  documentName?: string | null,
  locale = "en",
) {
  return fetchApi<StrategyMarkdownParseResponse>("/api/strategy/parse-markdown", {
    method: "POST",
    body: JSON.stringify({
      markdown_content: markdownContent,
      document_name: documentName ?? undefined,
      locale,
    }),
  });
}

export async function runBacktest(strategyJson: StrategyJson) {
  return fetchApi<BacktestResult>("/api/backtest/run", {
    method: "POST",
    body: JSON.stringify({ strategy_json: strategyJson }),
  });
}

export async function explainStrategy(
  strategyJson: StrategyJson,
  backtestResult: BacktestResult,
  locale = "en",
) {
  return fetchApi<ExplanationResponse>("/api/insights/explain", {
    method: "POST",
    body: JSON.stringify({
      strategy_json: strategyJson,
      backtest_result: backtestResult,
      locale,
    }),
  });
}

export async function reviewSandbox(
  strategyJson: StrategyJson,
  backtestResult: BacktestResult,
  priorIterations: string[] = [],
  locale = "en",
  iterationCount = 1,
) {
  return fetchApi<SandboxReviewResponse>("/api/review/sandbox", {
    method: "POST",
    body: JSON.stringify({
      strategy_json: strategyJson,
      backtest_result: backtestResult,
      prior_iterations: priorIterations,
      iteration_count: iterationCount,
      locale,
    }),
  });
}

export async function searchSymbols(query: string): Promise<SymbolSearchItem[]> {
  return fetchApi<SymbolSearchItem[]>(
    `/api/symbols/search?query=${encodeURIComponent(query)}`,
  );
}

export async function getDataStatus(symbol: string): Promise<DataStatusResponse> {
  return fetchApi<DataStatusResponse>(`/api/data/status/${symbol}`);
}

export async function getDataQuality(symbol: string): Promise<DataQualityReport> {
  return fetchApi<DataQualityReport>(`/api/data/quality/${symbol}`);
}

export async function warmupSymbols(
  symbols: string[],
  lookbackDays = 252,
): Promise<WarmupResponse> {
  return fetchApi<WarmupResponse>("/api/data/warmup", {
    method: "POST",
    body: JSON.stringify({ symbols, lookback_days: lookbackDays }),
  });
}

export async function runRobustness(
  strategyJson: StrategyJson,
  testsToRun: string[],
  peerTickers: string[] = [],
): Promise<RobustnessJobResponse> {
  return fetchApi<RobustnessJobResponse>("/api/robustness/run", {
    method: "POST",
    body: JSON.stringify({
      strategy_json: strategyJson,
      tests_to_run: testsToRun,
      peer_tickers: peerTickers,
    }),
  });
}

export async function getRobustnessJob(runId: string): Promise<RobustnessJobResponse> {
  return fetchApi<RobustnessJobResponse>(`/api/robustness/${runId}`);
}

export async function saveStrategy(backtestId: string, name: string): Promise<{ slug: string; url: string }> {
  return fetchApi<{ slug: string; url: string }>("/api/strategies/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backtest_id: backtestId, name }),
  });
}

export async function getSavedStrategy(slug: string): Promise<SavedStrategy> {
  return fetchApi<SavedStrategy>(`/api/strategies/${slug}`);
}

export async function getMarketOverview(symbols: string[]): Promise<MarketSnapshotItem[]> {
  return fetchApi<MarketSnapshotItem[]>(`/api/market/overview?symbols=${symbols.join(",")}`);
}

export async function getDailyPrices(symbol: string): Promise<PriceBarResponse[]> {
  return fetchApi<PriceBarResponse[]>(`/api/data/daily/${encodeURIComponent(symbol)}`);
}

export async function searchSymbolsApi(query: string): Promise<SymbolSearchItem[]> {
  return fetchApi<SymbolSearchItem[]>(`/api/symbols/search?query=${encodeURIComponent(query)}`);
}

// ── PRD-06: Fundamental Analysis ─────────────────────────────────────────────

export async function getFundamentalProfile(symbol: string): Promise<CompanyProfile> {
  return fetchApi<CompanyProfile>(`/api/fundamental/profile/${encodeURIComponent(symbol)}`);
}

export async function getFundamentalMetrics(symbol: string): Promise<KeyMetrics> {
  return fetchApi<KeyMetrics>(`/api/fundamental/metrics/${encodeURIComponent(symbol)}`);
}

export async function getFundamentalOverview(symbol: string): Promise<FundamentalSummary> {
  return fetchApi<FundamentalSummary>(`/api/fundamental/overview/${encodeURIComponent(symbol)}`);
}
