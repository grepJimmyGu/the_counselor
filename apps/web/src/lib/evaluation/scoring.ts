import type { StockMetricsInput } from "./types";

function clamp(v: number): number {
  return Math.max(0, Math.min(100, Math.round(v)));
}

function scoreRevenueGrowth(v: number | null): number {
  if (v === null) return 50;
  if (v > 0.20) return 95;
  if (v > 0.10) return 80;
  if (v > 0.05) return 65;
  if (v > 0.00) return 50;
  if (v > -0.05) return 30;
  return 10;
}

function scoreMargin(grossMargin: number | null, opMargin: number | null): number {
  let s = 0, w = 0;
  if (grossMargin !== null) { s += grossMargin > 0.5 ? 90 : grossMargin > 0.35 ? 70 : grossMargin > 0.2 ? 50 : 25; w++; }
  if (opMargin !== null) { s += opMargin > 0.2 ? 90 : opMargin > 0.1 ? 70 : opMargin > 0 ? 45 : 15; w++; }
  return w > 0 ? s / w : 50;
}

function scoreFCF(fcfMargin: number | null, fcfConversion: number | null): number {
  let s = 0, w = 0;
  if (fcfMargin !== null) { s += fcfMargin > 0.25 ? 95 : fcfMargin > 0.15 ? 80 : fcfMargin > 0.05 ? 60 : fcfMargin > 0 ? 40 : 15; w++; }
  if (fcfConversion !== null) { s += fcfConversion > 1.0 ? 95 : fcfConversion > 0.8 ? 80 : fcfConversion > 0.5 ? 55 : 25; w++; }
  return w > 0 ? s / w : 50;
}

function scoreROE(roe: number | null): number {
  if (roe === null) return 50;
  // Adjust for highly leveraged buyback companies: ROE > 100% is inflated, use moderate caps
  const r = Math.min(Math.abs(roe), 0.5); // cap at 50% for scoring
  if (r > 0.30) return 90;
  if (r > 0.20) return 75;
  if (r > 0.10) return 60;
  if (r > 0.00) return 40;
  return 20;
}

function scoreBalanceSheet(netDebt: number | null, currentRatio: number | null, debtEquity: number | null): number {
  let s = 0, w = 0;
  if (netDebt !== null && netDebt < 0) { s += 95; w++; } // net cash
  else if (netDebt !== null) {
    // rough EBITDA proxy: can't compute without EBITDA, use absolute threshold
    s += netDebt < 5e9 ? 75 : netDebt < 20e9 ? 60 : netDebt < 50e9 ? 45 : 30;
    w++;
  }
  if (currentRatio !== null) { s += currentRatio > 2 ? 90 : currentRatio > 1.5 ? 75 : currentRatio > 1 ? 55 : currentRatio > 0.75 ? 35 : 15; w++; }
  if (debtEquity !== null) { s += debtEquity < 0.3 ? 90 : debtEquity < 0.75 ? 70 : debtEquity < 1.5 ? 50 : debtEquity < 3 ? 30 : 10; w++; }
  return w > 0 ? s / w : 50;
}

export function calculateStockHealthScore(m: StockMetricsInput): number {
  const s1 = scoreRevenueGrowth(m.revenueYoy) * 0.20;
  const s2 = scoreMargin(m.grossMargin, m.operatingMargin) * 0.20;
  const s3 = scoreFCF(m.fcfMargin, m.fcfConversion) * 0.20;
  const s4 = scoreROE(m.roe) * 0.20;
  const s5 = scoreBalanceSheet(m.netDebt, m.currentRatio, m.debtToEquity) * 0.20;
  return clamp(s1 + s2 + s3 + s4 + s5);
}

function scoreFCFYield(v: number | null): number {
  if (v === null) return 50;
  if (v > 0.08) return 95;
  if (v > 0.05) return 80;
  if (v > 0.03) return 60;
  if (v > 0.01) return 40;
  return 20;
}

function scoreEVEBITDA(v: number | null): number {
  if (v === null) return 50;
  if (v < 8) return 90;
  if (v < 12) return 75;
  if (v < 18) return 55;
  if (v < 25) return 38;
  if (v < 35) return 25;
  return 12;
}

function scorePE(v: number | null): number {
  if (v === null) return 50;
  if (v < 12) return 90;
  if (v < 18) return 75;
  if (v < 25) return 58;
  if (v < 35) return 40;
  if (v < 50) return 25;
  return 10;
}

function scorePEG(v: number | null): number {
  if (v === null) return 50;
  if (v < 0.8) return 90;
  if (v < 1.2) return 75;
  if (v < 2.0) return 55;
  if (v < 3.0) return 35;
  return 15;
}

export function calculateStockValuationScore(m: StockMetricsInput): number {
  const s1 = scoreFCFYield(m.fcfYield) * 0.28;
  const s2 = scoreEVEBITDA(m.evEbitda) * 0.27;
  const s3 = scorePE(m.peRatio) * 0.22;
  const s4 = scorePEG(m.pegRatio) * 0.17;
  const s5 = 50 * 0.06; // DCF placeholder: neutral
  return clamp(s1 + s2 + s3 + s4 + s5);
}

function scoreMomentum(perf3m: number | null, perf12m: number | null): number {
  let s = 0, w = 0;
  if (perf3m !== null) {
    s += perf3m > 0.15 ? 90 : perf3m > 0.05 ? 72 : perf3m > 0 ? 55 : perf3m > -0.1 ? 38 : 18;
    w += 1.5; // 3M weighted higher for near-term momentum
    s = s * 1.5;
  }
  if (perf12m !== null) {
    s += perf12m > 0.25 ? 88 : perf12m > 0.10 ? 70 : perf12m > 0 ? 52 : perf12m > -0.2 ? 33 : 14;
    w += 1;
  }
  return w > 0 ? s / w : 50;
}

function scoreMAPosition(price: number | null, ma50: number | null, ma200: number | null): number {
  if (price === null) return 50;
  let s = 0, w = 0;
  if (ma50 !== null) {
    const pct = price / ma50 - 1;
    s += pct > 0.05 ? 80 : pct > 0 ? 62 : pct > -0.05 ? 42 : 22;
    w++;
  }
  if (ma200 !== null) {
    const pct = price / ma200 - 1;
    s += pct > 0.10 ? 85 : pct > 0 ? 65 : pct > -0.10 ? 38 : 18;
    w++;
  }
  return w > 0 ? s / w : 50;
}

function scoreRelativeStrength(rs3m: number | null): number {
  if (rs3m === null) return 50;
  // rs3m is excess return vs SPY over 3M
  if (rs3m > 0.10) return 88;
  if (rs3m > 0.03) return 72;
  if (rs3m > -0.03) return 52;
  if (rs3m > -0.10) return 34;
  return 16;
}

export function calculateStockTrendScore(m: StockMetricsInput): number {
  const hasAnyTrend = m.perf3m !== null || m.perf12m !== null || m.ma50 !== null || m.ma200 !== null;
  if (!hasAnyTrend) return 50; // neutral placeholder when no price data

  const s1 = scoreMomentum(m.perf3m, m.perf12m) * 0.35;
  const s2 = scoreMAPosition(m.price, m.ma50, m.ma200) * 0.30;
  const s3 = scoreRelativeStrength(m.rsVsSector) * 0.20;
  const s4 = 50 * 0.15; // volume + EPS revision — neutral placeholder
  return clamp(s1 + s2 + s3 + s4);
}

export function getFinalScore(health: number, valuation: number, trend: number): number {
  return clamp(health * 0.40 + valuation * 0.30 + trend * 0.30);
}

export function getFinalLabel(score: number): string {
  if (score >= 80) return "Attractive";
  if (score >= 60) return "Moderately Positive";
  if (score >= 40) return "Neutral";
  if (score >= 20) return "Caution";
  return "High Risk / Avoid";
}

export function getScoreStatus(score: number): "strong" | "neutral" | "weak" {
  if (score >= 65) return "strong";
  if (score >= 42) return "neutral";
  return "weak";
}
