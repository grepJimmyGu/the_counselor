import type {
  AssetBehaviorFingerprint,
  BacktestResult,
  CompanyProfile,
  DataQualityReport,
  DataStatusResponse,
  DiagnoseResponse,
  EntitlementErrorResponse,
  ExplanationResponse,
  FundamentalSummary,
  Holding,
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

/**
 * API base URL resolution.
 *
 * Priority:
 *   1. `NEXT_PUBLIC_API_BASE_URL` baked in at build time (production + any
 *      preview where Jimmy set it explicitly on Vercel).
 *   2. Runtime host check on the client: if the page is served from
 *      localhost/127.0.0.1, use the local FastAPI dev port (8001).
 *   3. Otherwise (Vercel preview deployments without the env var,
 *      static-export sites, anywhere not localhost) fall back to the
 *      production Railway URL so the page doesn't try to fetch from a
 *      127.0.0.1 that doesn't exist for the visitor.
 *
 * Why: 2026-05-21 — the PR #41 Market Pulse preview rendered with empty
 * data because Vercel didn't inject NEXT_PUBLIC_API_BASE_URL for the
 * Preview environment, the old fallback was `http://127.0.0.1:8001`, and
 * the visitor's browser had nothing at that port. Switching the default
 * to the production URL means previews work for anyone who can reach
 * the preview, env-var or not.
 */
const PROD_API_FALLBACK = "https://thecounselor-production.up.railway.app";
const LOCAL_API_FALLBACK = "http://127.0.0.1:8001";

function deriveApiBaseUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv) return fromEnv;
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return LOCAL_API_FALLBACK;
    }
  }
  return PROD_API_FALLBACK;
}

export const API_BASE_URL = deriveApiBaseUrl();

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

/** Module 2 — fetch the Asset Behavior Fingerprint for a single ticker.
 *  Backend route: `GET /api/assets/{symbol}/behavior` (no auth required). */
export async function getAssetBehavior(symbol: string): Promise<AssetBehaviorFingerprint> {
  return fetchApi<AssetBehaviorFingerprint>(
    `/api/assets/${encodeURIComponent(symbol.toUpperCase())}/behavior`,
  );
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
  // CN A-shares use their own overview endpoint (FMP + AKShare)
  const isCn = symbol.toUpperCase().endsWith(".SS") || symbol.toUpperCase().endsWith(".SZ");
  if (isCn) {
    return fetchApi(`/api/cn/company/${encodeURIComponent(symbol)}/overview`);
  }
  return fetchApi(`/api/company/${encodeURIComponent(symbol)}/overview`);
}

export async function getStockTrend(symbol: string): Promise<import("@/lib/contracts").StockTrendData> {
  const isCn = symbol.toUpperCase().endsWith(".SS") || symbol.toUpperCase().endsWith(".SZ");
  if (isCn) {
    return fetchApi(`/api/cn/company/${encodeURIComponent(symbol)}/trend`);
  }
  return fetchApi(`/api/company/${encodeURIComponent(symbol)}/trend`);
}

export async function getCommodityTrend(commodity: string): Promise<import("@/lib/contracts").StockTrendData> {
  return fetchApi(`/api/commodities/${encodeURIComponent(commodity)}/trend`);
}

/**
 * Max time the browser waits for `/api/market/pulse` before aborting.
 *
 * **Why 30 seconds:** during the 2026-06-07 outage, the backend held
 * connections open for ~180s waiting on wedged asyncio locks. Without
 * a client-side timeout, `fetch` inherits the browser's default
 * (often 5+ minutes) and the page hangs that long for users. 30s is a
 * generous ceiling for the warm path (~2s) and the worst observed cold
 * path (~20s with overlay) while still aborting fast enough that the
 * page's fallback-cache UI (`StaleDataBanner`) kicks in promptly when
 * something is wrong.
 */
const MARKET_PULSE_TIMEOUT_MS = 30_000;

export async function getMarketPulse(
  market: "US" | "CN" = "US",
  bypassCache = false,
): Promise<import("@/lib/contracts").MarketPulseResponse> {
  const qs = bypassCache ? `&bypass_cache=true` : "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MARKET_PULSE_TIMEOUT_MS);
  try {
    return await fetchApi<import("@/lib/contracts").MarketPulseResponse>(
      `/api/market/pulse?market=${market}${qs}`,
      { signal: controller.signal },
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function getSectorComparison(
  symbol: string,
  range: "1M" | "6M" | "YTD" | "1Y" | "3Y" = "1Y",
): Promise<import("@/lib/contracts").SectorComparisonResponse> {
  return fetchApi(
    `/api/market/sector-comparison/${encodeURIComponent(symbol)}?range=${range}`,
  );
}

export async function getHistoryRhymes(
  market: "US" | "CN" = "US",
): Promise<import("@/lib/contracts").HistoryRhymesResponse> {
  return fetchApi(`/api/market/history-rhymes?market=${market}`);
}

export async function getDataLatency(): Promise<import("@/lib/contracts").DataLatencyResponse> {
  return fetchApi(`/api/market/data-latency`);
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

// Phase 1f — preset screens (Market Pulse Section 6 cards)
export async function getScreenerPresets(): Promise<import("@/lib/contracts").ScreenerPresetsResponse> {
  return fetchApi("/api/screener/presets");
}

export async function getScreenerPresetResults(
  slug: string,
  limit = 50,
  offset = 0,
  opts: { backendToken?: string } = {},
): Promise<import("@/lib/contracts").ScreenerResponse> {
  const headers: Record<string, string> = {};
  if (opts.backendToken) headers["Authorization"] = `Bearer ${opts.backendToken}`;
  return fetchApi(
    `/api/screener/preset/${encodeURIComponent(slug)}?limit=${limit}&offset=${offset}`,
    { headers },
  );
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

// ── PRD-16c-3c — Active execution dashboard endpoints ──────────────────────

export interface UniverseSymbolState {
  symbol: string;
  latest_price: number | null;
  latest_at: string | null;
  source: "intraday" | "no_data" | string;
}

export interface UniverseStateResponse {
  strategy_id: string;
  bar_resolution: string;
  universe: UniverseSymbolState[];
  generated_at: string;
}

export interface PositionView {
  id: string;
  symbol: string;
  entered_at: string;
  entry_price: number;
  shares_initial: number;
  shares_remaining: number;
  is_open: boolean;
  closed_at: string | null;
  final_pnl: number | null;
  latest_price: number | null;
  pct_change_from_entry: number | null;
  trade_log: Array<Record<string, unknown>>;
}

export interface PositionsResponse {
  strategy_id: string;
  positions: PositionView[];
  open_count: number;
  closed_count: number;
}

export interface TradeEvent {
  position_id: string;
  symbol: string;
  event: string;
  timestamp: string;
  price?: number | null;
  shares?: number | null;
  shares_sold?: number | null;
  tier_label?: string | null;
}

export interface TradeLogResponse {
  strategy_id: string;
  events: TradeEvent[];
  total: number;
  next_before: string | null;
}

export async function getUniverseState(
  strategyId: string,
  backendToken: string,
): Promise<UniverseStateResponse> {
  return fetchApi<UniverseStateResponse>(
    `/api/saved-strategies/${strategyId}/universe-state`,
    { headers: { Authorization: `Bearer ${backendToken}` } },
  );
}

export async function getStrategyPositions(
  strategyId: string,
  backendToken: string,
): Promise<PositionsResponse> {
  return fetchApi<PositionsResponse>(
    `/api/saved-strategies/${strategyId}/positions`,
    { headers: { Authorization: `Bearer ${backendToken}` } },
  );
}

/** active-execution-v2 PR2: declare a real position the user holds, to be
 *  tracked against the strategy's exit ladder. `entry_price` is the
 *  user's actual average cost basis — Livermore never simulates a fill. */
export interface DeclarePositionRequest {
  symbol: string;
  shares: number;
  entry_price: number;
  entered_at?: string;
}

export async function declarePosition(
  strategyId: string,
  payload: DeclarePositionRequest,
  backendToken: string,
): Promise<PositionView> {
  return fetchApi<PositionView>(
    `/api/saved-strategies/${strategyId}/positions`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${backendToken}` },
      body: JSON.stringify(payload),
    },
  );
}

/** active-execution-v2 PR3: confirm the user executed a pending exit tier
 *  in their brokerage. Decrements the tracked position to match the
 *  user's real fill — Livermore never sells. */
export interface ConfirmExitRequest {
  trigger_type: string;
  shares_sold: number;
  fill_price?: number;
}

export async function confirmPositionExit(
  strategyId: string,
  positionId: string,
  payload: ConfirmExitRequest,
  backendToken: string,
): Promise<PositionView> {
  return fetchApi<PositionView>(
    `/api/saved-strategies/${strategyId}/positions/${positionId}/confirm-exit`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${backendToken}` },
      body: JSON.stringify(payload),
    },
  );
}

export async function getStrategyTradeLog(
  strategyId: string,
  backendToken: string,
  opts: { limit?: number; before?: string } = {},
): Promise<TradeLogResponse> {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.before) params.set("before", opts.before);
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : "";
  return fetchApi<TradeLogResponse>(
    `/api/saved-strategies/${strategyId}/trade-log${suffix}`,
    { headers: { Authorization: `Bearer ${backendToken}` } },
  );
}

// ── intraday live chart (price trend + tier lines + trigger markers) ─────────

export interface IntradayChartBar {
  t: string;
  close: number;
}

export interface IntradayChartTier {
  label: string;
  trigger_pct: number;
  price_level: number | null;
}

export interface IntradayChartEvent {
  t: string;
  price: number | null;
  event: string;
  tier_label: string | null;
}

export interface IntradayChartSeries {
  position_id: string;
  symbol: string;
  is_open: boolean;
  entry_at: string | null;
  entry_price: number | null;
  bars: IntradayChartBar[];
  tiers: IntradayChartTier[];
  events: IntradayChartEvent[];
}

export interface IntradayChartResponse {
  strategy_id: string;
  bar_resolution: string;
  generated_at: string;
  series: IntradayChartSeries[];
}

export async function getIntradayChart(
  strategyId: string,
  backendToken: string,
): Promise<IntradayChartResponse> {
  return fetchApi<IntradayChartResponse>(
    `/api/saved-strategies/${strategyId}/intraday-chart`,
    { headers: { Authorization: `Bearer ${backendToken}` } },
  );
}

// ── Signal alerts (PR #83 endpoints, wired into UI by PR-E) ──────────────────
// All three require `SIGNAL_ALERTS_ENABLED=true` on Railway. Without it,
// the routes 404.

export interface SignalSubscriptionStatus {
  subscription_active: boolean;
}

export interface SavedStrategySignalState {
  saved_strategy_id: string;
  current_signal: Record<string, unknown> | null;
  current_signal_display: string | null;
  as_of_date: string | null;
  last_changed_at: string | null;
  subscription_active: boolean;
  recent_events: Array<{
    id: string;
    previous_signal_display: string | null;
    new_signal_display: string;
    change_type: string;
    as_of_date: string;
    reference_price_snapshot: Record<string, unknown> | null;
  }>;
}

/** Fetch the cached signal state for a saved strategy. Returns `null` if
 *  the signal-alerts feature is disabled on the backend (route 404s) so
 *  callers can render a graceful fallback. */
export async function getSavedStrategySignal(
  strategyId: string,
  backendToken: string,
): Promise<SavedStrategySignalState | null> {
  try {
    return await fetchApi<SavedStrategySignalState>(
      `/api/saved-strategies/${strategyId}/signal`,
      { headers: { Authorization: `Bearer ${backendToken}` } },
    );
  } catch (err) {
    if (err instanceof Error && /\b404\b/.test(err.message)) return null;
    throw err;
  }
}

/** Opt the current user into email alerts for a saved strategy.
 *  Idempotent: re-calling flips `email_enabled` back to true if the
 *  row exists but was disabled. Returns 401 if anonymous (caller
 *  handles via SoftPaywall). */
export async function subscribeSignalAlert(
  strategyId: string,
  backendToken: string,
): Promise<SignalSubscriptionStatus> {
  return fetchApi(`/api/saved-strategies/${strategyId}/signal/subscribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

/** Opt out — deletes the subscription row. Idempotent. */
export async function unsubscribeSignalAlert(
  strategyId: string,
  backendToken: string,
): Promise<void> {
  await fetchApi(`/api/saved-strategies/${strategyId}/signal/subscribe`, {
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

// ── Email preferences (Stage 6a → extended by PRD-19 Step 4a) ────────────────
// Canonical types live in `contracts.ts` (EmailPreferences,
// EmailPreferencesUpdate). PRD-19 Step 4a extended the shape with
// `signal_alerts_enabled`, `daily_digest_enabled`, `silent_days_enabled`.
//
// `EmailPreferencesResponse` kept here as a legacy alias for any caller
// that imported the Stage 6a name. New callers should import
// `EmailPreferences` from `contracts.ts` directly. Helpers
// (`getEmailPreferences`, `updateEmailPreferences`) live in the PRD-19
// section below.
import type { EmailPreferences as EmailPreferencesAlias } from "./contracts";
export type EmailPreferencesResponse = EmailPreferencesAlias;

// PRD-13b — Portfolio Mode diagnose endpoint.
export async function diagnosePortfolio(
  holdings: Holding[],
  backendToken?: string,
): Promise<DiagnoseResponse> {
  const headers: Record<string, string> = {};
  if (backendToken) {
    headers["Authorization"] = `Bearer ${backendToken}`;
  }
  return fetchApi<DiagnoseResponse>("/api/portfolio/diagnose", {
    method: "POST",
    headers,
    body: JSON.stringify({ holdings }),
  });
}

// ── CN market (Phase 3c) ──────────────────────────────────────────────────────

export interface CnSearchResult {
  symbol: string;
  name_cn: string;
  exchange: string;
}

export async function searchCnStocks(q: string): Promise<CnSearchResult[]> {
  return fetchApi(`/api/cn/stocks/search?q=${encodeURIComponent(q)}`);
}

export interface CnIndicatorPoint {
  date: string;
  value: number;
}

export interface CnIndicatorResponse {
  symbol: string;
  function: string;
  points: CnIndicatorPoint[];
  latest_value: number | null;
  high: number | null;
  low: number | null;
  signal: string | null;
}

export async function getCnIndicator(
  symbol: string,
  func: string,
  timePeriod: number,
  range_: string,
): Promise<CnIndicatorResponse> {
  return fetchApi(
    `/api/cn/indicators?symbol=${encodeURIComponent(symbol)}&function=${func}&time_period=${timePeriod}&range=${range_}`,
  );
}

// ── PRD-16a Signal Library helpers ──────────────────────────────────────────

import type {
  MatchTemplatesRequest,
  MatchTemplatesResponse,
  SignalPreviewResponse,
  SignalPrimitivesResponse,
} from "./contracts";
import {
  readCachedVersionHash,
  readCatalogCache,
  writeCatalogCache,
} from "./signal-library/catalog-cache";

/** Fetch the signal-primitive catalog. Uses localStorage cache + ETag
 *  conditional GET to minimize cold-load cost.
 *
 *  Flow:
 *    1. Send `If-None-Match: "<cached_version_hash>"` if we have one.
 *    2. If server responds 304, reuse the cached payload (zero bytes
 *       deserialized from network).
 *    3. If server responds 200, store the new payload in localStorage
 *       (keyed by its content hash).
 *
 *  When localStorage is empty + server responds 200, we just write the
 *  cache. When localStorage has stale content + server responds 200, we
 *  overwrite. The two paths converge: after this function returns, the
 *  cache reflects the server's truth.
 */
export async function getSignalPrimitives(): Promise<SignalPrimitivesResponse> {
  const cachedHash = readCachedVersionHash();
  const headers: Record<string, string> = {};
  if (cachedHash) headers["If-None-Match"] = `"${cachedHash}"`;

  const response = await fetch(`${API_BASE_URL}/api/signal-primitives`, {
    method: "GET",
    headers,
  });

  if (response.status === 304) {
    const cached = readCatalogCache();
    if (cached) return cached.payload;
    // Cache claimed the hash matched but the body wasn't there —
    // shouldn't happen, but force a re-fetch without the header.
    const fresh = await fetch(`${API_BASE_URL}/api/signal-primitives`);
    const body = (await fresh.json()) as SignalPrimitivesResponse;
    writeCatalogCache(body);
    return body;
  }

  if (!response.ok) {
    throw new Error(`Catalog fetch failed: ${response.status}`);
  }
  const body = (await response.json()) as SignalPrimitivesResponse;
  writeCatalogCache(body);
  return body;
}

/** Fetch a sample series for one primitive — used by the preview chart
 *  in the catalog browser. `paramOverrides` are passed as query-string
 *  values; the backend accepts known param names per the primitive's
 *  schema (e.g. `period=21` on RSI). */
export async function previewSignalPrimitive(
  primitiveId: string,
  opts: {
    symbol?: string;
    days?: number;
    paramOverrides?: Record<string, string | number>;
  } = {},
): Promise<SignalPreviewResponse> {
  const query = new URLSearchParams();
  if (opts.symbol) query.set("symbol", opts.symbol);
  if (opts.days) query.set("days", String(opts.days));
  if (opts.paramOverrides) {
    for (const [k, v] of Object.entries(opts.paramOverrides)) {
      query.set(k, String(v));
    }
  }
  const qs = query.toString();
  const path = `/api/signal-primitives/${encodeURIComponent(primitiveId)}/preview${
    qs ? `?${qs}` : ""
  }`;
  return fetchApi<SignalPreviewResponse>(path);
}

/** Send the user's selected primitive IDs to the KB matcher; receive
 *  top-N template suggestions with per-primitive thresholds.
 *  Deterministic and pure on the backend — same request always gets
 *  the same response. */
export async function matchSignalCombosToTemplates(
  body: MatchTemplatesRequest,
): Promise<MatchTemplatesResponse> {
  return fetchApi<MatchTemplatesResponse>("/api/signal-combos/match-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── PRD-19 Step 5: notification surface API helpers ─────────────────────────

import type {
  EmailPreferences,
  EmailPreferencesUpdate,
  MarkAsExecutedRequest,
  MarkAsExecutedResponse,
  PendingNotificationBanner,
} from "./contracts";

/** Fetch pending in-app banner entries for the current user.
 *  Returns the empty array when the user is unauthenticated (401 from
 *  backend), so callers can treat "no banners" and "not signed in"
 *  identically at the render layer. */
export async function getPendingNotifications(
  backendToken: string,
): Promise<PendingNotificationBanner[]> {
  try {
    return await fetchApi<PendingNotificationBanner[]>(
      "/api/me/notifications/pending",
      {
        headers: { Authorization: `Bearer ${backendToken}` },
      },
    );
  } catch {
    // 401 / 404 → render as empty. Banner is non-critical; never blocks page.
    return [];
  }
}

/** Acknowledge (soft-delete) a banner entry. Backend returns 204 with no
 *  body, which fetchApi tolerates. */
export async function ackNotificationBanner(
  entryId: number,
  backendToken: string,
): Promise<void> {
  await fetchApi<unknown>(`/api/me/notifications/${entryId}/ack`, {
    method: "POST",
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

/** Log that the user acted on the latest signal for this strategy.
 *  Idempotent — second click on the same notification returns
 *  `idempotent: true` and the existing row's `executed_at`. */
export async function markStrategyExecuted(
  strategyId: string,
  body: MarkAsExecutedRequest,
  backendToken: string,
): Promise<MarkAsExecutedResponse> {
  return fetchApi<MarkAsExecutedResponse>(
    `/api/saved-strategies/${encodeURIComponent(strategyId)}/mark-executed`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${backendToken}`,
      },
      body: JSON.stringify(body),
    },
  );
}

/** Read the current user's notification preferences — `EmailPreference`
 *  row with the 3 legacy marketing flags + the 3 PRD-19 flags. */
export async function getEmailPreferences(
  backendToken: string,
): Promise<EmailPreferences> {
  return fetchApi<EmailPreferences>("/api/me/email-preferences", {
    headers: { Authorization: `Bearer ${backendToken}` },
  });
}

/** Partial-update the user's notification preferences. Omit fields to
 *  leave unchanged. PATCHing a re-enable on ANY flag clears the global
 *  `unsubscribed_at`; disabling a single flag does NOT. */
export async function updateEmailPreferences(
  payload: EmailPreferencesUpdate,
  backendToken: string,
): Promise<EmailPreferences> {
  return fetchApi<EmailPreferences>("/api/me/email-preferences", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${backendToken}`,
    },
    body: JSON.stringify(payload),
  });
}
