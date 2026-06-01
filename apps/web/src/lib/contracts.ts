// ── Identity & Entitlements (Stage 1) ────────────────────────────────────────

export type Tier = "scout" | "strategist" | "quant";

export type PlanStatus = "active" | "trialing" | "past_due" | "canceled";

export interface UserPublic {
  id: string;
  handle: string | null;
  display_name: string | null;
  avatar_url: string | null;
  locale: string;
}

export interface PlanInfo {
  tier: Tier;
  status: PlanStatus;
  billing_cycle: "monthly" | "annual" | null;
  trial_end: string | null;
  current_period_end: string | null;
}

export interface UsageThisMonth {
  period_start: string;
  backtest_runs: number;
  robustness_runs: number;
  saved_strategies_count: number;
}

export interface UserMe extends UserPublic {
  email: string;
  created_at: string;
  plan: PlanInfo;
  usage: UsageThisMonth;
}

export interface Entitlements {
  tier: Tier;
  // Stage 1a changes:
  //   backtest_runs_remaining → custom_backtest_runs_remaining (weekly, custom only)
  //   added week_start so the UI can render "resets Monday"
  //   added template_runs_unlimited (templates exempt from custom caps)
  //   universe_size_max → universe_size_max_custom
  //   history_window_years → history_window_years_custom
  //   added saved_strategies_always_public (Scout-only force-public)
  //   removed api_access (deferred indefinitely)
  status: PlanStatus;
  custom_backtest_runs_remaining: number | null;
  week_start: string; // ISO date of the current week's Monday (UTC)
  template_runs_unlimited: boolean;
  universe_size_max_custom: number;
  history_window_years_custom: number;
  asset_classes: ("equities" | "commodities" | "a_shares")[];
  robustness_tests: string[];
  market_pulse_ticker_scope: "top_250" | "all_us" | "all_us_plus_alerts";
  business_model_section: "full" | "full_plus_supply_chain";
  commodity_framework: boolean;
  saved_strategies_max: number;
  saved_strategies_always_public: boolean;
  community_badge: "verified" | "creator" | null;
}

export interface AnonymousEntitlements {
  runs_remaining: number; // 0 or 1
  asset_classes: ["equities"];
  market_pulse_ticker_scope: "top_250";
  cta: "signup_to_continue" | "signup_to_save";
}

// 402 Upgrade-Required envelope (Stage 1a foundation; Stage 3 adds more codes)
export type EntitlementErrorCode =
  | "saved_strategies_quota_reached"
  | "anonymous_runs_exhausted"
  // Stage 3 codes (declared now for type stability)
  | "runs_exhausted"
  | "universe_too_large"
  | "history_too_long"
  | "robustness_test_locked"
  | "market_pulse_ticker_out_of_scope";

export interface EntitlementErrorDetail {
  code: EntitlementErrorCode;
  current_tier: Tier | null;
  required_tier: "strategist" | "quant" | null;
  current_value: string | null;
  limit_value: string | null;
  upgrade_url: string;
  cta_text: string;
  detail: string;
  is_anonymous: boolean;
  cta_action: "signup" | "trial" | "checkout" | "upgrade";
}

export interface EntitlementErrorResponse {
  error: "upgrade_required";
  entitlement: EntitlementErrorDetail;
}

// Stage 1a — new SavedStrategy table (Path A). Distinct from the legacy
// PRD-02 SavedStrategy below (which is a BacktestRecord with slug != null).
export interface UserSavedStrategy {
  id: string;
  user_id: string;
  title: string;
  strategy_json: unknown;
  is_public: boolean;
  backtest_record_id: string | null;
  created_at: string;
  updated_at: string;
}

// Stage 4a — published strategies (snapshot of a saved strategy, public).
export interface PublishedAuthor {
  id: string;
  handle: string | null;
  display_name: string | null;
  badge: "verified" | "creator" | null;
}

export interface PublishedStrategySummary {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  strategy_type: string;
  universe: string[];
  benchmark: string;
  metrics: {
    total_return?: number | null;
    annualized_return?: number | null;
    sharpe_ratio?: number | null;
    max_drawdown?: number | null;
    win_rate?: number | null;
    number_of_trades?: number | null;
    buy_and_hold_return?: number | null;
  };
  follow_count: number;
  like_count: number;
  comment_count: number;
  view_count: number;
  created_at: string;
  author: PublishedAuthor;
}

export interface PublishedStrategyDetail extends PublishedStrategySummary {
  strategy_json: Record<string, unknown>;
  equity_curve: Array<{ date: string | null; equity: number | null; benchmark: number | null }>;
}

export interface PublishedStrategyFeed {
  items: PublishedStrategySummary[];
  page: number;
  page_size: number;
}

// ── Billing (Stage 2) ─────────────────────────────────────────────────────────

export interface PricingTierOption {
  tier: "strategist" | "quant";
  billing_cycle: "monthly" | "annual";
  price_id: string;
  amount_cents: number;
  display_price: string;
}

export interface PricingPage {
  options: PricingTierOption[];
  trial_days: number;
}

// ── Strategy types ────────────────────────────────────────────────────────────

export type StrategyType =
  | "moving_average_filter"
  | "moving_average_crossover"
  | "momentum_rotation"
  | "rsi_mean_reversion"
  | "breakout"
  | "static_allocation"
  | "cross_sectional_momentum"
  | "time_series_momentum"
  | "short_term_reversal"
  | "pairs_trading"
  | "sector_rotation"
  | "dual_momentum"
  | "low_volatility"
  | "bollinger_mean_reversion"
  | "value_composite"
  | "quality_piotroski"
  | "buyback_yield"
  | "pead_drift"
  | "earnings_revision"
  | "news_sentiment_momentum"
  | "insider_buying"
  | "multi_factor_composite"
  // PRD-13b — Portfolio Mode overlays
  | "portfolio_defensive_overlay"
  | "portfolio_rotation_overlay"
  | "portfolio_rebalance_overlay";

export type RebalanceFrequency = "daily" | "weekly" | "monthly" | "quarterly";

export type TemplateAvailability = "ready" | "unavailable" | "proxy";

export interface SavedStrategy {
  slug: string;
  name: string;
  saved_at: string;
  is_public: boolean;
  strategy_json: StrategyJson;
  metrics: BacktestMetrics;
  equity_curve: CurvePoint[];
  benchmark_curve: CurvePoint[];
  drawdown_curve: CurvePoint[];
  trade_log: TradeLogItem[];
  warnings: string[];
}

export interface ResearchTemplate {
  id: string;
  name: string;
  category:
    | "Momentum" | "Rotation" | "Factor" | "Carry"
    | "Sentiment" | "Alternative"
    | "Reversal" | "Arbitrage";
  description: string;
  /** Two-sentence thesis — what the strategy captures and why it works. */
  whatItCaptures?: string;
  whatItTests: string;
  dataRequirement: string;
  universeDescription: string;
  defaultTickers: string[];
  multiTicker: boolean;
  tickerLabel: string;
  minTickers?: number;
  availability: TemplateAvailability;
  dataGapReason?: string;
  etfProxyCaveat?: string;
  strategy: StrategyJson;
  chatSeed: string;
  /** Evidence quality tier: A=strong academic, B=mixed, C=practitioner-only. */
  evidenceTier?: string;
  /** Intended user capacity (e.g. "Retail", "Prosumer", "Institutional"). */
  capacityBadge?: string;
  /** Typical holding horizon: "Intraday" | "Swing" | "Position" | "Multi-quarter". */
  horizonBadge?: string;
  /** Risk / regime / capacity caveats surfaced from the strategy library. */
  caveats?: string[];
  /** True = Phase B/C template shown with "Coming soon" overlay. */
  comingSoon?: boolean;
  /** Academic or practitioner citation + one-line credibility note. */
  academicRef?: { citation: string; note: string };
  /** Indicative historical performance context shown in the Strategy Brief card. */
  perfContext?: { returnRange: string; sharpeRange: string; worstStretch: string };
  /** Plain-English entry signal — shown in the WHEN IN section of the
   *  4-block summary step (PR-C, 2026-05-24). E.g.
   *  "Hold when price is above the 200-day moving average".
   *  Optional; falls back to a derived description when absent. */
  whenInCopy?: string;
  /** Plain-English exit signal — shown in the WHEN OUT section of the
   *  4-block summary step (PR-C, 2026-05-24). E.g.
   *  "Sell when price drops back below the 200-day moving average".
   *  Optional; falls back to a derived description when absent. */
  whenOutCopy?: string;
}

export interface StrategyRule {
  indicator?: string;
  lookback_days?: number;
  threshold?: number;
  operator?: "gt" | "gte" | "lt" | "lte" | "crosses_above" | "crosses_below";
  source?: "close" | "adjusted_close" | "return" | "moving_average" | "rsi" | "high";
  value?: number | string;
  fast_window?: number;
  slow_window?: number;
  entry_window?: number;
  exit_window?: number;
  top_n?: number;
  top_pct?: number;
  ranking_measure?: "total_return";
  ranking_lookback_days?: number;
  signal_source?:
    | "price"
    | "return"
    | "vol"
    | "sentiment_score"
    | "f_score"
    | "buyback_yield"
    | "value_composite"
    | "quality_composite"
    | "earnings_surprise"
    | "estimate_revision"
    | "insider_net_buy"
    | "safe_asset";
  rank_direction?: "top" | "bottom";
  zscore_entry?: number;
  zscore_exit?: number;
  zscore_stop?: number;
  pair_symbol?: string;
  hedge_ratio?: number;
  target_vol_annual?: number;
  formation_period_days?: number;
  skip_period_days?: number;
  num_std?: number;
  holding_window_days?: number;
  factor_weights?: Record<string, number>;  // multi_factor_composite: factor → weight
}

export interface PositionSizing {
  method: "equal_weight" | "fixed_weight" | "vol_target" | "signal_weighted";
  max_positions?: number;
  weights?: Record<string, number>;
  target_vol_annual?: number;
  signal_power?: number;
}

export interface RiskManagement {
  max_drawdown_stop?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
}

export interface CashManagement {
  hold_cash_when_no_signal: boolean;
  cash_yield_bps?: number;
}

export interface StrategyJson {
  strategy_name: string;
  strategy_type: StrategyType;
  universe: string[];
  benchmark: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  rebalance_frequency: RebalanceFrequency;
  transaction_cost_bps: number;
  slippage_bps: number;
  rules: StrategyRule[];
  position_sizing: PositionSizing;
  risk_management: RiskManagement;
  cash_management: CashManagement;
  /** PRD-13b — Portfolio Mode. When set, the backend uses this list as
   *  the effective universe and ignores `universe`. Required when
   *  `strategy_type` starts with `portfolio_`. */
  inherited_universe?: string[];
}

// ── PRD-13b: Portfolio Mode contracts ────────────────────────────────────────

export interface Holding {
  ticker: string;
  /** Target weight 0..1. Wins over `shares` if both are present. */
  weight?: number;
  /** Number of shares. Used only if `weight` is undefined. */
  shares?: number;
  /** Display-only. Does not affect backtest. */
  cost_basis_per_share?: number;
}

export type StyleBucket =
  | "growth"
  | "value"
  | "defensive"
  | "commodity"
  | "macro_sensitive";

export type BehaviorBucket = "trending" | "mean_reverting" | "mixed";

export type OverlayKind = "defensive" | "rotation" | "rebalance" | "dual_momentum" | "defense_first" | "stability_tilt";

export interface StyleMix {
  growth: number;
  value: number;
  defensive: number;
  commodity: number;
  macro_sensitive: number;
  unclassified_weight: number;
}

export interface FactorExposure {
  size?: number | null;
  value?: number | null;
  momentum?: number | null;
  quality?: number | null;
  low_vol?: number | null;
  beta_to_spy?: number | null;
}

export interface BehaviorAggregate {
  trending_pct: number;
  mean_reverting_pct: number;
  mixed_pct: number;
}

export interface SectorBreakdown {
  sectors: Record<string, number>;
  unknown_sector_weight: number;
}

export interface OverlayRecommendation {
  overlay: OverlayKind;
  rank: number;
  reason: string;
}

export interface PortfolioDiagnosis {
  n_holdings: number;
  style_mix: StyleMix;
  factor_exposure: FactorExposure;
  behavior: BehaviorAggregate;
  sectors: SectorBreakdown;
  realized_vol_1y?: number | null;
  max_drawdown_5y?: number | null;
  caveats: string[];
}

export interface DiagnoseResponse {
  diagnosis: PortfolioDiagnosis;
  recommended_overlays: OverlayRecommendation[];
  cache_hit: boolean;
}

export type ClarificationState = "ready" | "needs_parameters" | "not_supported";

export interface StrategyChatResponse {
  assistant_message: string;
  strategy_json: StrategyJson | null;
  validation_status: "valid" | "needs_clarification" | "invalid";
  missing_fields: string[];
  clarification_questions: string[];
  clarification_state: ClarificationState;
  approximation_note?: string | null;
  unsupported_reason?: string | null;
  suggested_reformulation?: string | null;
}

export interface StrategyExtractedField {
  field: string;
  value: string;
  status: "explicit" | "inferred" | "missing";
}

export interface StrategyMarkdownParseResponse {
  assistant_message: string;
  strategy_json: StrategyJson | null;
  validation_status: "valid" | "needs_clarification" | "invalid";
  extracted_fields: StrategyExtractedField[];
  ambiguities: string[];
  assumption_log: string[];
  missing_fields: string[];
  clarification_questions: string[];
  source_summary: string;
}

export interface CurvePoint {
  date: string;
  value: number;
}

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  calmar_ratio: number;
  win_rate: number;
  number_of_trades: number;
  average_trade_return: number;
  best_trade: number;
  worst_trade: number;
  average_holding_period: number;
  benchmark_total_return: number;
  excess_return_vs_benchmark: number;
  alpha_vs_benchmark: number;
  beta_vs_benchmark: number;
  turnover: number;
  time_in_market: number;
  // Extended trade diagnostics
  profit_factor?: number | null;
  avg_winner?: number | null;
  avg_loser?: number | null;
  median_trade_return?: number | null;
  longest_winning_streak?: number | null;
  longest_losing_streak?: number | null;
  // Buy-and-hold comparison
  buy_and_hold_return?: number | null;
  buy_and_hold_annualized_return?: number | null;
}

export interface TradeLogItem {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  return_pct: number;
  holding_period_days: number;
}

export interface BacktestResult {
  backtest_id: string;
  strategy_json: StrategyJson;
  metrics: BacktestMetrics;
  equity_curve: CurvePoint[];
  benchmark_curve: CurvePoint[];
  buy_and_hold_curve: CurvePoint[];
  drawdown_curve: CurvePoint[];
  trade_log: TradeLogItem[];
  annual_returns: { year: number; return_pct: number }[];
  monthly_returns: { year: number; month: number; return_pct: number }[];
  warnings: string[];
  created_at?: string | null;
}

export interface ExplanationResponse {
  strategy_summary: string;
  performance_explanation: string;
  strengths: string[];
  weaknesses: string[];
  market_regime_notes: string[];
  suggested_iterations: string[];
  disclaimer: string;
}

export interface SandboxReviewResponse {
  review_verdict: "promising" | "mixed" | "skeptical" | "untrusted";
  trust_score: number;
  confidence_level: "low" | "medium" | "high";
  overfitting_risk: "low" | "medium" | "high";
  overfitting_risk_explanation: string;
  benchmark_concerns: string[];
  regime_dependence_concerns: string[];
  parameter_sensitivity_concerns: string[];
  transaction_cost_concerns: string[];
  sample_size_concerns: string[];
  data_quality_concerns: string[];
  main_reasons_to_trust: string[];
  main_reasons_to_distrust: string[];
  required_next_tests: string[];
  suggested_next_experiments: string[];
  final_warning: string;
}

export interface DataQualityReport {
  symbol: string;
  status: "ready" | "warning" | "blocked";
  warnings: string[];
  blocking_errors: string[];
  earliest_available_date?: string | null;
  latest_available_date?: string | null;
  row_count: number;
  missing_date_count?: number | null;
  adjusted_close_coverage: number;
  volume_coverage: number;
}

export interface SymbolSearchItem {
  symbol: string;
  name: string;
  region?: string | null;
  currency?: string | null;
  instrument_type?: string | null;
  exchange?: string | null;
  timezone?: string | null;
  alpha_vantage_match_score?: number | null;
}

export interface SymbolDetailResponse extends SymbolSearchItem {
  is_active: boolean;
  last_seen_at?: string | null;
  last_validated_at?: string | null;
}

export interface DataStatusResponse {
  symbol: string;
  bar_count: number;
  earliest_date?: string | null;
  latest_date?: string | null;
  is_stale: boolean;
  last_fetch_status?: "success" | "error" | "rate_limited" | null;
  last_fetched_at?: string | null;
}

export interface PriceBarResponse {
  symbol: string;
  trading_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  volume: number;
  dividend_amount: number;
  split_coefficient: number;
}

export interface MarketSnapshotItem {
  symbol: string;
  name: string;
  last_price: number;
  prev_close: number;
  change_pct: number;
  change_abs: number;
  last_date: string;
  sparkline: number[];
}

export interface WarmupRequest {
  symbols: string[];
  lookback_days?: number;
}

export interface WarmupResponse {
  queued: string[];
  already_fresh: string[];
  errors: Record<string, string>;
}

// ── Robustness ────────────────────────────────────────────────────────────────

export interface ParameterSensitivityRow {
  parameter_set: Record<string, number | string>;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  trade_count: number;
  verdict: "better" | "similar" | "worse";
}

export interface SubperiodRow {
  period: string;
  start_date: string;
  end_date: string;
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  verdict: "strong" | "acceptable" | "weak" | "insufficient_data";
}

export interface TransactionCostRow {
  cost_bps: number;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  turnover_impact: number;
  verdict: "robust" | "sensitive" | "breaks_down";
}

export interface BenchmarkComparisonRow {
  name: string;
  symbol: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  excess_return_vs_strategy: number;
}

export interface PeerTickerRow {
  ticker: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  trade_count: number;
  verdict: "better" | "similar" | "worse" | "error";
  error?: string | null;
}

export interface RobustnessResults {
  parameter_sensitivity: ParameterSensitivityRow[];
  subperiod: SubperiodRow[];
  transaction_cost: TransactionCostRow[];
  benchmark_comparison: BenchmarkComparisonRow[];
  peer_ticker: PeerTickerRow[];
  summary: string;
  warnings: string[];
}

export interface RobustnessJobResponse {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  results?: RobustnessResults | null;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
}

// ── Demo strategies ───────────────────────────────────────────────────────────

export interface DemoStrategy {
  label: string;
  labelZh: string;
  prompt: string;
  strategy: StrategyJson;
}

const today = new Date().toISOString().slice(0, 10);
const oneYearAgo = new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
const threeYearsAgo = new Date(Date.now() - 3 * 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
const fiveYearsAgo = new Date(Date.now() - 5 * 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

export const commodityDemoStrategies: DemoStrategy[] = [
  {
    label: "Gold Trend Following",
    labelZh: "黄金趋势跟踪",
    prompt: "Buy GLD when price is above its 200-day moving average, sell when below. Benchmark against DBC.",
    strategy: {
      strategy_name: "GLD 200-Day MA Trend Filter",
      strategy_type: "moving_average_filter",
      universe: ["GLD"],
      benchmark: "DBC",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "daily",
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ indicator: "moving_average", lookback_days: 200, operator: "gt", source: "adjusted_close" }],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
  },
  {
    label: "Commodity Momentum Rotation",
    labelZh: "大宗商品动量轮动",
    prompt: "Every month, rotate into the top 2 commodities by 3-month return from GLD, SLV, USO, UNG, DBA.",
    strategy: {
      strategy_name: "Commodity Momentum Rotation",
      strategy_type: "momentum_rotation",
      universe: ["GLD", "SLV", "USO", "UNG", "DBA"],
      benchmark: "DBC",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ top_n: 2, ranking_measure: "total_return", ranking_lookback_days: 63 }],
      position_sizing: { method: "equal_weight", max_positions: 2 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false },
    },
  },
  {
    label: "Diversified Commodity Allocation",
    labelZh: "多元化大宗商品配置",
    prompt: "Static allocation: 40% gold, 30% oil, 20% agriculture, 10% silver. Rebalance monthly.",
    strategy: {
      strategy_name: "Diversified Commodity Allocation",
      strategy_type: "static_allocation",
      universe: ["GLD", "USO", "DBA", "SLV"],
      benchmark: "DBC",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [],
      position_sizing: { method: "fixed_weight", weights: { GLD: 0.4, USO: 0.3, DBA: 0.2, SLV: 0.1 } },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false },
    },
  },
];

export const demoStrategies: DemoStrategy[] = [
  {
    label: "NVDA Trend Following",
    labelZh: "英伟达趋势跟踪",
    prompt: "Buy NVDA when price is above its 100-day moving average, sell when below. Compare against NVDA buy-and-hold and SPY.",
    strategy: {
      strategy_name: "NVDA 100-Day MA Filter",
      strategy_type: "moving_average_filter",
      universe: ["NVDA"],
      benchmark: "SPY",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "daily",
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ indicator: "moving_average", lookback_days: 100, operator: "gt", source: "adjusted_close" }],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
  },
  {
    label: "QQQ RSI Mean-Reversion",
    labelZh: "纳指RSI均值回归",
    prompt: "Buy QQQ when RSI drops below 30, sell when RSI rises above 60. Compare against QQQ buy-and-hold.",
    strategy: {
      strategy_name: "QQQ RSI Mean-Reversion",
      strategy_type: "rsi_mean_reversion",
      universe: ["QQQ"],
      benchmark: "QQQ",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "daily",
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [
        { indicator: "rsi", lookback_days: 14, operator: "lt", threshold: 30 },
        { indicator: "rsi", lookback_days: 14, operator: "gt", threshold: 60 },
      ],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
  },
  {
    label: "Mega-Cap Momentum Rotation",
    labelZh: "大盘动量轮动",
    prompt: "Every month, rotate into the top 3 mega-cap stocks by 6-month momentum from AAPL, MSFT, NVDA, AMZN, GOOGL, META.",
    strategy: {
      strategy_name: "Mega-Cap Momentum Rotation",
      strategy_type: "momentum_rotation",
      universe: ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"],
      benchmark: "QQQ",
      start_date: threeYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ top_n: 3, ranking_measure: "total_return", ranking_lookback_days: 126 }],
      position_sizing: { method: "equal_weight", max_positions: 3 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false },
    },
  },
];

export const demoPrompts = [
  "Buy AAPL when price is above its 200-day moving average. Sell when below.",
  "Buy NVDA when 50-day moving average is above 200-day moving average. Sell when below.",
  "Every month, buy the top 3 stocks from AAPL, MSFT, NVDA, AMZN, GOOGL based on 6-month return.",
  "Buy TSLA when RSI is below 30. Sell when RSI is above 60.",
];

export const demoMarkdownStrategy = `# Momentum Rotation Research Memo

## Objective
Test a simple monthly rotation model for large-cap technology leaders.

## Universe
AAPL, MSFT, NVDA, AMZN, GOOGL

## Portfolio Construction
- Rebalance monthly
- Hold the top 3 names by trailing 6-month return
- Equal weight selected positions

## Benchmark
QQQ

## Risk and Frictions
- Transaction cost: 10 bps
- Slippage: 10 bps

## Backtest Window
- Start Date: 2024-01-01
- End Date: 2025-01-31
`;

export const researchTemplates: ResearchTemplate[] = [
  {
    id: "trend-following",
    name: "Trend Following",
    category: "Momentum",
    description: "Price momentum with a trailing stop",
    whatItTests:
      "Buy when price breaks above a 20-day rolling high. Exit when price falls below a 10-day low, or triggers an 8% stop loss. Tests whether sustained price trends produce better risk-adjusted returns than buy-and-hold.",
    dataRequirement: "Price data only",
    universeDescription: "Any equity or ETF",
    defaultTickers: ["AAPL"],
    multiTicker: false,
    tickerLabel: "Which ticker do you want to test this on?",
    availability: "ready",
    strategy: {
      strategy_name: "Trend Following — 20-Day Breakout",
      strategy_type: "breakout",
      universe: ["AAPL"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 10000,
      rebalance_frequency: "daily",
      transaction_cost_bps: 10,
      slippage_bps: 5,
      rules: [{ entry_window: 20, exit_window: 10 }],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: { stop_loss_pct: 0.08 },
      cash_management: { hold_cash_when_no_signal: true, cash_yield_bps: 0 },
    },
    chatSeed:
      "I want to build a trend following strategy for {ticker}. Tell me your rules — breakout window, exit window, or stop type.",
    academicRef: { citation: "Donchian (1970s) · Covel — Trend Following (2004) · Hurst, Ooi & Pedersen (2017)", note: "Price trend-following is one of the oldest systematic strategies — documented in live CTA fund returns for 50+ years across asset classes." },
    perfContext: { returnRange: "+3% to +12% annual (varies widely by asset and lookback)", sharpeRange: "Sharpe ~0.5 – 1.0", worstStretch: "−20% to −35% in choppy, mean-reverting markets" },
    whenInCopy:
      "Each trading day, watch the trailing 20-day price high. Enter long on the first daily close that prints above that high — a classic Donchian breakout. The 20-day window is the shortest 'trend confirmation' lookback that filters routine intraday noise; the breakout itself is the only entry trigger (no oscillator, no fundamental filter). Position size is full notional on this single-asset template.",
    whenOutCopy:
      "Exit on the first daily close below the trailing 10-day price low (the trend has failed) OR if the position is down 8% from entry (the stop-loss has triggered), whichever happens first. The asymmetric 20-up / 10-down windows deliberately give trends room to develop while cutting losers fast — the original Turtle Trader heuristic. After exit the strategy sits in cash until the next 20-day high prints.",
  },
  {
    id: "cross-sectional-momentum",
    name: "Cross-Sectional Momentum",
    category: "Momentum",
    description: "Rank a universe by return, rotate into top performers",
    whatItTests:
      "Each month, rank all assets in your universe by 6-month trailing return. Hold the top 2 performers and rotate out of the rest. Tests whether relative strength across assets predicts short-term continuation.",
    dataRequirement: "Price data only",
    universeDescription: "Multi-asset universe (min 3 tickers)",
    defaultTickers: ["AAPL", "MSFT", "GOOGL", "NVDA", "META"],
    multiTicker: true,
    minTickers: 3,
    tickerLabel: "Enter your universe (min 3 tickers, comma-separated)",
    availability: "ready",
    strategy: {
      strategy_name: "Cross-Sectional Momentum — Top 2 of 5",
      strategy_type: "momentum_rotation",
      universe: ["AAPL", "MSFT", "GOOGL", "NVDA", "META"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 10000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 5,
      rules: [{ top_n: 2, ranking_measure: "total_return", ranking_lookback_days: 126 }],
      position_sizing: { method: "equal_weight", max_positions: 2 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
    },
    chatSeed:
      "I want to build a cross-sectional momentum strategy. My universe is {tickers}. Tell me: how many top performers to hold, and what lookback period to rank by.",
    academicRef: { citation: "Jegadeesh & Titman (1993, JF) · Carhart (1997) · AQR Capital Research", note: "Cross-sectional momentum is one of the most replicated anomalies in finance — documented across equities, bonds, commodities, and currencies." },
    perfContext: { returnRange: "+4% to +12% annual alpha over benchmark", sharpeRange: "Sharpe ~0.8 – 1.3", worstStretch: "−25% to −40% in momentum crashes (2009, 2020)" },
    whenInCopy:
      "At each month-end, rank every asset in your universe by trailing 126-day (6-month) total return. Buy the top 2 ranked names, equal-weighted. The ranking is purely relative — what matters is each asset's return versus its peers in the universe, not whether the return is positive in absolute terms. You'll always be holding the two strongest performers, regardless of whether the broader market is trending up or down.",
    whenOutCopy:
      "At each monthly rebalance, re-rank the universe and rebuild the portfolio from the new top 2. Names that have dropped out of the top 2 are sold; the new entrants are bought. There are no stops or take-profits — the monthly rebalance IS the entire exit mechanism, so a name can be held one month, sold the next, and bought back two months later if its relative momentum recovers.",
  },
  {
    id: "etf-rotation",
    name: "ETF Rotation",
    category: "Rotation",
    description: "Rotate across asset class ETFs by relative momentum",
    whatItTests:
      "Each month, hold the single ETF with the highest 3-month trailing return across a basket of asset class proxies. Tests whether simple momentum across asset classes adds value over a static allocation.",
    dataRequirement: "Price data only",
    universeDescription: "Asset class ETF basket",
    defaultTickers: ["SPY"],
    multiTicker: false,
    tickerLabel: "Which benchmark do you want to compare against?",
    availability: "ready",
    strategy: {
      strategy_name: "ETF Rotation — Asset Class Momentum",
      strategy_type: "momentum_rotation",
      universe: ["SPY", "QQQ", "IEF", "GLD", "DBC"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 10000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 5,
      rules: [{ top_n: 1, ranking_measure: "total_return", ranking_lookback_days: 63 }],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
    },
    chatSeed:
      "I want to build an ETF rotation strategy. My benchmark is {ticker}. Tell me: which ETFs to rotate across, what lookback period to rank by, and how many to hold at once.",
    academicRef: { citation: "Faber — GTAA (2007) · Antonacci (2012) · Blitz & Van Vliet (2008)", note: "Systematic asset class rotation using momentum has been shown to improve risk-adjusted returns vs. static allocation across multiple market cycles." },
    perfContext: { returnRange: "+2% to +8% annual vs buy-and-hold", sharpeRange: "Sharpe ~0.6 – 1.0", worstStretch: "−20% to −35% in sharp broad-market drawdowns" },
  },
  {
    id: "value-momentum",
    name: "Value + Momentum",
    category: "Factor",
    description: "Combine fundamental value signals with price momentum",
    whatItTests:
      "Buy stocks that are both cheap (low P/E) and showing positive price momentum. Tests whether combining a value filter with a momentum signal improves returns over either factor alone.",
    dataRequirement: "Requires P/E and earnings data",
    universeDescription: "Equity universe",
    defaultTickers: [],
    multiTicker: false,
    tickerLabel: "",
    availability: "unavailable",
    dataGapReason:
      "Requires fundamental data (P/E, earnings) — not yet available in this tool. Shown here so you can plan your research.",
    strategy: {
      strategy_name: "Value + Momentum",
      strategy_type: "momentum_rotation",
      universe: ["AAPL"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 10000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 5,
      rules: [],
      position_sizing: { method: "equal_weight", max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
    },
    chatSeed: "",
  },
  {
    id: "commodity-carry",
    name: "Commodity Carry",
    category: "Carry",
    description: "Roll yield proxy using front-month ETF returns",
    whatItTests:
      "Approximate commodity carry by using short-term ETF returns as a proxy for roll yield. Rotate monthly into the top 2 commodity ETFs by 1-month return. Note: ETF proxy differs from true futures roll yield.",
    dataRequirement: "Futures curve data (ETF proxy available)",
    universeDescription: "Commodity ETFs",
    defaultTickers: ["GLD", "SLV", "USO", "UNG", "DBA"],
    multiTicker: true,
    minTickers: 2,
    tickerLabel: "Enter your commodity universe (comma-separated)",
    availability: "proxy",
    etfProxyCaveat:
      "This template uses an ETF proxy for futures curve data. The approximation may differ materially from actual roll yield. Treat results as directional, not precise.",
    strategy: {
      strategy_name: "Commodity Carry — ETF Proxy",
      strategy_type: "momentum_rotation",
      universe: ["GLD", "SLV", "USO", "UNG", "DBA"],
      benchmark: "DBC",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 10000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 10,
      slippage_bps: 5,
      rules: [{ top_n: 2, ranking_measure: "total_return", ranking_lookback_days: 21 }],
      position_sizing: { method: "equal_weight", max_positions: 2 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false, cash_yield_bps: 0 },
    },
    chatSeed:
      "I want to build a commodity carry strategy using ETF proxies. My universe is {tickers}. Tell me: which commodity ETFs to include and how to rank them.",
    academicRef: { citation: "Gorton & Rouwenhorst (2006, JF) · Erb & Harvey (2006, FAJ)", note: "Commodity carry has been documented in futures roll-yield data since the 1980s. This ETF proxy approximates the concept but deviates from true futures carry." },
    perfContext: { returnRange: "+2% to +8% annual (ETF proxy — true futures carry differs)", sharpeRange: "Sharpe ~0.5 – 1.0", worstStretch: "−25% to −45% in commodity bear markets" },
  },
  {
    id: "news-sentiment-momentum",
    name: "News Sentiment Momentum",
    category: "Sentiment",
    description:
      "Rank stocks by rolling 30-day mean news sentiment score and go long the top decile. Combines NLP-derived sentiment signals with monthly rebalancing.",
    whatItTests:
      "Tests whether stocks with persistently positive news sentiment outperform over a one-month holding window. The 30-day rolling mean smooths day-to-day noise. Note: sentiment-only alpha has mixed empirical support in 2024–2025 literature — consider combining with a fundamental signal.",
    dataRequirement: "News sentiment scores (requires sentiment data pipeline)",
    universeDescription: "Large-cap equities with active news coverage",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 5,
    tickerLabel: "Enter your universe (comma-separated, min 5 symbols)",
    availability: "unavailable",
    dataGapReason:
      "Requires live news sentiment scores from the sentiment data pipeline. Not yet available for backtesting — shown here so you can plan your research.",
    evidenceTier: "B",
    capacityBadge: "Prosumer",
    strategy: {
      strategy_name: "News Sentiment Momentum",
      strategy_type: "news_sentiment_momentum",
      universe: ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"],
      benchmark: "SPY",
      start_date: "2022-01-01",
      end_date: "2024-12-31",
      initial_capital: 100000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 15,
      slippage_bps: 10,
      rules: [{ top_pct: 0.1 }],
      position_sizing: { method: "equal_weight" },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a news sentiment momentum strategy. My universe is {tickers}. Tell me: how to rank by sentiment, what lookback window to use, and how to combine with a second signal.",
    whenInCopy:
      "At each month-end, compute the trailing 30-day mean sentiment score for every stock in your universe (sentiment comes from an NLP model like FinBERT, scored per news article in the window). Buy the top decile by mean sentiment, sized equal-weight. The 30-day window smooths day-to-day noise so the signal reflects persistent positive coverage rather than a single bullish headline.",
    whenOutCopy:
      "At each monthly rebalance, re-compute 30-day mean sentiment across the universe and rebuild from the new top decile. Names whose sentiment has cooled out of the top 10% are sold; the new sentiment leaders are bought. Sentiment-only alpha has mixed empirical support — evidence is stronger when paired with a price-trend co-signal (e.g. require the stock to also trade above its 200-day moving average) layered on top of the sentiment ranking.",
  },
  {
    id: "insider-buying",
    name: "Insider Buying Cluster",
    category: "Alternative",
    description:
      "Rank stocks by rolling 30-day net insider-purchase dollars (cluster buys) and hold the top 20. Insider purchases are weighted by dollar value, not count.",
    whatItTests:
      "Tests whether cluster insider purchasing — multiple insiders buying the same stock in the same rolling window — predicts positive short-term returns. Weekly rebalancing captures new filing disclosures (Form 4, ~2-day lag).",
    dataRequirement: "SEC Form 4 insider transaction data (via FMP or EDGAR)",
    universeDescription: "S&P 500 or Russell 1000 constituents",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 50,
    tickerLabel: "Enter your universe (comma-separated, min 50 symbols for signal diversity)",
    availability: "unavailable",
    dataGapReason:
      "Requires real-time SEC Form 4 insider transaction data. Not yet available for backtesting — shown here so you can plan your research.",
    evidenceTier: "B",
    capacityBadge: "Prosumer",
    strategy: {
      strategy_name: "Insider Buying Cluster",
      strategy_type: "insider_buying",
      universe: ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"],
      benchmark: "SPY",
      start_date: "2022-01-01",
      end_date: "2024-12-31",
      initial_capital: 100000,
      rebalance_frequency: "weekly",
      transaction_cost_bps: 15,
      slippage_bps: 10,
      rules: [{ top_n: 20 }],
      position_sizing: { method: "equal_weight" },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build an insider buying strategy. My universe is {tickers}. Tell me: how to filter for cluster buys, what dollar threshold to use, and how to size positions.",
  },
  {
    id: "multi-factor-composite",
    name: "Multi-Factor Composite",
    category: "Factor",
    description:
      "Combine Value, Momentum, Quality, and Low-Volatility into a single equal-weighted composite score. Rank the top decile monthly. Each factor is cross-sectionally z-scored before blending.",
    whatItTests:
      "Tests whether a diversified factor composite (value 25%, momentum 25%, quality 25%, low-vol 25%) outperforms single-factor strategies over a full market cycle. Factor weights are customisable — e.g. tilt toward value in bear markets and momentum in bull runs.",
    dataRequirement: "Price data + fundamental data (FCF, book value, EBITDA, F-Score)",
    universeDescription: "Large- and mid-cap equities (min 20 symbols recommended)",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 10,
    tickerLabel: "Enter your universe (comma-separated, min 10 symbols for factor diversity)",
    availability: "unavailable",
    dataGapReason:
      "Requires fundamental signal data (FCF yield, book-to-market, Piotroski F-Score). Not yet available for backtesting — shown here so you can plan your research.",
    evidenceTier: "A",
    capacityBadge: "Pro",
    strategy: {
      strategy_name: "Multi-Factor Composite — Equal-Weighted",
      strategy_type: "multi_factor_composite",
      universe: ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "JPM", "JNJ", "XOM"],
      benchmark: "SPY",
      start_date: "2020-01-01",
      end_date: "2024-12-31",
      initial_capital: 100000,
      rebalance_frequency: "monthly",
      transaction_cost_bps: 15,
      slippage_bps: 10,
      rules: [{
        factor_weights: {
          value_composite: 0.25,
          momentum_12_1: 0.25,
          quality_f_score: 0.25,
          low_volatility: 0.25,
        },
        top_pct: 0.1,
      }],
      position_sizing: { method: "equal_weight" },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a multi-factor composite strategy. My universe is {tickers}. Tell me: how to weight each factor, whether to tilt toward value or momentum, and how to handle factor timing.",
    whenInCopy:
      "At each month-end, compute four factor scores per stock: Value (composite of FCF yield + book-to-market + EV/EBITDA), Momentum (12-1 trailing return), Quality (Piotroski F-Score), and Low Volatility (inverse of 63-day realised vol). Cross-sectionally z-score each factor, average the four equally (25% weight each by default), then buy the top decile by composite score. Factor weights are user-tunable for value or momentum tilts.",
    whenOutCopy:
      "At each monthly rebalance, re-score the universe and rebuild the portfolio from the new top-decile composite. Stocks whose composite ranking has fallen out of the top 10% are sold; new top-decile entrants are bought, equal-weighted. The four-factor diversification means the portfolio rarely turns over completely — typically 30–50% of holdings change per rebalance, which is much more manageable than single-factor strategies that can turn over 100%+ per quarter.",
  },
  // ── Phase A: 8 new engine-backed templates ────────────────────────────────

  {
    id: "cross-sectional-momentum-12-1",
    name: "Cross-Sectional Momentum (12-1)",
    category: "Momentum" as const,
    description:
      "Each month, rank your universe by trailing 12-month return (skipping the most recent month) and hold the top quintile. The 12-1 specification is the most-replicated momentum variant across asset classes.",
    whatItCaptures:
      "Assets that have outperformed their peers over the past year tend to continue outperforming over the next 1–3 months. The 1-month skip prevents short-term reversal from contaminating the signal.",
    whatItTests:
      "Whether trailing 12-month relative return predicts near-term outperformance within the cross-section, net of a 1-month skip period.",
    dataRequirement: "Price data — at least 14 months of history per symbol",
    universeDescription: "Large- and mid-cap equities — min 10 symbols for meaningful cross-section",
    defaultTickers: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
    multiTicker: true,
    minTickers: 10,
    tickerLabel: "Enter your universe (comma-separated, min 10 symbols)",
    availability: "ready" as const,
    evidenceTier: "A",
    capacityBadge: "Institutional",
    horizonBadge: "Position",
    caveats: [
      "Momentum crashes: large drawdowns during sharp market reversals (e.g. March 2009, COVID recovery 2020).",
      "Requires a broad universe — fewer than 10 symbols reduces the cross-sectional signal-to-noise ratio significantly.",
      "High turnover (~100% annually) makes transaction costs critical; run the backtest with realistic 10+ bps assumptions.",
      "Regime sensitivity: underperforms in low-dispersion environments where stocks move in lockstep.",
    ],
    strategy: {
      strategy_name: "Cross-Sectional Momentum (12-1)",
      strategy_type: "cross_sectional_momentum",
      universe: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly" as const,
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ formation_period_days: 252, skip_period_days: 21, top_pct: 0.2 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a 12-1 cross-sectional momentum strategy. My universe is {tickers}. Tell me: what lookback, whether to skip the most recent month, and how many names to hold.",
    academicRef: { citation: "Jegadeesh & Titman (1993, JF) · Fama & French (2012) · AQR Capital (live since 1994)", note: "The 12-1 specification is the single most-replicated momentum variant — documented in 40+ markets and 200+ years of return data." },
    perfContext: { returnRange: "+4% to +16% annual alpha over benchmark", sharpeRange: "Sharpe ~1.0 – 1.5", worstStretch: "−30% to −50% in momentum crashes (March 2009, COVID recovery 2020)" },
    whenInCopy:
      "At each month-end, for every stock in your universe, compute the trailing 12-month return from t-252 days to t-21 days — explicitly skipping the most recent month. Rank the universe by that 12-1 return and buy the top quintile (20%), equal-weighted. The 1-month skip is the load-bearing detail: without it, short-term reversal contaminates the signal and the strategy loses most of its documented alpha (Jegadeesh & Titman 1993; replicated across 40+ markets).",
    whenOutCopy:
      "At each monthly rebalance, re-rank the entire universe on the same 12-1 window and rebuild the portfolio from the new top quintile. Names that have fallen out of the top 20% are sold; new top-quintile entrants are bought. There are no stops or take-profits — the rebalance IS the exit. Turnover is roughly 100% per year, which is why transaction costs (10+ bps assumed) materially affect the realised vs. paper return.",
  },
  {
    id: "time-series-momentum",
    name: "Time-Series Momentum / Trend",
    category: "Momentum" as const,
    description:
      "Hold each asset only when its own 12-month absolute return is positive; equal-weight all qualifying assets. Moves to cash when most assets are in downtrends — providing a built-in bear market hedge.",
    whatItCaptures:
      "Each asset's own trend — whether it is moving up or down on its own merits — predicts near-term returns. Unlike cross-sectional momentum, this strategy can hold 0% during broad bear markets.",
    whatItTests:
      "Whether positive absolute 12-month momentum for individual assets predicts positive near-term returns, with cash as the alternative when the signal is off.",
    dataRequirement: "Price data — at least 14 months of history per symbol",
    universeDescription: "Multi-asset or equity universe — best across uncorrelated assets",
    defaultTickers: ["SPY","QQQ","IWM","EFA","EEM","TLT","GLD","DBC","VNQ","HYG"],
    multiTicker: true,
    minTickers: 3,
    tickerLabel: "Enter your universe (comma-separated)",
    availability: "ready" as const,
    evidenceTier: "A",
    capacityBadge: "Prosumer",
    horizonBadge: "Position",
    caveats: [
      "Whipsaw risk in choppy, mean-reverting markets where trend signals repeatedly reverse in quick succession.",
      "Works best with a diversified multi-asset universe; single-sector equity universes show weaker out-of-sample results.",
      "The 12-month lookback is slow to adapt — consider also testing 6M and 3M variants to understand parameter sensitivity.",
    ],
    strategy: {
      strategy_name: "Time-Series Momentum",
      strategy_type: "time_series_momentum",
      universe: ["SPY","QQQ","IWM","EFA","EEM","TLT","GLD","DBC","VNQ","HYG"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly" as const,
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ lookback_days: 252 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a time-series momentum strategy. My universe is {tickers}. Tell me: what lookback is optimal, and whether to scale position sizes by signal strength.",
    academicRef: { citation: "Moskowitz, Ooi & Pedersen (2012, JFE) · AQR White Paper — TSMOM", note: "Time-series momentum has been documented across 58 liquid futures markets over 25 years — and provides a natural bear-market hedge by moving to cash during downtrends." },
    perfContext: { returnRange: "+3% to +10% annual alpha, with lower drawdowns than equity buy-and-hold", sharpeRange: "Sharpe ~0.7 – 1.3", worstStretch: "−15% to −25% in rapid trend-reversal environments" },
    whenInCopy:
      "At each month-end, for every asset in your universe, compute the trailing 252-day (12-month) total return. Buy any asset whose 12-month return is positive, sized equal-weight across all qualifying names. The 'absolute' part is critical — there's no peer comparison, no ranking. Each asset stands on its own trend, so during broad bear markets when no asset has positive 12M momentum, the portfolio is held entirely in cash (Moskowitz, Ooi & Pedersen 2012).",
    whenOutCopy:
      "At the next monthly rebalance, re-check the 252-day return for every held position. Any asset whose 12-month return has turned negative is sold and the capital moves to cash — no replacement asset is bought from outside the eligibility list. This is how the strategy provides its built-in bear-market hedge: when most assets are in downtrends the portfolio sits mostly or fully in cash, rather than chasing a 'least-bad' alternative.",
  },
  {
    id: "short-term-reversal",
    name: "Short-Term Reversal",
    category: "Reversal" as const,
    description:
      "Every week, rank your universe by 1-week return and buy the biggest losers. Short-term price pressure from liquidity-demanding sellers creates transient mispricings that revert as market makers are compensated.",
    whatItCaptures:
      "Liquidity providers absorbing temporary selling pressure earn a short-horizon premium. The strategy attempts to replicate this by systematically buying the recent losers who are most likely to bounce.",
    whatItTests:
      "Whether the bottom quintile of 5-day return within a cross-section outperforms over the subsequent week, after realistic transaction costs.",
    dataRequirement: "Price data only",
    universeDescription: "Liquid large-cap equities — min 20 symbols; requires tight spreads",
    defaultTickers: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
    multiTicker: true,
    minTickers: 10,
    tickerLabel: "Enter your universe (comma-separated, min 10 symbols)",
    availability: "ready" as const,
    evidenceTier: "B",
    capacityBadge: "Institutional",
    horizonBadge: "Swing",
    caveats: [
      "Transaction costs are critical — with 10+ bps round-trip much of the alpha is consumed. Originally profitable mainly for institutional desks with near-zero execution costs.",
      "Very high turnover (~5,000% annually with weekly rebalance) — the backtest result is extremely sensitive to cost assumptions.",
      "Not suitable for retail investors without near-zero commissions and tight spreads on all universe members.",
    ],
    strategy: {
      strategy_name: "Short-Term Reversal",
      strategy_type: "short_term_reversal",
      universe: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "weekly" as const,
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ formation_period_days: 5, rank_direction: "bottom" as const, top_pct: 0.2 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a short-term reversal strategy. My universe is {tickers}. Tell me: what reversal lookback and how to handle the transaction cost drag.",
    academicRef: { citation: "Jegadeesh (1990, JF) · Lehmann (1990, JF) · Lo & MacKinlay (1990)", note: "Short-term reversal is well-documented in academic literature but profitable mainly at institutional scale — retail transaction costs typically erode most of the alpha." },
    perfContext: { returnRange: "+2% to +8% gross (near-zero after typical retail costs)", sharpeRange: "Sharpe ~0.5 – 1.0 before costs", worstStretch: "−10% to −20%; cost drag creates persistent headwind" },
    whenInCopy:
      "At each weekly rebalance, rank every asset in your universe by its trailing 5-day (1-week) total return and buy the bottom 20% — the worst recent performers. The thesis (Lehmann 1990; refreshed in 2025 research on MAX-effect stocks) is that short-horizon selling pressure from liquidity-demanding sellers creates transient mispricings, and the strategy effectively gets paid to provide the liquidity those sellers needed. The bottom-quintile cut is the standard academic specification.",
    whenOutCopy:
      "At the next weekly rebalance, re-rank the universe and rebuild the portfolio from the new bottom-quintile losers. Last week's losers are sold (whether they bounced or not) and this week's losers are bought. Turnover runs ~5,000% annually — which is why transaction costs are decisive: at retail commission rates and spreads, much of the documented gross alpha is consumed before it ever reaches the portfolio, and the strategy is mainly viable for institutional desks.",
  },
  {
    id: "pairs-trading-long-only",
    name: "Pairs Trading (Long-Only)",
    category: "Arbitrage" as const,
    description:
      "Track the log-price spread between two correlated assets. Go long the cheaper asset when the z-score is 2+ standard deviations below its mean, exit when the spread normalises.",
    whatItCaptures:
      "Temporary deviations in the relative valuation of two economically linked assets tend to revert. The long-only variant captures the cheaper leg of classic statistical arbitrage.",
    whatItTests:
      "Whether deviations of 2+ standard deviations in the log-spread between two historically correlated assets revert to mean within a 60-day window.",
    dataRequirement: "Price data — two correlated assets",
    universeDescription: "Two positively correlated assets (e.g. AAPL/MSFT, SPY/QQQ)",
    defaultTickers: ["AAPL","MSFT"],
    multiTicker: true,
    minTickers: 2,
    tickerLabel: "Enter exactly 2 correlated assets",
    availability: "ready" as const,
    evidenceTier: "B",
    capacityBadge: "Prosumer",
    horizonBadge: "Swing",
    caveats: [
      "Long-only variant captures only half the spread trade — full statistical arbitrage requires short-selling capability.",
      "Cointegration can break down permanently (e.g. Nokia/Ericsson). Always verify the pair has a genuine economic link.",
      "Stop-loss at z = –3 is essential to prevent losses when the spread diverges instead of reverting.",
    ],
    strategy: {
      strategy_name: "Pairs Trading (Long-Only) — AAPL / MSFT",
      strategy_type: "pairs_trading",
      universe: ["AAPL","MSFT"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "daily" as const,
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ lookback_days: 60, zscore_entry: 2.0, zscore_exit: 0.5, zscore_stop: 3.0, hedge_ratio: 1.0 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a long-only pairs trading strategy between {tickers}. Tell me: what z-score to use for entry and exit, and how to set the stop-loss.",
    academicRef: { citation: "Gatev, Goetzmann & Rouwenhorst (2006, RFS) · Vidyamurthy (2004) — Pairs Trading", note: "Pairs trading has been practiced by quantitative desks since the 1980s. Academic evidence is solid for the full long-short variant; long-only captures half the opportunity." },
    perfContext: { returnRange: "+2% to +8% annual (long-only variant)", sharpeRange: "Sharpe ~0.5 – 1.0", worstStretch: "−15% to −25% if spread diverges instead of reverting" },
    whenInCopy:
      "Each day, compute the log-price spread between your two correlated assets and its trailing 60-day z-score (how many standard deviations the spread is from its 60-day rolling mean). Enter long the relatively-cheaper asset when the z-score reaches −2.0 or worse — meaning the cheap leg is at least 2 standard deviations undervalued versus its historical relationship with the other leg. Hedge ratio defaults to 1.0 (equal notional on the long leg).",
    whenOutCopy:
      "Exit when the z-score recovers back to within ±0.5 of the mean — the spread has reverted to fair value. A hard stop-loss fires if the z-score widens to −3.0 (the cheap leg becomes even cheaper instead of reverting), which prevents a permanent regime break — Nokia/Ericsson-style cointegration breakdowns — from sinking the portfolio. This long-only template captures only half of a classic pair trade because it doesn't short the expensive leg.",
  },
  {
    id: "sector-rotation-spdr",
    name: "Sector Rotation (SPDR)",
    category: "Rotation" as const,
    description:
      "Monthly, rank the 11 SPDR sector ETFs by trailing 3–6 month total return and hold the top 3. Rotate out of lagging sectors into the current economic cycle leaders.",
    whatItCaptures:
      "Different economic sectors lead and lag through the business cycle. By rotating into recent leaders, the strategy attempts to ride the dominant economic theme — technology in 2020–21, energy in 2022.",
    whatItTests:
      "Whether trailing 3–6 month relative return among SPDR sector ETFs predicts near-term relative outperformance, net of monthly rebalancing costs.",
    dataRequirement: "Price data — SPDR sector ETF history",
    universeDescription: "11 SPDR sector ETFs",
    defaultTickers: ["XLK","XLF","XLE","XLV","XLI","XLP","XLU","XLY","XLB","XLRE","XLC"],
    multiTicker: true,
    minTickers: 5,
    tickerLabel: "Enter sector ETFs (comma-separated)",
    availability: "ready" as const,
    evidenceTier: "A",
    capacityBadge: "Retail",
    horizonBadge: "Position",
    caveats: [
      "ETF-level rotation misses intra-sector stock selection alpha — you're getting broad sector beta, not individual stock outperformance.",
      "Concentration risk: holding 3 of 11 sectors creates meaningful tracking error versus SPY.",
      "Formation period sensitivity: results vary significantly across 1M/3M/6M lookbacks — treat the lookback as a free parameter that could be overfit.",
    ],
    strategy: {
      strategy_name: "Sector Rotation — SPDR Top 3",
      strategy_type: "sector_rotation",
      universe: ["XLK","XLF","XLE","XLV","XLI","XLP","XLU","XLY","XLB","XLRE","XLC"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly" as const,
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ formation_period_days: 126, top_n: 3 }],
      position_sizing: { method: "equal_weight" as const, max_positions: 3 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: false },
    },
    chatSeed:
      "I want to build a sector rotation strategy using {tickers}. Tell me: what lookback period works best and how many sectors to hold simultaneously.",
    academicRef: { citation: "Moskowitz & Grinblatt (1999, JF) · Faber (2007) · Blitz & Van Vliet (2008)", note: "Sector momentum is well-documented — industry-level price momentum is a significant driver of individual stock momentum returns." },
    perfContext: { returnRange: "+2% to +8% annual alpha vs SPY", sharpeRange: "Sharpe ~0.6 – 1.1", worstStretch: "−25% to −40% in broad market crashes (sector rotation does not hedge market beta)" },
    whenInCopy:
      "At each month-end, rank the 11 SPDR sector ETFs (XLK, XLF, XLE, XLV, XLI, XLP, XLU, XLY, XLB, XLRE, XLC) by their trailing 126-day (6-month) total return. Buy the top 3 by relative strength, equal-weighted. This rotates capital toward whichever sectors are leading the current business cycle — technology in 2020–21, energy in 2022, defensives (staples + healthcare + utilities) during late-cycle slowdowns.",
    whenOutCopy:
      "At each monthly rebalance, re-rank all 11 sectors and rebuild the portfolio from the new top 3. Sectors that have fallen out of the top 3 are sold; the new entrants are bought, equal-weight. The strategy is always fully invested in sector ETFs — there is no cash position even in broad market downturns, which is exactly why sector rotation does not hedge overall market beta and still draws down meaningfully in broad crashes.",
  },
  {
    id: "dual-momentum",
    name: "Dual Momentum",
    category: "Momentum" as const,
    description:
      "Gary Antonacci's Dual Momentum: first check absolute momentum (is SPY above cash?), then relative momentum (does SPY beat bonds?). Holds US equities, international equities, or bonds depending on signals.",
    whatItCaptures:
      "Combining absolute momentum (trend filter) with relative momentum (asset selection) reduces bear market drawdowns while capturing uptrends. The dual filter removes most of the large equity drawdowns historically.",
    whatItTests:
      "Whether a two-signal filter — absolute return above the risk-free rate AND equities above bonds — improves Sharpe ratio versus buy-and-hold (per Antonacci 2014).",
    dataRequirement: "Price data — broad asset class ETFs",
    universeDescription: "Broad equity and bond ETFs",
    defaultTickers: ["SPY","EFA","TLT"],
    multiTicker: true,
    minTickers: 2,
    tickerLabel: "Enter equity + bond ETFs",
    availability: "ready" as const,
    evidenceTier: "A",
    capacityBadge: "Retail",
    horizonBadge: "Multi-quarter",
    caveats: [
      "Very low turnover (~1–2 switches per year) — timing is concentrated and a single bad switch meaningfully impacts annual returns.",
      "Slow to adapt: the 12-month lookback holds losing positions for months before the signal flips.",
      "Post-publication alpha decay: the strategy attracted significant retail AUM after Antonacci's 2014 book, potentially compressing returns.",
    ],
    strategy: {
      strategy_name: "Dual Momentum — Equity / Bond",
      strategy_type: "dual_momentum",
      universe: ["SPY","EFA","TLT"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly" as const,
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ formation_period_days: 252 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a dual momentum strategy across {tickers}. Tell me: how to incorporate an absolute momentum filter against a cash return proxy.",
    academicRef: { citation: "Antonacci — Dual Momentum Investing (2014) · Faber — GTAA (2007)", note: "The dual-filter approach (absolute + relative momentum) has demonstrated significantly lower drawdowns than buy-and-hold with comparable long-run returns across live strategy data." },
    perfContext: { returnRange: "+2% to +7% annual vs buy-and-hold with materially lower drawdowns", sharpeRange: "Sharpe ~0.8 – 1.3", worstStretch: "−10% to −20% (vs −50%+ for buy-and-hold in 2008)" },
    whenInCopy:
      "At each month-end, run two filters in sequence (Antonacci 2014). First (absolute momentum): is the US-equity ETF's trailing 252-day return above the risk-free rate? If no → hold 100% bonds. If yes → apply relative momentum: is the US-equity 12-month return higher than the international-equity 12-month return? Whichever wins is held 100%. The dual filter is what removes the biggest equity bear-market drawdowns.",
    whenOutCopy:
      "At each monthly rebalance, re-run both filters and switch holdings only if the signal changes. The strategy makes typically just 1–2 switches per year, keeping turnover and frictions low. The 'exit' is automatic: when the absolute-momentum filter fails (US-equity 12M return drops below cash), the strategy moves 100% to bonds — providing the built-in bear-market protection that defines the framework and historically clipped drawdowns to ~20% versus 50%+ for buy-and-hold.",
  },
  {
    id: "low-volatility",
    name: "Low Volatility",
    category: "Factor" as const,
    description:
      "Monthly, rank your universe by trailing 63-day realised volatility and hold the lowest-volatility quintile equal-weight. Lower-risk stocks historically deliver superior Sharpe ratios — the 'low vol anomaly'.",
    whatItCaptures:
      "Low-volatility stocks outperform on a risk-adjusted basis because investors systematically overpay for high-volatility lottery-like stocks and underweight boring low-risk names due to leverage constraints and benchmark hugging.",
    whatItTests:
      "Whether the bottom quintile of realised volatility earns superior Sharpe ratios versus an equal-weight index, net of monthly rebalancing costs.",
    dataRequirement: "Price data — at least 4 months of history per symbol for vol estimation",
    universeDescription: "Broad equity universe — min 15 symbols",
    defaultTickers: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
    multiTicker: true,
    minTickers: 10,
    tickerLabel: "Enter your universe (comma-separated, min 10 symbols)",
    availability: "ready" as const,
    evidenceTier: "A",
    capacityBadge: "Institutional",
    horizonBadge: "Multi-quarter",
    caveats: [
      "Crowding risk: large AUM inflows post-2010 compressed returns and created periodic factor unwinds.",
      "Rate sensitivity: low-volatility portfolios are bond-like and underperform during rising-rate regimes.",
      "Sector concentration: typically overweights utilities, consumer staples, and healthcare — check sector exposure.",
    ],
    strategy: {
      strategy_name: "Low Volatility Factor",
      strategy_type: "low_volatility",
      universe: ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","JNJ","XOM","V","UNH","PG","HD","CVX","TSLA"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "monthly" as const,
      transaction_cost_bps: 10,
      slippage_bps: 10,
      rules: [{ lookback_days: 63, top_pct: 0.2 }],
      position_sizing: { method: "equal_weight" as const },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a low volatility strategy. My universe is {tickers}. Tell me: what vol lookback to use and whether to add a minimum-variance optimiser.",
    academicRef: { citation: "Baker, Bradley & Wurgler (2011, FAJ) · Frazzini & Pedersen (2014, JFE) — Betting Against Beta", note: "The low-volatility anomaly is one of the most persistent puzzles in finance — lower-risk stocks earn higher risk-adjusted returns, contradicting CAPM predictions." },
    perfContext: { returnRange: "+2% to +8% annual risk-adjusted alpha", sharpeRange: "Sharpe ~0.8 – 1.5 (superior Sharpe is the core claim)", worstStretch: "−20% to −35% in sharp drawdowns (still lower than equal-weight market)" },
    whenInCopy:
      "At each month-end, compute the trailing 63-day (3-month) realised volatility — the standard deviation of daily returns, annualised — for every asset in your universe. Buy the bottom quintile (lowest 20% by vol), sized equal-weight. The low-vol anomaly (Baker-Bradley-Wurgler 2011; Frazzini-Pedersen 2014) says these 'boring' names earn superior Sharpe ratios because investors systematically overpay for high-volatility lottery-like stocks and underweight stable defensives.",
    whenOutCopy:
      "At each monthly rebalance, re-measure 63-day volatility across the universe and rebuild the portfolio from the new low-vol quintile. Names whose volatility has risen out of the bottom 20% are sold; new low-vol entrants are bought. The strategy is always fully invested — it doesn't hedge market beta, just tilts toward lower-volatility names within whatever the broader market is doing. The portfolio typically overweights utilities, staples, and healthcare, so monitor sector concentration.",
  },
  {
    id: "bollinger-mean-reversion",
    name: "Bollinger Mean Reversion",
    category: "Reversal" as const,
    description:
      "Enter long when price closes below the lower 2-sigma Bollinger Band (20-day MA). Exit when price crosses back above the middle band. A dynamic, volatility-scaled oversold signal.",
    whatItCaptures:
      "Short-term oversold conditions relative to recent price range tend to revert as buying interest returns. Bollinger Bands scale the entry threshold by the asset's own volatility, making the signal adaptive.",
    whatItTests:
      "Whether a close below the lower 2-standard-deviation Bollinger Band predicts positive returns over the subsequent 1–5 days for a single liquid asset.",
    dataRequirement: "Price data only",
    universeDescription: "Single liquid equity or ETF with mean-reverting character",
    defaultTickers: ["AAPL"],
    multiTicker: false,
    tickerLabel: "Which stock or ETF do you want to test?",
    availability: "ready" as const,
    evidenceTier: "C",
    capacityBadge: "Prosumer",
    horizonBadge: "Swing",
    caveats: [
      "Regime-dependent: fails in strong trending markets where price walks along the lower band without reverting.",
      "Evidence tier C: results are highly sensitive to the lookback and standard-deviation parameters — easy to overfit.",
      "Single-asset focus provides no diversification; a bad period for the underlying hits the whole portfolio.",
    ],
    strategy: {
      strategy_name: "Bollinger Mean Reversion — AAPL",
      strategy_type: "bollinger_mean_reversion",
      universe: ["AAPL"],
      benchmark: "SPY",
      start_date: fiveYearsAgo,
      end_date: today,
      initial_capital: 100000,
      rebalance_frequency: "daily" as const,
      transaction_cost_bps: 5,
      slippage_bps: 5,
      rules: [{ lookback_days: 20, num_std: 2.0 }],
      position_sizing: { method: "equal_weight" as const, max_positions: 1 },
      risk_management: {},
      cash_management: { hold_cash_when_no_signal: true },
    },
    chatSeed:
      "I want to build a Bollinger Band mean-reversion strategy on {ticker}. Tell me: what window and standard-deviation threshold to use.",
    academicRef: { citation: "Bollinger — Bollinger on Bollinger Bands (2002) · Connors & Alvarez (2009) — Short-Term Strategies", note: "Bollinger Band mean reversion is a widely used practitioner technique. Academic evidence is mixed — results are highly parameter-sensitive and regime-dependent." },
    perfContext: { returnRange: "+2% to +10% annual (highly sensitive to asset and parameters)", sharpeRange: "Sharpe ~0.5 – 1.2", worstStretch: "−20% to −40% in sustained trending markets where price walks along the band" },
    whenInCopy:
      "Each day, compute the 20-day simple moving average of price plus two-standard-deviation bands around it (Bollinger Bands). Enter long on the first daily close below the lower band — i.e. when price is at least 2 standard deviations below the 20-day mean. The standard-deviation scaling makes the threshold adaptive: it widens automatically in high-volatility regimes and tightens in calm markets, so the 'oversold' signal is always calibrated to the asset's own recent volatility.",
    whenOutCopy:
      "Exit on the first daily close back above the middle band (the 20-day SMA itself). The mean — not the upper band — is the exit, because the trade is targeting reversion to fair value, not a full overshoot to the upside. If the signal never reverts and price simply walks along the lower band (typical in a strong sustained downtrend), the position sits underwater until the close finally crosses back through the mean — which is the regime risk this template carries.",
  },

  // ── Phase B / C — Coming soon ─────────────────────────────────────────────

  {
    id: "value-composite-cs",
    name: "Value Composite",
    category: "Factor" as const,
    description: "Rank stocks by a composite of FCF yield, book-to-market, and EV/EBITDA. Hold the cheapest decile monthly.",
    whatItCaptures: "Stocks trading at low prices relative to fundamentals tend to outperform as the market corrects mispricings over 12–36 month horizons.",
    whatItTests: "Whether a multi-metric value composite outperforms single-metric value screens.",
    dataRequirement: "Fundamental data (FCF, book value, EBITDA) — not yet available",
    universeDescription: "Large- and mid-cap equities",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 20,
    tickerLabel: "",
    availability: "unavailable" as const,
    evidenceTier: "A",
    capacityBadge: "Institutional",
    horizonBadge: "Multi-quarter",
    comingSoon: true,
    caveats: ["Requires fundamental data pipeline."],
    dataGapReason: "Requires FCF yield, book-to-market, and EV/EBITDA data — coming in Phase B.",
    strategy: { strategy_name: "Value Composite", strategy_type: "value_composite", universe: ["AAPL"], benchmark: "SPY", start_date: fiveYearsAgo, end_date: today, initial_capital: 100000, rebalance_frequency: "monthly" as const, transaction_cost_bps: 10, slippage_bps: 10, rules: [{ top_pct: 0.1 }], position_sizing: { method: "equal_weight" as const }, risk_management: {}, cash_management: { hold_cash_when_no_signal: true } },
    chatSeed: "",
    whenInCopy:
      "At each month-end, compute three value metrics for every stock in your universe: Free-Cash-Flow Yield (FCF / EV), Book-to-Market ratio, and Enterprise Value / EBITDA. Cross-sectionally z-score each metric so they're on the same scale, average them with equal weight, then buy the cheapest 10% by composite score. Multi-metric value avoids the single-metric trap — a stock that scores cheap on one measure but expensive on the other two is filtered out.",
    whenOutCopy:
      "At each monthly rebalance, re-score the universe with the latest fundamentals (FCF, book value, EBITDA) and rebuild from the new cheapest decile. Stocks that have re-rated upward and fallen out of the top decile are sold; newly-cheap entrants are bought, equal-weighted. The strategy is designed for 12–36 month payoff horizons — monthly rebalancing keeps the portfolio fresh, but individual positions are typically held for many months while the re-rating thesis plays out.",
  },
  {
    id: "quality-piotroski-cs",
    name: "Quality — Piotroski F-Score",
    category: "Factor" as const,
    description: "Long stocks with an F-Score of 8 or 9 — companies with strengthening profitability, leverage, and efficiency.",
    whatItCaptures: "Piotroski's 9 binary signals identify companies with improving fundamentals that the market is slow to reprice upward.",
    whatItTests: "Whether high-F-Score stocks generate excess returns versus the broader market.",
    dataRequirement: "Annual financial statements — not yet available",
    universeDescription: "Broad equity universe",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 20,
    tickerLabel: "",
    availability: "unavailable" as const,
    evidenceTier: "A",
    capacityBadge: "Prosumer",
    horizonBadge: "Multi-quarter",
    comingSoon: true,
    caveats: ["Requires annual financial statement data."],
    dataGapReason: "Requires annual financial statement data — coming in Phase B.",
    strategy: { strategy_name: "Quality Piotroski F-Score", strategy_type: "quality_piotroski", universe: ["AAPL"], benchmark: "SPY", start_date: fiveYearsAgo, end_date: today, initial_capital: 100000, rebalance_frequency: "monthly" as const, transaction_cost_bps: 10, slippage_bps: 10, rules: [{ top_pct: 0.3 }], position_sizing: { method: "equal_weight" as const }, risk_management: {}, cash_management: { hold_cash_when_no_signal: true } },
    chatSeed: "",
    whenInCopy:
      "At each month-end, compute the Piotroski F-Score (a 9-point composite of profitability, leverage, and operating efficiency signals from the most recent annual filing) for every stock in your universe. Buy the top 30% by F-Score — typically stocks scoring 8 or 9 out of 9 — sized equal-weight. Piotroski's original 2000 research showed these high-F-Score names outperform precisely because their improving fundamentals are slow to be repriced by the market.",
    whenOutCopy:
      "At each monthly rebalance, re-compute F-Scores using any updated annual data and rebuild from the new top 30%. Names whose F-Score has dropped out of the top tercile are sold; new high-quality entrants are bought. Because F-Scores update annually (when 10-K filings drop), portfolio turnover is modest — most months only the marginal names change, with the major rotation happening 2–3 months after the bulk of fiscal-year filing season.",
  },
  {
    id: "pead-drift-cs",
    name: "Post-Earnings Drift (PEAD)",
    category: "Momentum" as const,
    description: "After a top-decile earnings surprise, hold the stock for 60 days to capture the gradual market revaluation.",
    whatItCaptures: "Markets under-react to large earnings surprises — positive shocks continue to generate abnormal returns for weeks after announcement.",
    whatItTests: "Whether post-announcement drift is exploitable after realistic transaction costs.",
    dataRequirement: "Quarterly EPS and analyst estimates — not yet available",
    universeDescription: "Active-reporting equities",
    defaultTickers: [],
    multiTicker: true,
    minTickers: 20,
    tickerLabel: "",
    availability: "unavailable" as const,
    evidenceTier: "A",
    capacityBadge: "Prosumer",
    horizonBadge: "Swing",
    comingSoon: true,
    caveats: ["Requires EPS surprise data pipeline."],
    dataGapReason: "Requires quarterly EPS and analyst estimate data — coming in Phase B.",
    strategy: { strategy_name: "Post-Earnings Announcement Drift", strategy_type: "pead_drift", universe: ["AAPL"], benchmark: "SPY", start_date: fiveYearsAgo, end_date: today, initial_capital: 100000, rebalance_frequency: "weekly" as const, transaction_cost_bps: 10, slippage_bps: 10, rules: [{ holding_window_days: 60, top_pct: 0.1 }], position_sizing: { method: "equal_weight" as const }, risk_management: {}, cash_management: { hold_cash_when_no_signal: true } },
    chatSeed: "",
    whenInCopy:
      "Each week, scan for stocks that reported earnings in the previous 5 trading days. Compute the standardized earnings surprise (SUE — earnings minus consensus estimate, scaled by historical surprise volatility) for each report and buy the top decile of positive surprises. The thesis (Bernard & Thomas 1989; UCLA Anderson 2024) is that markets under-react to large surprises, so the stock keeps drifting up for weeks after announcement and systematic buyers can earn the drift.",
    whenOutCopy:
      "Each position is held for exactly 60 trading days (about 3 months) from the earnings-announcement date, regardless of intervening price action — that's the documented drift window. After 60 days the position is sold and the capital recycles into newer surprise-decile names. There are no stops or take-profits — the time-based exit IS the entire risk-management mechanism, which means individual positions can drawdown significantly without triggering an early exit.",
  },
];


// ── PRD-06: Fundamental Analysis types ───────────────────────────────────────

export interface CompanyProfile {
  symbol: string;
  name: string;
  sector?: string | null;
  industry?: string | null;
  exchange?: string | null;
  country?: string | null;
  currency?: string | null;
  description?: string | null;
  ceo?: string | null;
  employees?: number | null;
  website?: string | null;
  price?: number | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  dividend_yield?: number | null;
  beta?: number | null;
  week_52_high?: number | null;
  week_52_low?: number | null;
  is_etf: boolean;
  is_actively_trading: boolean;
  peers: string[];
  data_source: string;
  as_of_date?: string | null;
}

export interface KeyMetrics {
  symbol: string;
  as_of_date?: string | null;
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  ps_ratio?: number | null;
  ev_to_ebitda?: number | null;
  peg_ratio?: number | null;
  free_cash_flow_yield?: number | null;
  dividend_yield?: number | null;
  roe?: number | null;
  roa?: number | null;
  free_cash_flow_per_share?: number | null;
  operating_cash_flow_per_share?: number | null;
  debt_to_equity?: number | null;
  current_ratio?: number | null;
  interest_coverage?: number | null;
  net_debt_to_ebitda?: number | null;
  revenue_per_share?: number | null;
  earnings_per_share?: number | null;
  book_value_per_share?: number | null;
  data_source: string;
}

export interface FundamentalSummary {
  profile: CompanyProfile;
  metrics: KeyMetrics;
  disclaimer: string;
}

// ── PRD-07: Stock Screener types ──────────────────────────────────────────────

export interface ScreenerResult {
  symbol: string;
  name: string;
  sector?: string | null;
  industry?: string | null;
  exchange?: string | null;
  country?: string | null;
  market_cap?: number | null;
  market_cap_category?: string | null;
  pe_ratio?: number | null;
  dividend_yield?: number | null;
  beta?: number | null;
  week_52_high?: number | null;
  week_52_low?: number | null;
}

export interface ScreenerResponse {
  results: ScreenerResult[];
  total: number;
  offset: number;
  limit: number;
  filters_applied: Record<string, unknown>;
}

export interface ScreenerFiltersResponse {
  sectors: string[];
  industries: string[];
  countries: string[];
  exchanges: string[];
  market_cap_categories: string[];
  total_symbols: number;
}

/** Phase 1f — preset summary metadata for the 9 Market Pulse screener
 * tile cards. Returned by `GET /api/screener/presets`. */
export interface ScreenerPresetSummary {
  slug: string;
  title: string;
  description: string;
  icon: string;        // lucide-react icon name, e.g. "BrainCircuit"
  tier: "scout" | "strategist" | "quant";
  result_count: number;
  sample_tickers: string[];
}

export interface ScreenerPresetsResponse {
  presets: ScreenerPresetSummary[];
}

// ── PRD-15: Market Pulse types ────────────────────────────────────────────────

export interface IndexCard {
  symbol: string;
  name: string;
  price: number | null;
  perf_1d: number | null;
  perf_5d: number | null;
  sparkline_5d: number[];
  latest_date?: string | null;  // ISO date of most recent price bar
  is_stale?: boolean;           // true if data is >5 calendar days old
}

export interface MacroCard {
  symbol: string;
  label: string;
  price: number | null;
  perf_1d: number | null;
  latest_date?: string | null;
  is_stale?: boolean;
}

export interface SectorCard {
  symbol: string;
  name: string;
  price: number | null;
  perf_1d: number | null;
  perf_5d: number | null;
  rs_vs_spy_5d: number | null;  // excess return vs SPY
  cmf_20: number | null;        // Chaikin Money Flow, -1 to +1
  volume_ratio: number | null;  // 5d avg vol / 20d avg vol
  latest_date?: string | null;
  is_stale?: boolean;
}

export interface AssetCard {
  symbol: string;
  name: string;
  sector: string | null;
  price: number | null;
  perf_1d: number | null;
  cmf_20: number | null;
  market_cap: number | null;
  latest_date?: string | null;
  is_stale?: boolean;
}

/** Phase 1b — LLM-generated narrative block. Null when LLM_PROVIDER is
 * unset or the backend's narrative generation fails. Frontend falls back
 * to the deterministic template in `lib/market-pulse-narrative.ts`.
 *
 * Phase 1g (2026-05-22) — `as_of` anchors the narrative to a specific
 * calendar date so users can tell at a glance whether they're reading
 * today's read or yesterday's leftover cache. Populated by the route
 * layer, not the LLM. */
export interface MarketNarrative {
  headline: string;
  sector_rotation: string;
  watch_items: string[];
  as_of?: string | null;
}

/** Phase 1c — Macro Pulse table payload. 4 rows: Growth / Inflation /
 * Rates / Stress. Rates + Inflation are real (Alpha Vantage); Growth +
 * Stress are mock pending a FRED API key for ISM PMI and HY OAS. The
 * `source` field tells the UI whether to show a "real data" or "mock
 * data" hint inline. */
export interface MacroSignal {
  category: "Growth" | "Inflation" | "Rates" | "Stress";
  latestLabel: string;
  trendDirection: "up" | "down" | "flat";
  trendLabel: string;
  takeaway: string;
  explanation: string;
  series6M: number[];
  series1Y: number[];
  series5Y: number[];
  source: "alpha_vantage" | "mock_pending_fred" | "mock_av_failed";
}

export interface MarketPulseResponse {
  market: string;               // "US" | "CN"
  as_of: string;
  indices: IndexCard[];
  macro: MacroCard[];
  sectors: SectorCard[];        // sorted by CMF descending
  top_assets: AssetCard[];      // top 10 by CMF from full universe
  featured_etfs: AssetCard[];
  narrative?: MarketNarrative | null;
  macro_signals?: MacroSignal[];
}

/** Phase 1d — (sector, SPY) cumulative-return comparison series. Both
 * series are normalized to 0 at the start of the window so the chart
 * shows comparative drift. `sector_day` etc are pre-computed perf
 * numbers used by the returns table underneath the chart. */
export interface SectorComparisonPoint {
  date: string;     // ISO date
  sector: number;   // cumulative return, decimal (0.082 = +8.2%)
  spy: number;
}

export interface SectorComparisonResponse {
  symbol: string;
  sector_name: string;
  range: "1M" | "6M" | "YTD" | "1Y" | "3Y";
  series: SectorComparisonPoint[];
  sector_day: number | null;
  sector_ytd: number | null;
  sector_1y: number | null;
  sector_3y: number | null;
  spy_day: number | null;
  spy_ytd: number | null;
  spy_1y: number | null;
  spy_3y: number | null;
}

/** Phase 1e — History Rhymes / macro similarity match. One historical
 * 5-day window that resembles today's normalized 5-day macro return
 * vector, with the SPY 30-trading-day post-window outcome. */
export interface HistoryRhymeMatch {
  label: string;                       // "Aug 13–19, 2019"
  start_date: string;                  // ISO date
  end_date: string;                    // ISO date
  context: string;                     // heuristic regime tag
  similarity: number;                  // 0..1
  post_window_30d_return: number;      // SPY return 30d after window
  sample_sparkline: number[];          // 30 normalized SPY values (start=100)
}

export interface HistoryRhymesResponse {
  market: string;
  as_of: string;
  today_vector: Record<string, number>;
  matches: HistoryRhymeMatch[];
  caveat: string;
}

/** Phase 1g — per-source freshness report. Powers `<DataFreshnessFooter />`
 * at the foot of `/stocks` so users can tell whether they're looking at
 * today's data or yesterday's leftover cache. */
export type DataLatencyStatus = "fresh" | "stale" | "very_stale" | "missing";

export interface DataLatencyMember {
  symbol: string;
  latest_date: string | null;
  status: DataLatencyStatus;
  hours_stale: number | null;
}

export interface DataLatencySource {
  group: string;
  description: string;
  latest_date: string | null;
  status: DataLatencyStatus;
  hours_stale: number | null;
  members: DataLatencyMember[];
}

export interface DataLatencyResponse {
  as_of: string;       // server timestamp
  today: string;       // server's "today" (ISO date)
  overall_status: DataLatencyStatus;
  overall_hours_stale: number | null;
  overall_latest_date: string | null;
  sources: DataLatencySource[];
}

// ── PRD-trend: Stock Trend types ──────────────────────────────────────────────

export interface StockTrendData {
  latest_price?: number | null;
  latest_date?: string | null;
  perf_1m?: number | null;
  perf_3m?: number | null;
  perf_6m?: number | null;
  perf_12m?: number | null;
  ma_50?: number | null;
  ma_200?: number | null;
  price_vs_ma50?: number | null;
  price_vs_ma200?: number | null;
  vol_trend?: string | null;
  avg_vol_20d?: number | null;
  avg_vol_65d?: number | null;
  rs_vs_spy_3m?: number | null;
  rs_vs_spy_12m?: number | null;
  price_series_90d: Array<{ date: string; price: number }>;
  bar_count: number;
  data_source: string;
}

// ── PRD-08d: Revenue Segment types ───────────────────────────────────────────

export interface SegmentYear {
  year: number;
  segments: Record<string, number>;  // {segmentName: revenueValue}
}

export interface RevenueSegmentSection {
  product_years: SegmentYear[];      // newest first, up to 5
  geo_years: SegmentYear[];
  segment_names: string[];           // ordered by latest revenue
  geo_names: string[];
  segment_colors: string[];
  geo_colors: string[];
  fallback_note?: string | null;
}

// ── PRD-08a: Company Overview types ──────────────────────────────────────────

export interface BusinessMapSection {
  one_line_summary?: string | null;
  primary_value_chain_role?: string | null;
  secondary_value_chain_roles: string[];
  customer_types: string[];
  revenue_model?: string | null;
  margin_implication?: string | null;
  cyclicality_implication?: string | null;
  pricing_power_implication?: string | null;
  confidence: string;
  source_notes: string[];
}

export interface SupplyChainEntry {
  name: string;
  symbol?: string | null;
}

export interface CompetitorRankingEntry {
  symbol: string;
  name: string;
  revenue: string;           // formatted e.g. "$209B"
  revenue_raw: number;
  share: number;             // 0.0 - 1.0
  position: string;          // Dominant / Market Leader / Major Participant / Niche
  trend_5yr: number[];
}

export interface CompetitorSegment {
  segment: string;
  rankings: CompetitorRankingEntry[];
  disclaimer: string;
}

export interface MarketPositionSection {
  market_category?: string | null;
  market_size_estimate: string;
  market_growth_label?: string | null;
  competitive_position_label?: string | null;
  market_share_notes?: string | null;
  key_competitors: string[];
  key_growth_drivers: string[];
  key_risks: string[];
  upstream_suppliers: SupplyChainEntry[];
  downstream_customers: SupplyChainEntry[];
  competitor_segments: CompetitorSegment[];
  confidence: string;
  source_notes: string[];
}

export interface FinancialCheckSection {
  financial_validation_label: string;
  financial_validation_score: number;
  valuation_risk_score: number;
  overall_score: number;
  growth_summary?: string | null;
  profitability_summary?: string | null;
  cash_flow_summary?: string | null;
  balance_sheet_summary?: string | null;
  valuation_summary?: string | null;
  revenue_yoy?: number | null;
  revenue_3y_cagr?: number | null;
  eps_yoy?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  roe?: number | null;
  free_cash_flow?: number | null;
  fcf_margin?: number | null;
  fcf_conversion?: number | null;
  cash?: number | null;
  total_debt?: number | null;
  net_debt?: number | null;
  debt_to_equity?: number | null;
  current_ratio?: number | null;
  pe_ratio?: number | null;
  ps_ratio?: number | null;
  pb_ratio?: number | null;
  peg_ratio?: number | null;
  fcf_yield?: number | null;
  ev_ebitda?: number | null;
  dividend_yield?: number | null;
  revenue_series: Array<{ date: string; revenue?: number | null; gross_margin?: number | null; operating_margin?: number | null }>;
  margin_series: unknown[];
  fcf_series: Array<{ date: string; fcf?: number | null; operating_cf?: number | null }>;
  warnings: string[];
  confidence: string;
  source_notes: string[];
}

export interface CompanyOverviewResponse {
  symbol: string;
  name: string;
  price?: number | null;
  market_cap?: number | null;
  sector?: string | null;
  industry?: string | null;
  exchange?: string | null;
  country?: string | null;
  as_of_date?: string | null;
  revenue_segments: RevenueSegmentSection;
  business_map: BusinessMapSection;
  market_position: MarketPositionSection;
  financial_check: FinancialCheckSection;
  disclaimer: string;
}

// ── PRD-09/10: News & Sentiment ──────────────────────────────────────────────

export type SentimentProviderStatus = "active" | "not_configured" | "rate_limited" | "failed" | "unavailable";

export interface NewsArticle {
  provider: string;
  symbol: string;
  title: string;
  summary?: string | null;
  source_name?: string | null;
  url?: string | null;
  published_at?: string | null;
  topics: string[];
  sentiment_score?: number | null;
  sentiment_label?: string | null;
  relevance_score?: number | null;
}

export interface CommunityMention {
  provider: string;
  platform: string;
  symbol: string;
  title?: string | null;
  text: string;
  author?: string | null;
  community_name?: string | null;
  url?: string | null;
  published_at?: string | null;
  upvotes?: number | null;
  comments?: number | null;
  sentiment_score?: number | null;
  sentiment_label?: string | null;
}

export interface NewsCatalystSection {
  main_catalyst_summary?: string | null;
  catalyst_type?: string | null;
  catalyst_scope?: string | null;
  time_horizon?: string | null;
  expected_business_impact?: string | null;
  catalyst_materiality_label?: string | null;
  information_source_quality_label?: string | null;
  source_quality_notes?: string | null;
  key_articles: Array<{ title: string; url?: string }>;
  confidence: string;
  source_notes: string[];
}

export interface NewsSentimentSection {
  news_sentiment_label?: string | null;
  news_sentiment_trend?: string | null;
  bullish_news_themes: string[];
  bearish_news_themes: string[];
  conflicting_news_signals: string[];
  news_sentiment_score?: number | null;
  source_diversity?: string | null;
  confidence: string;
  source_notes: string[];
}

export interface CommunityPulseSection {
  community_sentiment_label?: string | null;
  community_attention_label?: string | null;
  community_attention_trend?: string | null;
  dominant_sources: string[];
  bullish_community_themes: string[];
  bearish_community_themes: string[];
  representative_discussions: Array<{ title?: string; url?: string; community?: string }>;
  confidence: string;
  source_notes: string[];
}

export interface SignalQualityRiskSection {
  signal_quality_label?: string | null;
  news_community_alignment?: string | null;
  materiality_assessment?: string | null;
  information_source_quality_assessment?: string | null;
  crowding_risk?: string | null;
  overreaction_risk?: string | null;
  headline_risks: string[];
  required_next_checks: string[];
  confidence: string;
  source_notes: string[];
}

export interface SentimentTakeaway {
  takeaway_label: string;
  takeaway_summary?: string | null;
  suggested_user_action?: string | null;
}

export interface SentimentScores {
  catalyst_score: number;
  catalyst_materiality_score: number;
  information_source_quality_score: number;
  news_sentiment_score: number;
  community_sentiment_score: number;
  attention_score: number;
  signal_quality_score: number;
  risk_score: number;
  overall_sentiment_signal_score: number;
  overall_label: string;
}

export interface SentimentSummaryResponse {
  symbol: string;
  as_of_datetime?: string | null;
  expires_at?: string | null;
  news_catalyst: NewsCatalystSection;
  news_sentiment: NewsSentimentSection;
  community_pulse: CommunityPulseSection;
  signal_quality_risk: SignalQualityRiskSection;
  takeaway: SentimentTakeaway;
  scores: SentimentScores;
  provider_status: Record<string, string>;
  warnings: string[];
  disclaimer: string;
}

export interface ProvidersStatusResponse {
  alpha_vantage: SentimentProviderStatus;
  reddit: SentimentProviderStatus;
  x: SentimentProviderStatus;
  internal_community: SentimentProviderStatus;
}

export interface SentimentCandidateResult {
  symbol: string;
  company_name?: string | null;
  overall_sentiment_signal_score: number;
  overall_label: string;
  takeaway_label: string;
  takeaway_summary?: string | null;
  catalyst_type?: string | null;
  catalyst_materiality_label?: string | null;
  news_sentiment_label?: string | null;
  signal_quality_label?: string | null;
  bullish_themes: string[];
  bearish_themes: string[];
  provider_status: Record<string, string>;
}

export interface SentimentAnalyzeResponse {
  candidates: SentimentCandidateResult[];
  provider_status: Record<string, string>;
  warnings: string[];
  toolkit_id?: string | null;
}

export interface SentimentSandboxResponse {
  review_verdict: string;
  trust_score: number;
  key_concerns: string[];
  missing_data: string[];
  noise_risks: string[];
  source_limitations: string[];
  required_next_checks: string[];
  final_warning?: string | null;
}

export interface SentimentToolkit {
  id: string;
  name: string;
  description: string;
}

// ── PRD-12/13/14: Community Layer ────────────────────────────────────────────

export interface WatchlistItem {
  symbol: string;
  added_at: string;
}

export interface WatchlistResponse {
  symbols: WatchlistItem[];
  count: number;
}

export interface VoteSummary {
  symbol: string;
  bull: number;
  bear: number;
  hold: number;
  total: number;
  user_vote?: "bull" | "bear" | "hold" | null;
}

export interface SignalScore {
  symbol: string;
  watchlist_count: number;
  bull_votes: number;
  bear_votes: number;
  hold_votes: number;
  total_votes: number;
  strategy_run_count: number;
  thesis_count: number;
  latest_thesis_at?: string | null;
  signal_score: number;
  signal_label: string;
  computed_at?: string | null;
  disclaimer: string;
}

export interface CommunityBoardResponse {
  items: SignalScore[];
  total: number;
  disclaimer: string;
}

export interface CommentResponse {
  id: number;
  user_id: string;
  strategy_slug: string;
  content: string;
  created_at: string;
  display_name?: string | null;
  avatar_url?: string | null;
}

export interface CommentsListResponse {
  comments: CommentResponse[];
  total: number;
}

export interface UpvoteResponse {
  slug: string;
  upvote_count: number;
  user_upvoted: boolean;
}

export interface StockThesis {
  id: number;
  user_id: string;
  symbol: string;
  stance: "bull" | "bear" | "hold";
  timeframe: string;
  thesis: string;
  risks: string;
  evidence_url?: string | null;
  created_at: string;
  display_name?: string | null;
  avatar_url?: string | null;
}

export interface StockThesisListResponse {
  theses: StockThesis[];
  total: number;
  disclaimer: string;
}

export interface LivePerformance {
  slug: string;
  published_at: string;
  total_return?: number | null;
  total_return_pct?: number | null;
  days_tracked: number;
  current_signal?: string | null;
  last_price_date?: string | null;
  equity_curve: Array<{ date: string; value: number }>;
  error?: string | null;
  computed_at?: string | null;
}

export interface PublicStrategyItem {
  slug: string;
  name: string;
  saved_at: string;
  upvote_count: number;
  trust_score: number;
  verification_status: string;
  follower_count: number;
  live?: LivePerformance | null;
}


// ── Stage 7: Chat v2 (ticket #7) ──────────────────────────────────────────────
//
// Types-first per CLAUDE.md frontend rule. These mirror the backend SSE
// protocol — every field in a frame the widget might receive is enumerated
// here so schema drift surfaces at typecheck-time rather than runtime.

/** Context the widget tells the backend about for this conversation.
 *  Backend uses it for system-prompt anchoring (e.g., "looking at AAPL"). */
export type ChatContextType =
  | "workspace"
  | `stock:${string}`
  | `backtest:${string}`
  | `community_strategy:${string}`
  | "user_saved"
  | "general";

export interface ChatMessageRequest {
  content: string;
  context_type?: ChatContextType | null;
  context_payload?: Record<string, unknown> | null;
}

/** SSE frame types produced by /api/chat/conversations/{id}/messages.
 *  Each `type` corresponds to one branch of the discriminated union below.
 *  Match the chat.py _sse(...) call sites exactly. */
export type ChatEventType =
  | "started"
  | "token"
  | "tool_call_start"
  | "tool_result"
  | "guardrail"
  | "done"
  | "error";

interface ChatEventBase {
  type: ChatEventType;
}

/** First frame after the request is accepted. Authed path includes
 *  conversation_id only; anonymous path also includes anon_turns_remaining
 *  so the widget can render "3 of 5 free turns left". */
export interface ChatStartedEvent extends ChatEventBase {
  type: "started";
  conversation_id: string;
  anon_turns_remaining?: number;
}

export interface ChatTokenEvent extends ChatEventBase {
  type: "token";
  text: string;
}

export interface ChatToolCallStartEvent extends ChatEventBase {
  type: "tool_call_start";
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ChatToolResultEvent extends ChatEventBase {
  type: "tool_result";
  call_id: string;
  name: string;
}

/** Ticket #9 guardrail action frames. The widget can use these to style
 *  the message differently (refusal banner, citation chip badge, warning). */
export interface ChatGuardrailEvent extends ChatEventBase {
  type: "guardrail";
  action:
    | "refusal_logged"
    | "citation_reprompt_succeeded"
    | "citation_warning_appended";
  category?: string;            // for refusal_logged
  uncited_count?: number;       // for citation_*
  rewritten_text?: string;      // for citation_reprompt_succeeded
}

export interface ChatDoneEvent extends ChatEventBase {
  type: "done";
  finish_reason: string;
}

export interface ChatErrorEvent extends ChatEventBase {
  type: "error";
  message: string;
  fatal?: boolean;
}

export type ChatEvent =
  | ChatStartedEvent
  | ChatTokenEvent
  | ChatToolCallStartEvent
  | ChatToolResultEvent
  | ChatGuardrailEvent
  | ChatDoneEvent
  | ChatErrorEvent;

/** Local widget state — one entry per displayed message. The widget
 *  builds these from streamed events; nothing on the wire matches this
 *  shape exactly. */
export interface UIChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  /** Parsed `<cite source="..." id="..."/>` chips, extracted at render time. */
  citations?: Array<{ source: string; id?: string; raw: string }>;
  /** Set on assistant messages whose backend guardrail.action=refusal_logged. */
  refusalCategory?: string;
  /** Set when citation_warning_appended fires — widget can show a warning. */
  hasCitationWarning?: boolean;
  /** Set when this message is mid-stream (tokens still arriving). */
  isStreaming?: boolean;
  /** Tool-message body, displayed as a collapsed chip rather than prose. */
  toolName?: string;
}

// ── Module 2: Asset Behavior Fingerprint (2026-05-26) ────────────────────────

/** Coarse asset-type bucket. `pair` / `basket` are reserved for higher-level
 *  entry paths that pass an explicit override; single-ticker requests always
 *  surface as one of the four leaf types or `unknown`. */
export type AssetType =
  | "single_stock"
  | "commodity_etf"
  | "broad_etf"
  | "sector_etf"
  | "pair"
  | "basket"
  | "unknown";

/** Rule-based regime label — see backend's `classify_current_regime`. */
export type CurrentRegime = "trending" | "range_bound" | "volatile" | "mixed";

/** Bucketed history depth: good = 3y+, limited = 1-3y, insufficient = <1y. */
export type DataQuality = "good" | "limited" | "insufficient";

/** Backend response from `GET /api/assets/{symbol}/behavior`.
 *  Mirrors `AssetBehaviorFingerprint` in
 *  `apps/api/app/services/asset_behavior_service.py`. */
export interface AssetBehaviorFingerprint {
  symbol: string;
  asset_type: AssetType;
  /** % (0-100) of 200-day rolling windows where price > MA AND MA slope > 0.
   *  Null when history is too short or signal too noisy. */
  trending_pct: number | null;
  /** % (0-100) of |z|>1.5 extremes that reverted toward mean within 10 days.
   *  Null when fewer than ~5 extreme events were observed. */
  mean_reverting_pct: number | null;
  /** Annualised stdev of daily returns (last 252 trading days). Decimal —
   *  0.18 == 18% annual vol. Null when insufficient history. */
  realized_vol_1y: number | null;
  /** Annualised stdev over the last 5 years (or available history). Null
   *  when insufficient history. */
  realized_vol_5y: number | null;
  /** Worst peak-to-trough decline over the last 5 years, as a negative
   *  decimal (-0.32 == -32%). Null when insufficient history. */
  max_drawdown_5y: number | null;
  current_regime: CurrentRegime;
  data_quality: DataQuality;
  /** Plain-English suggestion of strategy family (trend / mean-reversion /
   *  risk overlay / diversified). Never includes buy/sell verbs or
   *  forward-looking claims. */
  strategy_implication: string;
}
