import type { StockMetricsInput } from "./types";

export const MOCK_AAPL: StockMetricsInput = {
  ticker: "AAPL", companyName: "Apple Inc.", sector: "Technology",
  marketCap: 4390000000000, price: 213.50,
  revenueYoy: 0.064, revenue3yCagr: 0.018,
  grossMargin: 0.469, operatingMargin: 0.320, netMargin: 0.269, roe: 1.47,
  freeCashFlow: 98800000000, fcfMargin: 0.250, fcfConversion: 0.89,
  cash: 35900000000, netDebt: 76400000000, debtToEquity: 1.52,
  currentRatio: 0.89, interestCoverage: 28.5,
  peRatio: 35.8, pegRatio: 1.58, evEbitda: 27.6, fcfYield: 0.0295,
  psRatio: 8.2, pbRatio: null, dividendYield: 0.0045,
  perf1m: null, perf3m: null, perf6m: null, perf12m: null,
  ma50: null, ma200: null, rsVsSector: null, epsRevisionTrend: "neutral", shortInterest: null,
  revenueSeries: [
    { date: "2021", revenue: 365817000000 }, { date: "2022", revenue: 394328000000 },
    { date: "2023", revenue: 383285000000 }, { date: "2024", revenue: 391035000000 },
    { date: "2025", revenue: 415840000000 },
  ],
  marginSeries: [],
  fcfSeries: [
    { date: "2021", fcf: 92953000000 }, { date: "2022", fcf: 111443000000 },
    { date: "2023", fcf: 99584000000 }, { date: "2024", fcf: 108807000000 },
    { date: "2025", fcf: 98800000000 },
  ],
};

export const MOCK_NVDA: StockMetricsInput = {
  ticker: "NVDA", companyName: "NVIDIA Corporation", sector: "Technology",
  marketCap: 3200000000000, price: 131.20,
  revenueYoy: 1.22, revenue3yCagr: 0.73,
  grossMargin: 0.745, operatingMargin: 0.618, netMargin: 0.556, roe: 1.23,
  freeCashFlow: 60000000000, fcfMargin: 0.44, fcfConversion: 0.78,
  cash: 35800000000, netDebt: -19000000000, debtToEquity: 0.42,
  currentRatio: 4.2, interestCoverage: 85,
  peRatio: 38.5, pegRatio: 0.31, evEbitda: 32.1, fcfYield: 0.019,
  psRatio: 23.3, pbRatio: 47.2, dividendYield: 0.0003,
  perf1m: null, perf3m: null, perf6m: null, perf12m: null,
  ma50: null, ma200: null, rsVsSector: null, epsRevisionTrend: "positive", shortInterest: null,
  revenueSeries: [
    { date: "2021", revenue: 16675000000 }, { date: "2022", revenue: 26974000000 },
    { date: "2023", revenue: 44870000000 }, { date: "2024", revenue: 60922000000 },
    { date: "2025", revenue: 135000000000 },
  ],
  marginSeries: [],
  fcfSeries: [
    { date: "2021", fcf: 4694000000 }, { date: "2022", fcf: 3938000000 },
    { date: "2023", fcf: 13483000000 }, { date: "2024", fcf: 27021000000 },
    { date: "2025", fcf: 60000000000 },
  ],
};

export const MOCK_XOM: StockMetricsInput = {
  ticker: "XOM", companyName: "ExxonMobil Corporation", sector: "Energy",
  marketCap: 490000000000, price: 116.40,
  revenueYoy: -0.032, revenue3yCagr: 0.048,
  grossMargin: 0.328, operatingMargin: 0.135, netMargin: 0.107, roe: 0.132,
  freeCashFlow: 18000000000, fcfMargin: 0.055, fcfConversion: 0.91,
  cash: 18800000000, netDebt: 15500000000, debtToEquity: 0.18,
  currentRatio: 1.42, interestCoverage: 22.1,
  peRatio: 14.2, pegRatio: null, evEbitda: 7.8, fcfYield: 0.037,
  psRatio: 1.51, pbRatio: 1.89, dividendYield: 0.034,
  perf1m: null, perf3m: null, perf6m: null, perf12m: null,
  ma50: null, ma200: null, rsVsSector: null, epsRevisionTrend: "neutral", shortInterest: null,
  revenueSeries: [
    { date: "2021", revenue: 276692000000 }, { date: "2022", revenue: 398674000000 },
    { date: "2023", revenue: 334697000000 }, { date: "2024", revenue: 321686000000 },
    { date: "2025", revenue: 311000000000 },
  ],
  marginSeries: [],
  fcfSeries: [
    { date: "2021", fcf: 10268000000 }, { date: "2022", fcf: 37466000000 },
    { date: "2023", fcf: 14701000000 }, { date: "2024", fcf: 18000000000 },
    { date: "2025", fcf: 18000000000 },
  ],
};

export const MOCK_JPM: StockMetricsInput = {
  ticker: "JPM", companyName: "JPMorgan Chase & Co.", sector: "Financial Services",
  marketCap: 760000000000, price: 262.30,
  revenueYoy: 0.073, revenue3yCagr: 0.092,
  grossMargin: null, // N/A for banks
  operatingMargin: 0.382, netMargin: 0.265, roe: 0.172,
  freeCashFlow: null, fcfMargin: null, fcfConversion: null, // not standard for banks
  cash: 1400000000000, netDebt: null, // net debt not meaningful for banks
  debtToEquity: null, currentRatio: null, interestCoverage: null,
  peRatio: 14.8, pegRatio: null, evEbitda: null, fcfYield: null,
  psRatio: 4.1, pbRatio: 2.35, dividendYield: 0.021,
  perf1m: null, perf3m: null, perf6m: null, perf12m: null,
  ma50: null, ma200: null, rsVsSector: null, epsRevisionTrend: "positive", shortInterest: null,
  revenueSeries: [
    { date: "2021", revenue: 121649000000 }, { date: "2022", revenue: 128695000000 },
    { date: "2023", revenue: 154864000000 }, { date: "2024", revenue: 175484000000 },
    { date: "2025", revenue: 188000000000 },
  ],
  marginSeries: [],
  fcfSeries: [],
};

export const MOCK_DATA: Record<string, StockMetricsInput> = {
  AAPL: MOCK_AAPL, NVDA: MOCK_NVDA, XOM: MOCK_XOM, JPM: MOCK_JPM,
};

// ── Commodity mock data (realistic 2025 values) ───────────────────────────────

import type { CommodityMetricsInput } from "./types";

// Helper to build a simple trending price series
function buildPriceSeries(
  currentPrice: number,
  perf12m: number,
  points = 90,
): Array<{ date: string; price: number }> {
  const series = [];
  const startPrice = currentPrice / (1 + perf12m);
  const today = new Date("2026-05-14");
  for (let i = points - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const t = (points - 1 - i) / (points - 1);
    // Add some noise around the trend
    const noise = (Math.sin(i * 0.7) * 0.015 + Math.cos(i * 0.3) * 0.01);
    const price = startPrice + (currentPrice - startPrice) * t + startPrice * noise;
    series.push({ date: d.toISOString().slice(0, 10), price: Math.round(price * 100) / 100 });
  }
  return series;
}

// Gold: strong 2025 — central bank buying + geopolitical safe haven + USD weakness
export const MOCK_GOLD: CommodityMetricsInput = {
  symbol: "GOLD",
  name: "Gold",
  category: "metals",
  unit: "oz",
  spotPrice: 3320,
  perf1d: 0.004,
  // Health
  inventoryPercentile: 22,          // Low — ETF + central bank demand draining above-ground stocks
  supplyDemandLabel: "deficit",
  supplyDemandBalance: -500,         // ~500 ton deficit
  daysOfSupply: null,                // Not standard for gold
  spareCapacity: "low",
  productionGrowthYoy: 0.01,         // Mine production nearly flat
  consumptionGrowthYoy: 0.08,        // Central bank + ETF demand up sharply
  marginalCostEstimate: 1420,        // All-in sustaining cost ~$1,200-1,500/oz
  producerBreakevenCost: 1180,
  disruptionRisk: "medium",
  // Valuation
  futuresCurve: "backwardation",
  frontBackSpread: -0.02,            // Slight backwardation
  spotVsMarginalCostPct: 1.34,       // 134% above AISC — historically elevated
  spotPercentile10yr: 88,            // Near all-time highs in 10yr context
  relatedRatioLabel: "Gold/Oil: 48x",
  relatedRatioPercentile: 85,        // Gold expensive vs oil historically
  // Trend
  perf1m: 0.062,
  perf3m: 0.118,
  perf6m: 0.195,
  perf12m: 0.428,
  ma50: 3050,
  ma200: 2680,
  cftcPositioningPct: 78,            // Stretched long but not extreme
  etfFlowsTrend: "inflows",
  openInterestTrend: "rising",
  dollarIndexTrend: "weakening",
  realYieldTrend: "falling",
  inflationExpectationTrend: "rising",
  chinaPMI: null,
  priceSeries: buildPriceSeries(3320, 0.428),
};

// WTI Crude: range-bound 2025 — OPEC+ increases production, soft China demand
export const MOCK_WTI: CommodityMetricsInput = {
  symbol: "WTI",
  name: "WTI Crude Oil",
  category: "energy",
  unit: "bbl",
  spotPrice: 64.80,
  perf1d: -0.012,
  // Health
  inventoryPercentile: 58,           // Slightly above average — OPEC+ adding barrels
  supplyDemandLabel: "balanced",
  supplyDemandBalance: 0.3,          // Small surplus (Mbbl/d)
  daysOfSupply: 31,
  spareCapacity: "medium",           // OPEC+ has ~4-5 Mbbl/d spare
  productionGrowthYoy: 0.04,
  consumptionGrowthYoy: 0.015,       // Demand growth slowing with EV adoption
  marginalCostEstimate: 42,          // US shale breakeven ~$40-50/bbl
  producerBreakevenCost: 35,
  disruptionRisk: "medium",          // Middle East tensions ongoing
  // Valuation
  futuresCurve: "contango",
  frontBackSpread: 0.04,             // Mild contango
  spotVsMarginalCostPct: 0.54,       // 54% above marginal cost — not extreme
  spotPercentile10yr: 42,            // Below-median 10yr price
  relatedRatioLabel: "Gold/Oil: 51x",
  relatedRatioPercentile: 88,        // Oil cheap vs gold
  // Trend
  perf1m: -0.038,
  perf3m: -0.095,
  perf6m: -0.142,
  perf12m: -0.188,
  ma50: 70.2,
  ma200: 76.8,
  cftcPositioningPct: 32,            // Bearish — speculators have largely exited
  etfFlowsTrend: "outflows",
  openInterestTrend: "falling",
  dollarIndexTrend: "stable",
  realYieldTrend: "stable",
  inflationExpectationTrend: "stable",
  chinaPMI: 49.8,                    // Slightly below 50 — soft Chinese demand
  priceSeries: buildPriceSeries(64.80, -0.188),
};

// Copper: structural bull — energy transition, EV demand, constrained mine supply
export const MOCK_COPPER: CommodityMetricsInput = {
  symbol: "COPPER",
  name: "Copper",
  category: "metals",
  unit: "lb",
  spotPrice: 4.72,
  perf1d: 0.008,
  // Health
  inventoryPercentile: 18,           // Very tight — LME + COMEX warehouses at low levels
  supplyDemandLabel: "deficit",
  supplyDemandBalance: -0.35,        // ~350,000 tonne deficit
  daysOfSupply: 4.2,                 // Less than a week of visible stock
  spareCapacity: "low",              // Chile/Peru mine disruptions ongoing
  productionGrowthYoy: -0.02,        // Mine supply declining — grade depletion
  consumptionGrowthYoy: 0.06,        // EV + grid electrification driving demand
  marginalCostEstimate: 3.20,        // 90th percentile all-in cost
  producerBreakevenCost: 2.80,
  disruptionRisk: "high",            // Labor unrest in Chile, Peru regulatory risk
  // Valuation
  futuresCurve: "backwardation",
  frontBackSpread: -0.06,            // Meaningful backwardation
  spotVsMarginalCostPct: 0.475,      // 47.5% premium to marginal cost
  spotPercentile10yr: 65,            // Above median but not extreme
  relatedRatioLabel: "Gold/Copper: 704x",
  relatedRatioPercentile: 72,
  // Trend
  perf1m: 0.048,
  perf3m: 0.092,
  perf6m: 0.156,
  perf12m: 0.224,
  ma50: 4.42,
  ma200: 4.15,
  cftcPositioningPct: 65,            // Moderately long — not yet crowded
  etfFlowsTrend: "inflows",
  openInterestTrend: "rising",
  dollarIndexTrend: "weakening",
  realYieldTrend: "falling",
  inflationExpectationTrend: "rising",
  chinaPMI: 50.4,                    // Just above 50 — recovering
  priceSeries: buildPriceSeries(4.72, 0.224),
};

// Wheat: normalized after Russia-Ukraine spike — recovering global supply
export const MOCK_WHEAT: CommodityMetricsInput = {
  symbol: "WHEAT",
  name: "Wheat",
  category: "agriculture",
  unit: "bu",
  spotPrice: 5.48,
  perf1d: -0.003,
  // Health
  inventoryPercentile: 55,           // Near historical average — good crop season
  supplyDemandLabel: "surplus",
  supplyDemandBalance: 8.2,          // ~8.2 Mt surplus
  daysOfSupply: 92,                  // ~3 months global supply
  spareCapacity: null,               // Not applicable for agriculture
  productionGrowthYoy: 0.035,        // Good Northern Hemisphere harvest
  consumptionGrowthYoy: 0.015,
  marginalCostEstimate: 5.20,        // Cost of production in major exporting regions
  producerBreakevenCost: 4.80,
  disruptionRisk: "medium",          // Black Sea risk remains; La Niña watch
  // Valuation
  futuresCurve: "contango",
  frontBackSpread: 0.06,             // Normal carry cost for grain storage
  spotVsMarginalCostPct: 0.054,      // Just 5% above cost — tight margin
  spotPercentile10yr: 38,            // Below the median of the 2022-spiked decade
  relatedRatioLabel: "Corn/Wheat: 0.91x",
  relatedRatioPercentile: 42,
  // Trend
  perf1m: -0.022,
  perf3m: -0.058,
  perf6m: -0.098,
  perf12m: -0.142,
  ma50: 5.72,
  ma200: 5.95,
  cftcPositioningPct: 28,            // Speculators net short — possible contrarian signal
  etfFlowsTrend: "outflows",
  openInterestTrend: "stable",
  dollarIndexTrend: "stable",
  realYieldTrend: "stable",
  inflationExpectationTrend: "falling",
  chinaPMI: null,
  priceSeries: buildPriceSeries(5.48, -0.142),
};

export const MOCK_COMMODITY_DATA: Record<string, CommodityMetricsInput> = {
  GOLD: MOCK_GOLD,
  WTI: MOCK_WTI,
  COPPER: MOCK_COPPER,
  WHEAT: MOCK_WHEAT,
};
