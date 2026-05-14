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
