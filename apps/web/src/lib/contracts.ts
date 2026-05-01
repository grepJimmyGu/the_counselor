export type StrategyType =
  | "moving_average_filter"
  | "moving_average_crossover"
  | "momentum_rotation"
  | "rsi_mean_reversion"
  | "breakout"
  | "static_allocation";

export type RebalanceFrequency = "daily" | "weekly" | "monthly" | "quarterly";

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

export interface StrategyChatResponse {
  assistant_message: string;
  strategy_json: StrategyJson | null;
  validation_status: "valid" | "needs_clarification" | "invalid";
  missing_fields: string[];
  clarification_questions: string[];
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
  drawdown_curve: CurvePoint[];
  trade_log: TradeLogItem[];
  annual_returns: { year: number; return_pct: number }[];
  monthly_returns: { year: number; month: number; return_pct: number }[];
  warnings: string[];
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
  overfitting_risk: string;
  benchmark_concerns: string[];
  regime_dependence: string[];
  parameter_sensitivity_concerns: string[];
  transaction_cost_concerns: string[];
  sample_size_concerns: string[];
  robustness_tests: string[];
  suggested_next_tests: string[];
  final_warning: string;
}

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
