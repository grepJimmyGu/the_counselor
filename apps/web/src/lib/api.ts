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

export async function saveStrategy(
  backtestId: string,
  name: string,
  isPublic = true,
  resultPayload?: object,
  strategyType?: string,
): Promise<{ slug: string; url: string; is_public: boolean }> {
  // Attempt 1: lightweight request (no payload) — works for strategies run on production
  try {
    return await fetchApi<{ slug: string; url: string; is_public: boolean }>(
      "/api/strategies/save",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backtest_id: backtestId, name, is_public: isPublic }),
      }
    );
  } catch (firstErr: unknown) {
    // Only retry with full payload if the record genuinely doesn't exist (404)
    // For any other error (already saved, network, etc.) surface immediately
    const is404 =
      firstErr instanceof Error &&
      (firstErr.message.includes("404") || firstErr.message.toLowerCase().includes("not found"));

    if (!is404 || !resultPayload) throw firstErr;

    // Attempt 2: full payload — for strategies run locally / on a different DB
    return fetchApi<{ slug: string; url: string; is_public: boolean }>(
      "/api/strategies/save",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          backtest_id: backtestId,
          name,
          is_public: isPublic,
          result_payload: resultPayload,
          strategy_type: strategyType ?? "unknown",
        }),
      }
    );
  }
}

export async function updateStrategyVisibility(
  slug: string,
  isPublic: boolean
): Promise<{ slug: string; is_public: boolean }> {
  return fetchApi<{ slug: string; is_public: boolean }>(
    `/api/strategies/${slug}/visibility`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_public: isPublic }),
    }
  );
}

export async function getPublicStrategies(
  limit = 20
): Promise<import("@/lib/contracts").PublicStrategyItem[]> {
  return fetchApi(`/api/strategies/public?limit=${limit}`);
}

export async function getStrategyLivePerformance(
  slug: string,
  refresh = false
): Promise<import("@/lib/contracts").LivePerformance> {
  return fetchApi(`/api/strategies/${slug}/live-performance${refresh ? "?refresh=true" : ""}`);
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

export async function getCompanyOverview(symbol: string): Promise<import("@/lib/contracts").CompanyOverviewResponse> {
  return fetchApi(`/api/company/${encodeURIComponent(symbol)}/overview`);
}

// ── PRD-07: Stock Screener ────────────────────────────────────────────────────

export async function getScreenerFilters(): Promise<import("@/lib/contracts").ScreenerFiltersResponse> {
  return fetchApi("/api/screener/filters");
}

export async function getScreenerResults(params: Record<string, string | number | undefined>): Promise<import("@/lib/contracts").ScreenerResponse> {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== "" && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  return fetchApi(`/api/screener/results${qs ? `?${qs}` : ""}`);
}

// ── PRD-09/10: News & Sentiment ───────────────────────────────────────────────

export async function getSentimentSummary(
  symbol: string,
  refresh = false
): Promise<import("@/lib/contracts").SentimentSummaryResponse> {
  return fetchApi(`/api/sentiment/${encodeURIComponent(symbol)}/summary${refresh ? "?refresh=true" : ""}`);
}

export async function getSentimentNews(symbol: string): Promise<import("@/lib/contracts").NewsArticle[]> {
  return fetchApi(`/api/sentiment/${encodeURIComponent(symbol)}/news`);
}

export async function getSentimentCommunity(symbol: string): Promise<import("@/lib/contracts").CommunityMention[]> {
  return fetchApi(`/api/sentiment/${encodeURIComponent(symbol)}/community`);
}

export async function getProvidersStatus(): Promise<import("@/lib/contracts").ProvidersStatusResponse> {
  return fetchApi("/api/sentiment/providers/status");
}

export async function getSentimentToolkits(): Promise<import("@/lib/contracts").SentimentToolkit[]> {
  return fetchApi("/api/sentiment/toolkits");
}

export async function runSentimentAnalyze(
  symbols: string[],
  toolkitId?: string,
  refresh = false
): Promise<import("@/lib/contracts").SentimentAnalyzeResponse> {
  return fetchApi("/api/sentiment/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols, toolkit_id: toolkitId ?? null, refresh }),
  });
}

export async function runSentimentReview(
  symbol: string,
  sentimentSummary: object
): Promise<import("@/lib/contracts").SentimentSandboxResponse> {
  return fetchApi("/api/sentiment/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, sentiment_summary: sentimentSummary }),
  });
}
