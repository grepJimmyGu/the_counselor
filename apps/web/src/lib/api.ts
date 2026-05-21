import type {
  BacktestResult,
  CompanyProfile,
  DataQualityReport,
  DataStatusResponse,
  EntitlementErrorResponse,
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
import { dispatchUpgrade } from "@/lib/upgrade-modal-event-bus";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

/**
 * Custom Error thrown on 402 responses. Carries the parsed envelope so callers
 * can react (e.g. show an inline SoftPaywall instead of the global modal).
 * The global modal is ALSO dispatched automatically — callers don't have to
 * do anything to get it.
 */
export class UpgradeRequiredError extends Error {
  readonly status = 402;
  constructor(public readonly entitlement: EntitlementErrorResponse["entitlement"]) {
    super(entitlement.detail);
    this.name = "UpgradeRequiredError";
  }
}

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
    // Read the body once. `response.json()` consumes the stream — calling it
    // twice (as the old implementation did) silently failed because the
    // second read always threw, which masked any detail string we could have
    // surfaced.
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON response. Leave body=null and fall through to generic.
    }

    // 402 Upgrade Required — dispatch the global modal.
    //
    // FastAPI wraps `HTTPException(detail=<envelope>)` inside `{ detail: ... }`,
    // so the EntitlementErrorResponse lives at `body.detail` (not `body`).
    // Accept both shapes defensively in case a route ever returns the
    // envelope raw (Pydantic response_model) instead of via HTTPException.
    if (response.status === 402 && body && typeof body === "object") {
      const root = body as Record<string, unknown>;
      const candidate =
        root.detail && typeof root.detail === "object"
          ? (root.detail as Record<string, unknown>)
          : root;
      if (
        candidate.error === "upgrade_required" &&
        candidate.entitlement &&
        typeof candidate.entitlement === "object"
      ) {
        const envelope = candidate as unknown as EntitlementErrorResponse;
        dispatchUpgrade(envelope.entitlement);
        throw new UpgradeRequiredError(envelope.entitlement);
      }
    }

    // Generic error path: surface the backend's `detail` text when it's a
    // string (FastAPI's default for HTTPException(detail="...")).
    let message = `Request failed with status ${response.status}`;
    if (body && typeof body === "object") {
      const detail = (body as Record<string, unknown>).detail;
      if (typeof detail === "string") {
        message = detail;
      }
    }
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

export async function runBacktest(
  strategyJson: StrategyJson,
  opts: { backendToken?: string; templateId?: string } = {},
) {
  const headers: Record<string, string> = {};
  if (opts.backendToken) {
    headers["Authorization"] = `Bearer ${opts.backendToken}`;
  }
  return fetchApi<BacktestResult>("/api/backtest/run", {
    method: "POST",
    headers,
    body: JSON.stringify({
      strategy_json: strategyJson,
      // Stage 3: when set, templates bypass the custom-strategy caps.
      ...(opts.templateId ? { template_id: opts.templateId } : {}),
    }),
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
  opts: { backendToken?: string } = {},
): Promise<RobustnessJobResponse> {
  const headers: Record<string, string> = {};
  if (opts.backendToken) {
    headers["Authorization"] = `Bearer ${opts.backendToken}`;
  }
  return fetchApi<RobustnessJobResponse>("/api/robustness/run", {
    method: "POST",
    headers,
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
  backendToken: string,
  backtestId: string,
  name: string,
  isPublic = true,
  resultPayload?: object,
  strategyType?: string,
): Promise<{ slug: string; url: string; is_public: boolean }> {
  // `backendToken` is required (added 2026-05-20 after the QA audit found
  // /api/strategies/save was completely unauthenticated). The backend now
  // 401s if the Authorization header is missing — and Scout tier saves
  // additionally have their is_public forced to True regardless of what we
  // send here, by `saved_strategies_always_public`.
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${backendToken}`,
  };
  // Attempt 1: lightweight request (no payload) — works for strategies run on production
  try {
    return await fetchApi<{ slug: string; url: string; is_public: boolean }>(
      "/api/strategies/save",
      {
        method: "POST",
        headers,
        body: JSON.stringify({ backtest_id: backtestId, name, is_public: isPublic }),
      }
    );
  } catch (firstErr: unknown) {
    // Only retry with full payload if the record genuinely doesn't exist (404)
    // For any other error (already saved, 402, 401, network, etc.) surface immediately
    const is404 =
      firstErr instanceof Error &&
      (firstErr.message.includes("404") || firstErr.message.toLowerCase().includes("not found"));

    if (!is404 || !resultPayload) throw firstErr;

    // Attempt 2: full payload — for strategies run locally / on a different DB
    return fetchApi<{ slug: string; url: string; is_public: boolean }>(
      "/api/strategies/save",
      {
        method: "POST",
        headers,
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
  backendToken: string,
  slug: string,
  isPublic: boolean
): Promise<{ slug: string; is_public: boolean }> {
  return fetchApi<{ slug: string; is_public: boolean }>(
    `/api/strategies/${slug}/visibility`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${backendToken}`,
      },
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

export async function getStockTrend(symbol: string): Promise<import("@/lib/contracts").StockTrendData> {
  return fetchApi(`/api/company/${encodeURIComponent(symbol)}/trend`);
}

export async function getCommodityTrend(commodity: string): Promise<import("@/lib/contracts").StockTrendData> {
  return fetchApi(`/api/commodities/${encodeURIComponent(commodity)}/trend`);
}

export async function getMarketPulse(market: "US" | "CN" = "US", bypassCache = false): Promise<import("@/lib/contracts").MarketPulseResponse> {
  const qs = bypassCache ? `&bypass_cache=true` : "";
  return fetchApi(`/api/market/pulse?market=${market}${qs}`);
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

// ── Billing (Stage 2) ─────────────────────────────────────────────────────────

export async function getPricing(): Promise<import("@/lib/contracts").PricingPage> {
  return fetchApi("/api/billing/pricing");
}

export async function startTrial(
  tier: "strategist" | "quant",
  backendToken: string,
): Promise<{ trial_end: string; tier: string }> {
  return fetchApi("/api/billing/trial/start", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` },
    body: JSON.stringify({ tier }),
  });
}

export async function createCheckoutSession(
  params: { tier: "strategist" | "quant"; billing_cycle: "monthly" | "annual"; return_url: string },
  backendToken: string,
): Promise<{ url: string }> {
  return fetchApi("/api/billing/checkout/session", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${backendToken}` },
    body: JSON.stringify(params),
  });
}

export async function createPortalSession(backendToken: string): Promise<{ url: string }> {
  return fetchApi("/api/billing/portal", {
    method: "POST",
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

// ── Anonymous one-shot (Stage 1a) ─────────────────────────────────────────────

export async function getAnonymousEntitlements(): Promise<
  import("@/lib/contracts").AnonymousEntitlements
> {
  return fetchApi("/api/anonymous/entitlements", { credentials: "include" });
}

export async function anonymousBacktestRun(
  payload: {
    template_id: string;
    strategy_json: unknown;
    via_handle?: string;
  },
): Promise<import("@/lib/contracts").BacktestResult> {
  return fetchApi("/api/anonymous/backtest/run", {
    method: "POST",
    body: JSON.stringify(payload),
    credentials: "include", // sets/reads livermore_anon_id cookie
  });
}

// ── Saved strategies (Stage 1a) ───────────────────────────────────────────────

export async function listSavedStrategies(
  backendToken: string,
): Promise<import("@/lib/contracts").UserSavedStrategy[]> {
  return fetchApi("/api/saved-strategies", {
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

export async function createSavedStrategy(
  payload: {
    title: string;
    strategy_json: unknown;
    is_public?: boolean;
    backtest_record_id?: string;
  },
  backendToken: string,
): Promise<import("@/lib/contracts").UserSavedStrategy> {
  return fetchApi("/api/saved-strategies", {
    method: "POST",
    headers: { Authorization: `Bearer ${backendToken}` },
    body: JSON.stringify(payload),
  });
}

export async function deleteSavedStrategy(
  strategyId: string,
  backendToken: string,
): Promise<void> {
  await fetchApi(`/api/saved-strategies/${strategyId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

// ── Community publish (Stage 4a) ──────────────────────────────────────────────

export async function publishStrategy(
  payload: {
    title: string;
    description?: string;
    strategy_json: unknown;
    backtest_record_id?: string;
    equity_curve_snapshot?: Array<{ date: string | null; equity: number | null; benchmark: number | null }>;
  },
  backendToken: string,
): Promise<import("@/lib/contracts").PublishedStrategyDetail> {
  return fetchApi("/api/community/strategies", {
    method: "POST",
    headers: { Authorization: `Bearer ${backendToken}` },
    body: JSON.stringify(payload),
  });
}

export async function listPublishedStrategies(
  params: {
    sort?: "trending" | "newest" | "top_returns" | "top_sharpe";
    strategy_type?: string;
    ticker?: string;
    handle?: string;
    page?: number;
    page_size?: number;
  } = {},
): Promise<import("@/lib/contracts").PublishedStrategyFeed> {
  const qs = new URLSearchParams();
  if (params.sort) qs.set("sort", params.sort);
  if (params.strategy_type) qs.set("strategy_type", params.strategy_type);
  if (params.ticker) qs.set("ticker", params.ticker);
  if (params.handle) qs.set("handle", params.handle);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const path = qs.toString()
    ? `/api/community/strategies?${qs.toString()}`
    : "/api/community/strategies";
  return fetchApi(path);
}

export async function getPublishedStrategy(
  slug: string,
): Promise<import("@/lib/contracts").PublishedStrategyDetail> {
  return fetchApi(`/api/community/strategies/${slug}`);
}

export async function trackAttributionVisit(
  payload: { url: string; via: string },
): Promise<{ tracked: boolean }> {
  return fetchApi("/api/community/attribution/track", {
    method: "POST",
    body: JSON.stringify(payload),
    credentials: "include", // sets/reads livermore_vsid cookie
  });
}

// ── Email preferences (Stage 6a) ──────────────────────────────────────────────

export interface EmailPreferencesResponse {
  transactional: boolean;
  weekly_digest: boolean;
  upsell_nudges: boolean;
  creator_program: boolean;
  unsubscribed_at: string | null;
}

export async function getEmailPreferences(
  backendToken: string,
): Promise<EmailPreferencesResponse> {
  return fetchApi("/api/me/email-preferences", {
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

export async function updateEmailPreferences(
  payload: {
    weekly_digest?: boolean;
    upsell_nudges?: boolean;
    creator_program?: boolean;
  },
  backendToken: string,
): Promise<EmailPreferencesResponse> {
  return fetchApi("/api/me/email-preferences", {
    method: "PATCH",
    headers: { Authorization: `Bearer ${backendToken}` },
    body: JSON.stringify(payload),
  });
}
