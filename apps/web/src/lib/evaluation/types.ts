export type AssetType = "stock" | "commodity";
export type DataQuality = "live" | "estimated" | "mocked" | "unavailable";
export type ScoreStatus = "strong" | "neutral" | "weak";

export interface MetricRow {
  name: string;
  value: string | number | null;
  formatted: string;
  unit?: string;
  change?: string | null;
  changeDir?: "up" | "down" | "neutral";
  status: ScoreStatus | null;
  interpretation: string;
  quality: DataQuality;
  sparkline?: number[];
  tooltip?: string;
}

export interface QuestionScore {
  question: string;
  answer: string;
  score: number;
  status: ScoreStatus;
  explanation: string;
  topMetrics: MetricRow[];
  warning: string | null;
}

export interface EvaluationResult {
  assetType: AssetType;
  health: QuestionScore;
  valuation: QuestionScore;
  trend: QuestionScore;
  overallScore: number;
  overallLabel: string;
  analystSummary: string;
  bullCase: string;
  bearCase: string;
  keyMetricsToWatch: string[];
  contradictionWarning: string | null;
}

export interface StockMetricsInput {
  ticker: string;
  companyName: string;
  sector: string | null;
  marketCap: number | null;
  price: number | null;
  revenueYoy: number | null;
  revenue3yCagr: number | null;
  grossMargin: number | null;
  operatingMargin: number | null;
  netMargin: number | null;
  roe: number | null;
  freeCashFlow: number | null;
  fcfMargin: number | null;
  fcfConversion: number | null;
  cash: number | null;
  netDebt: number | null;
  debtToEquity: number | null;
  currentRatio: number | null;
  interestCoverage: number | null;
  peRatio: number | null;
  pegRatio: number | null;
  evEbitda: number | null;
  fcfYield: number | null;
  psRatio: number | null;
  pbRatio: number | null;
  dividendYield: number | null;
  perf1m: number | null;
  perf3m: number | null;
  perf6m: number | null;
  perf12m: number | null;
  ma50: number | null;
  ma200: number | null;
  rsVsSector: number | null;
  epsRevisionTrend: "positive" | "negative" | "neutral" | null;
  shortInterest: number | null;
  revenueSeries: Array<{ date: string; revenue: number | null }>;
  marginSeries: unknown[];
  fcfSeries: Array<{ date: string; fcf: number | null }>;
}
