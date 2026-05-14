export type AssetType = "stock" | "commodity";
export type DataQuality = "live" | "estimated" | "mocked" | "unavailable";
export type ScoreStatus = "strong" | "neutral" | "weak";

// Commodity sub-types
export type CommodityCategory = "energy" | "metals" | "agriculture" | "softs";
export type FuturesCurve = "backwardation" | "contango" | "flat";
export type CapacityLevel = "low" | "medium" | "high";
export type RiskLevel = "low" | "medium" | "high";
export type SupplyDemandLabel = "deficit" | "balanced" | "surplus";
export type TrendDirection = "rising" | "falling" | "stable";
export type DollarTrend = "strengthening" | "weakening" | "stable";
export type FlowDirection = "inflows" | "outflows" | "neutral";

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

// ── Commodity input ───────────────────────────────────────────────────────────

export interface CommodityMetricsInput {
  // Identity
  symbol: string;                           // "GOLD" | "WTI" | "COPPER" | "WHEAT"
  name: string;
  category: CommodityCategory;
  unit: string;                             // "oz" | "bbl" | "lb" | "bu"

  // Current price
  spotPrice: number | null;
  perf1d: number | null;

  // ── Health: physical market ─────────────────────────────────────────────────
  inventoryPercentile: number | null;       // 0-100; lower = tighter
  supplyDemandLabel: SupplyDemandLabel | null;
  supplyDemandBalance: number | null;       // unit Mt or Mbbl; negative = deficit
  daysOfSupply: number | null;
  spareCapacity: CapacityLevel | null;
  productionGrowthYoy: number | null;
  consumptionGrowthYoy: number | null;
  marginalCostEstimate: number | null;      // same unit as spotPrice
  producerBreakevenCost: number | null;
  disruptionRisk: RiskLevel | null;

  // ── Valuation ───────────────────────────────────────────────────────────────
  futuresCurve: FuturesCurve | null;
  frontBackSpread: number | null;           // % spread front vs 12M contract
  spotVsMarginalCostPct: number | null;     // % premium over marginal cost
  spotPercentile10yr: number | null;        // 0-100
  relatedRatioLabel: string | null;         // "Gold/Oil: 48x"
  relatedRatioPercentile: number | null;    // 0-100

  // ── Trend / macro ───────────────────────────────────────────────────────────
  perf1m: number | null;
  perf3m: number | null;
  perf6m: number | null;
  perf12m: number | null;
  ma50: number | null;
  ma200: number | null;
  cftcPositioningPct: number | null;        // 0-100 (50=neutral, 85+=crowded long)
  etfFlowsTrend: FlowDirection | null;
  openInterestTrend: TrendDirection | null;
  dollarIndexTrend: DollarTrend | null;
  realYieldTrend: TrendDirection | null;
  inflationExpectationTrend: TrendDirection | null;
  chinaPMI: number | null;

  // Sparkline
  priceSeries: Array<{ date: string; price: number }>;
}

// ── Stock input ───────────────────────────────────────────────────────────────

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
