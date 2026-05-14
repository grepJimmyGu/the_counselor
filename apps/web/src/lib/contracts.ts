export type StrategyType =
  | "moving_average_filter"
  | "moving_average_crossover"
  | "momentum_rotation"
  | "rsi_mean_reversion"
  | "breakout"
  | "static_allocation";

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
  category: "Momentum" | "Rotation" | "Factor" | "Carry";
  description: string;
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
  ranking_measure?: "total_return";
  ranking_lookback_days?: number;
}

export interface PositionSizing {
  method: "equal_weight" | "fixed_weight";
  max_positions?: number;
  weights?: Record<string, number>;
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

// ── PRD-08c: Health Score types ───────────────────────────────────────────────

export interface HealthScoreSection {
  // Piotroski F-Score
  piotroski_score?: number | null;          // 0-9
  piotroski_label: string;                  // Weak / Neutral / Good / Strong / N/A
  piotroski_signals: Record<string, boolean | null | undefined>;
  // Altman Z-Score
  altman_z_score?: number | null;
  altman_z_label: string;                   // Safe / Grey Zone / Distress / N/A
  altman_z_na_reason?: string | null;
  // Industry percentile
  sector_piotroski_pct?: number | null;     // 0-100
  sector_piotroski_n?: number | null;       // peer count
  // QSV insights
  insight_quality?: string | null;
  insight_safety?: string | null;
  insight_value?: string | null;
  // Valuation carry-through
  ev_ebitda?: number | null;
  fcf_yield?: number | null;
  pe_ratio?: number | null;
  peg_ratio?: number | null;
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
  health_score: HealthScoreSection;
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
  live?: LivePerformance | null;
}
