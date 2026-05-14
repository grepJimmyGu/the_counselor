import type { StockMetricsInput, CommodityMetricsInput, DollarTrend } from "./types";

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

// ── Commodity scoring ─────────────────────────────────────────────────────────
// Weights per spec:
//   Health:    inventory 30%, supply-demand 25%, spare capacity 15%, cost curve 15%, disruption 15%
//   Valuation: spot vs marginal cost 25%, historical pct 20%, futures curve 25%, inventory adj 20%, ratio 10%
//   Trend:     momentum 25%, futures curve momentum 20%, CFTC positioning 20%, ETF flows 15%, macro 20%

function scoreInventoryPercentile(v: number | null): number {
  // Lower percentile = tighter = bullish
  if (v === null) return 50;
  if (v < 10) return 95;
  if (v < 25) return 82;
  if (v < 40) return 67;
  if (v < 60) return 50;
  if (v < 75) return 35;
  if (v < 90) return 20;
  return 10;
}

function scoreSupplyDemand(label: string | null, balance: number | null): number {
  if (label === "deficit") return 82;
  if (label === "balanced") return 55;
  if (label === "surplus") {
    // Larger surplus = worse
    if (balance !== null && balance > 5) return 15;
    return 28;
  }
  return 50;
}

function scoreSpareCapacity(v: string | null): number {
  if (v === "low") return 88;    // Low spare capacity = tight market = bullish
  if (v === "medium") return 55;
  if (v === "high") return 22;
  return 50;
}

function scoreCostCurveSupport(spotPrice: number | null, marginalCost: number | null): number {
  // Is price above or below the cost of production?
  if (spotPrice === null || marginalCost === null || marginalCost === 0) return 50;
  const premium = (spotPrice - marginalCost) / marginalCost;
  if (premium > 0.5) return 80;   // Well above — healthy incentive
  if (premium > 0.2) return 65;
  if (premium > 0.0) return 52;
  if (premium > -0.1) return 38;  // At or slightly below breakeven
  return 18;                       // Below cost — producers losing money
}

function scoreDisruptionRisk(v: string | null): number {
  // High disruption risk = bullish (supply threat)
  if (v === "high") return 80;
  if (v === "medium") return 55;
  if (v === "low") return 35;
  return 50;
}

export function calculateCommodityHealthScore(m: CommodityMetricsInput): number {
  const s1 = scoreInventoryPercentile(m.inventoryPercentile) * 0.30;
  const s2 = scoreSupplyDemand(m.supplyDemandLabel, m.supplyDemandBalance) * 0.25;
  const s3 = scoreSpareCapacity(m.spareCapacity) * 0.15;
  const s4 = scoreCostCurveSupport(m.spotPrice, m.marginalCostEstimate) * 0.15;
  const s5 = scoreDisruptionRisk(m.disruptionRisk) * 0.15;
  return clamp(s1 + s2 + s3 + s4 + s5);
}

function scoreSpotVsMarginalCost(pct: number | null): number {
  // How expensive is spot relative to marginal cost?
  // Slight premium = fair value. Large premium = expensive. Discount = cheap.
  if (pct === null) return 50;
  if (pct < -0.10) return 88;   // Deep discount — below cost
  if (pct < 0.10) return 72;    // Near marginal cost — attractive
  if (pct < 0.30) return 55;    // Modest premium — fair
  if (pct < 0.60) return 38;    // Elevated premium
  if (pct < 1.00) return 22;    // Very expensive vs cost
  return 10;
}

function scoreHistoricalPercentile(v: number | null): number {
  // Where does spot sit in 10yr history? Lower = cheaper
  if (v === null) return 50;
  if (v < 15) return 90;
  if (v < 30) return 75;
  if (v < 50) return 58;
  if (v < 70) return 42;
  if (v < 85) return 26;
  return 12;
}

function scoreFuturesCurveValuation(curve: string | null, spread: number | null): number {
  // Backwardation = tight physical market = constructive
  if (curve === "backwardation") {
    if (spread !== null && spread < -0.05) return 88;  // Strong backwardation
    return 75;
  }
  if (curve === "flat") return 52;
  if (curve === "contango") {
    if (spread !== null && spread > 0.10) return 20;   // Deep contango = oversupply
    return 35;
  }
  return 50;
}

function scoreRelatedRatio(pct: number | null): number {
  // Ratio percentile: low = commodity cheap relative to companion
  if (pct === null) return 50;
  if (pct < 20) return 82;
  if (pct < 40) return 65;
  if (pct < 60) return 50;
  if (pct < 80) return 35;
  return 20;
}

export function calculateCommodityValuationScore(m: CommodityMetricsInput): number {
  const s1 = scoreSpotVsMarginalCost(m.spotVsMarginalCostPct) * 0.25;
  const s2 = scoreHistoricalPercentile(m.spotPercentile10yr) * 0.20;
  const s3 = scoreFuturesCurveValuation(m.futuresCurve, m.frontBackSpread) * 0.25;
  const s4 = scoreInventoryPercentile(m.inventoryPercentile) * 0.20; // inventory-adjusted signal
  const s5 = scoreRelatedRatio(m.relatedRatioPercentile) * 0.10;
  return clamp(s1 + s2 + s3 + s4 + s5);
}

function scoreCommodityMomentum(perf3m: number | null, perf12m: number | null): number {
  let s = 0, w = 0;
  if (perf3m !== null) {
    s += (perf3m > 0.12 ? 88 : perf3m > 0.05 ? 70 : perf3m > 0 ? 54 : perf3m > -0.08 ? 38 : 18) * 1.5;
    w += 1.5;
  }
  if (perf12m !== null) {
    s += perf12m > 0.20 ? 85 : perf12m > 0.08 ? 68 : perf12m > 0 ? 52 : perf12m > -0.15 ? 35 : 15;
    w++;
  }
  return w > 0 ? s / w : 50;
}

function scoreCFTCPositioning(v: number | null): number {
  // Crowded long (high pct) = contrarian bearish; crowded short (low pct) = contrarian bullish
  if (v === null) return 50;
  if (v > 85) return 22;   // Crowded long — reversal risk
  if (v > 70) return 40;
  if (v > 50) return 58;   // Moderate net long — constructive
  if (v > 30) return 70;
  if (v > 15) return 80;   // Crowded short — contrarian bullish
  return 88;
}

function scoreETFFlows(v: string | null): number {
  if (v === "inflows") return 72;
  if (v === "outflows") return 32;
  return 52;
}

function scoreMacroSupport(
  dollar: DollarTrend | null,
  realYield: string | null,
  inflation: string | null,
  chinaPMI: number | null,
  category: string,
): number {
  let s = 0, w = 0;
  // Dollar: weaker dollar supports USD-priced commodities
  if (dollar !== null) {
    const d = dollar as DollarTrend;
    s += d === "weakening" ? 72 : d === "stable" ? 52 : 32;
    w++;
  }
  // Real yields: falling = bullish for gold and risk assets
  if (realYield !== null && (category === "metals")) {
    s += realYield === "falling" ? 72 : realYield === "stable" ? 52 : 32;
    w++;
  }
  // Inflation expectations: rising = bullish for commodities broadly
  if (inflation !== null) {
    s += inflation === "rising" ? 70 : inflation === "stable" ? 52 : 35;
    w++;
  }
  // China PMI: industrial metals key driver
  if (chinaPMI !== null && (category === "metals" || category === "energy")) {
    s += chinaPMI > 52 ? 78 : chinaPMI > 50 ? 60 : chinaPMI > 48 ? 44 : 28;
    w++;
  }
  return w > 0 ? s / w : 50;
}

export function calculateCommodityTrendScore(m: CommodityMetricsInput): number {
  const s1 = scoreCommodityMomentum(m.perf3m, m.perf12m) * 0.25;
  const s2 = scoreFuturesCurveValuation(m.futuresCurve, m.frontBackSpread) * 0.20;
  const s3 = scoreCFTCPositioning(m.cftcPositioningPct) * 0.20;
  const s4 = scoreETFFlows(m.etfFlowsTrend) * 0.15;
  const s5 = scoreMacroSupport(
    m.dollarIndexTrend, m.realYieldTrend,
    m.inflationExpectationTrend, m.chinaPMI, m.category
  ) * 0.20;
  return clamp(s1 + s2 + s3 + s4 + s5);
}
