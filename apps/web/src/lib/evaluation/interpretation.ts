import type { StockMetricsInput, QuestionScore, MetricRow, ScoreStatus } from "./types";
import { getScoreStatus } from "./scoring";

// Formatting helpers
function fmtPct(v: number | null, digits = 1): string {
  if (v === null) return "N/A";
  return `${(v * 100).toFixed(digits)}%`;
}
function fmtMoney(v: number | null): string {
  if (v === null) return "N/A";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs/1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${sign}$${(abs/1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs/1e6).toFixed(0)}M`;
  return `${sign}$${abs.toFixed(0)}`;
}
function fmtX(v: number | null, digits = 1): string {
  return v !== null ? `${v.toFixed(digits)}x` : "N/A";
}

// suppress unused warning — metricStatus is available for future use
function _metricStatus(score: number): ScoreStatus {
  return score >= 65 ? "strong" : score >= 42 ? "neutral" : "weak";
}
void _metricStatus;

export function interpretStockHealth(m: StockMetricsInput, score: number): QuestionScore {
  const status = getScoreStatus(score);

  // Answer text
  let answer: string;
  if (score >= 75) answer = "The business is fundamentally strong across growth, margins, and cash generation.";
  else if (score >= 60) answer = "The business is in reasonable health with mostly positive signals.";
  else if (score >= 45) answer = "Health is mixed — some strengths but also areas of concern.";
  else answer = "Fundamentals show signs of stress — review margin and cash flow trends.";

  // Explanation with specifics
  const parts: string[] = [];
  if (m.revenueYoy !== null) {
    parts.push(`Revenue ${m.revenueYoy >= 0 ? "grew" : "declined"} ${fmtPct(Math.abs(m.revenueYoy))} YoY.`);
  }
  if (m.operatingMargin !== null) {
    parts.push(`Operating margin at ${fmtPct(m.operatingMargin)}.`);
  }
  if (m.fcfMargin !== null) {
    parts.push(`FCF margin of ${fmtPct(m.fcfMargin)}.`);
  }
  const explanation = parts.slice(0, 2).join(" ") || answer;

  // Top metrics
  const topMetrics: MetricRow[] = [
    {
      name: "Revenue Growth",
      value: m.revenueYoy,
      formatted: fmtPct(m.revenueYoy),
      change: m.revenue3yCagr !== null ? `3Y CAGR ${fmtPct(m.revenue3yCagr)}` : null,
      changeDir: (m.revenueYoy ?? 0) > 0 ? "up" : "down",
      status: m.revenueYoy !== null ? (m.revenueYoy > 0.1 ? "strong" : m.revenueYoy > 0 ? "neutral" : "weak") : null,
      interpretation: m.revenueYoy !== null
        ? m.revenueYoy > 0.15 ? "Strong growth — demand is expanding faster than the market"
        : m.revenueYoy > 0 ? "Modest growth — business is stable but not accelerating"
        : "Revenue is declining — monitor for further deterioration"
        : "Revenue data unavailable",
      quality: m.revenueYoy !== null ? "live" : "unavailable",
      sparkline: m.revenueSeries.map(r => r.revenue ?? 0).filter((v): v is number => v !== 0 || true),
      tooltip: "Year-over-year revenue change. Consistent growth above 10% signals strong demand.",
    },
    {
      name: "Operating Margin",
      value: m.operatingMargin,
      formatted: fmtPct(m.operatingMargin),
      status: m.operatingMargin !== null ? (m.operatingMargin > 0.2 ? "strong" : m.operatingMargin > 0.05 ? "neutral" : "weak") : null,
      interpretation: m.operatingMargin !== null
        ? m.operatingMargin > 0.25 ? "Exceptional profitability — strong pricing power or cost structure"
        : m.operatingMargin > 0.1 ? "Healthy margins — business is efficiently run"
        : "Thin margins — limited buffer against cost pressures"
        : "Margin data unavailable",
      quality: m.operatingMargin !== null ? "live" : "unavailable",
      tooltip: "Operating income as a % of revenue. >20% indicates strong pricing power.",
    },
    {
      name: "FCF Margin",
      value: m.fcfMargin,
      formatted: fmtPct(m.fcfMargin),
      status: m.fcfMargin !== null ? (m.fcfMargin > 0.15 ? "strong" : m.fcfMargin > 0.05 ? "neutral" : "weak") : null,
      interpretation: m.fcfMargin !== null
        ? m.fcfMargin > 0.20 ? "Excellent cash generation — high earnings quality"
        : m.fcfMargin > 0.08 ? "Solid free cash flow — company funds itself internally"
        : "Low cash conversion — watch for working capital or capex pressure"
        : "FCF data unavailable",
      quality: m.fcfMargin !== null ? "live" : "unavailable",
      sparkline: m.fcfSeries.map(r => r.fcf ?? 0),
      tooltip: "Free cash flow as % of revenue. Higher = better earnings quality.",
    },
  ];

  // Warning: find the worst signal
  let warning: string | null = null;
  if (m.currentRatio !== null && m.currentRatio < 1.0) {
    warning = `Current ratio of ${m.currentRatio.toFixed(2)} — current liabilities exceed current assets`;
  } else if (m.revenueYoy !== null && m.revenueYoy < -0.05) {
    warning = `Revenue declined ${fmtPct(Math.abs(m.revenueYoy))} — investigate root cause`;
  } else if (m.fcfConversion !== null && m.fcfConversion < 0.5) {
    warning = `FCF conversion of ${fmtPct(m.fcfConversion)} — reported earnings may overstate cash reality`;
  } else if (m.operatingMargin !== null && m.operatingMargin < 0.05) {
    warning = `Operating margin at ${fmtPct(m.operatingMargin)} — limited profitability buffer`;
  }

  return { question: "Is the business fundamentally healthy?", answer, score, status, explanation, topMetrics, warning };
}

export function interpretStockValuation(m: StockMetricsInput, score: number): QuestionScore {
  const status = getScoreStatus(score);

  let answer: string;
  if (score >= 75) answer = "Valuation looks attractive relative to cash flow and earnings.";
  else if (score >= 60) answer = "Valuation is reasonable — not cheap, but supported by fundamentals.";
  else if (score >= 45) answer = "Valuation is fair to mildly elevated — limited margin of safety.";
  else answer = "Valuation appears stretched — high multiple relative to growth and cash generation.";

  const parts: string[] = [];
  if (m.evEbitda !== null) parts.push(`EV/EBITDA of ${fmtX(m.evEbitda)}.`);
  if (m.fcfYield !== null) parts.push(`FCF yield of ${fmtPct(m.fcfYield)}.`);
  if (m.pegRatio !== null) parts.push(`PEG of ${fmtX(m.pegRatio, 2)}.`);
  const explanation = parts.slice(0, 2).join(" ") || answer;

  const topMetrics: MetricRow[] = [
    {
      name: "EV / EBITDA",
      value: m.evEbitda,
      formatted: fmtX(m.evEbitda),
      status: m.evEbitda !== null ? (m.evEbitda < 15 ? "strong" : m.evEbitda < 25 ? "neutral" : "weak") : null,
      interpretation: m.evEbitda !== null
        ? m.evEbitda < 12 ? "Below market average — value territory"
        : m.evEbitda < 20 ? "In line with quality growth companies"
        : "Premium multiple — priced for strong execution"
        : "EV/EBITDA unavailable",
      quality: m.evEbitda !== null ? "live" : "unavailable",
      tooltip: "Enterprise value divided by EBITDA. Lower is generally cheaper. <15x is often considered reasonable.",
    },
    {
      name: "FCF Yield",
      value: m.fcfYield,
      formatted: fmtPct(m.fcfYield, 1),
      changeDir: (m.fcfYield ?? 0) > 0.04 ? "up" : "down",
      status: m.fcfYield !== null ? (m.fcfYield > 0.05 ? "strong" : m.fcfYield > 0.025 ? "neutral" : "weak") : null,
      interpretation: m.fcfYield !== null
        ? m.fcfYield > 0.06 ? "High yield — significant cash return relative to market price"
        : m.fcfYield > 0.03 ? "Moderate yield — fair compensation for the risk"
        : "Low yield — market pricing in strong future growth"
        : "FCF yield unavailable",
      quality: m.fcfYield !== null ? "live" : "unavailable",
      tooltip: "Free cash flow per share / stock price. Think of it like a bond yield — higher means more cash per dollar invested.",
    },
    {
      name: "P/E Ratio",
      value: m.peRatio,
      formatted: fmtX(m.peRatio, 1),
      status: m.peRatio !== null ? (m.peRatio < 20 ? "strong" : m.peRatio < 35 ? "neutral" : "weak") : null,
      interpretation: m.peRatio !== null
        ? m.peRatio < 15 ? "Low P/E — potentially undervalued or facing headwinds"
        : m.peRatio < 25 ? "Market average range — reasonable for stable growers"
        : `${m.peRatio.toFixed(0)}x earnings — market expects strong growth to justify the premium`
        : "P/E unavailable",
      quality: m.peRatio !== null ? "live" : "unavailable",
      tooltip: "Price divided by earnings per share. Lower multiples are generally cheaper, but high-growth companies can justify higher P/E.",
    },
  ];

  let warning: string | null = null;
  if (m.evEbitda !== null && m.evEbitda > 30 && (m.revenueYoy ?? 0) < 0.10) {
    warning = `EV/EBITDA of ${fmtX(m.evEbitda)} is high for ${fmtPct(m.revenueYoy)} revenue growth`;
  } else if (m.pegRatio !== null && m.pegRatio > 2.5) {
    warning = `PEG ratio of ${fmtX(m.pegRatio, 2)} — growth may already be fully priced in`;
  } else if (m.fcfYield !== null && m.fcfYield < 0.015) {
    warning = `FCF yield of ${fmtPct(m.fcfYield, 1)} leaves little margin of safety`;
  } else if (m.pbRatio !== null && m.pbRatio > 10) {
    warning = `P/B ratio of ${fmtX(m.pbRatio, 1)} — significant premium to book value`;
  }

  return { question: "Is the asset cheap, fair, or expensive?", answer, score, status, explanation, topMetrics, warning };
}

export function interpretStockTrend(m: StockMetricsInput, score: number): QuestionScore {
  const hasData = m.perf1m !== null || m.perf3m !== null || m.perf12m !== null;
  const status = getScoreStatus(score);

  const answer = hasData
    ? score >= 65 ? "Market momentum is positive — price action confirms the fundamental thesis."
    : score >= 45 ? "Trend is mixed — no clear directional confirmation yet."
    : "Trend is negative — market is moving against the position."
    : "Market trend data requires price history integration.";

  const explanation = hasData
    ? `Based on ${m.perf3m !== null ? `3M performance of ${fmtPct(m.perf3m)}` : "available price data"}.`
    : "Price momentum, moving averages, and relative strength data are not yet available. This section will be populated when market data integration is complete.";

  const topMetrics: MetricRow[] = [
    {
      name: "3M Price Performance",
      value: m.perf3m,
      formatted: m.perf3m !== null ? fmtPct(m.perf3m) : "Pending",
      status: m.perf3m !== null ? (m.perf3m > 0.05 ? "strong" : m.perf3m > -0.05 ? "neutral" : "weak") : null,
      interpretation: m.perf3m !== null ? `${fmtPct(m.perf3m)} over 3 months` : "Requires price history API integration",
      quality: m.perf3m !== null ? "live" : "unavailable",
      tooltip: "3-month price return. Positive momentum often confirms improving fundamentals.",
    },
    {
      name: "vs 200-Day Moving Average",
      value: m.ma200,
      formatted: m.ma200 !== null && m.price !== null
        ? `${m.price > m.ma200 ? "+" : ""}${((m.price / m.ma200 - 1) * 100).toFixed(1)}%`
        : "Pending",
      status: m.ma200 !== null && m.price !== null ? (m.price > m.ma200 ? "strong" : "weak") : null,
      interpretation: m.ma200 !== null && m.price !== null
        ? `Price is ${m.price > m.ma200 ? "above" : "below"} the 200-day MA`
        : "Requires price history API integration",
      quality: m.ma200 !== null ? "live" : "unavailable",
      tooltip: "Price relative to 200-day moving average. Above = long-term uptrend, below = downtrend.",
    },
    {
      name: "EPS Revision Trend",
      value: m.epsRevisionTrend,
      formatted: m.epsRevisionTrend
        ? m.epsRevisionTrend.charAt(0).toUpperCase() + m.epsRevisionTrend.slice(1)
        : "Pending",
      status: m.epsRevisionTrend === "positive" ? "strong"
        : m.epsRevisionTrend === "negative" ? "weak"
        : m.epsRevisionTrend === "neutral" ? "neutral"
        : null,
      interpretation: m.epsRevisionTrend
        ? m.epsRevisionTrend === "positive" ? "Analysts are raising EPS estimates — positive signal"
        : m.epsRevisionTrend === "negative" ? "Analysts are cutting estimates — caution warranted"
        : "Estimates are stable"
        : "Requires analyst consensus data",
      quality: m.epsRevisionTrend !== null ? "estimated" : "unavailable",
      tooltip: "Direction of analyst EPS estimate revisions. Upgrades are bullish; downgrades are bearish.",
    },
  ];

  return {
    question: "Is the market moving in favor of or against this asset?",
    answer,
    score,
    status,
    explanation,
    topMetrics,
    warning: !hasData
      ? "Market trend data (price history, moving averages, relative strength) requires separate integration"
      : null,
  };
}

export function buildContradictionWarning(health: number, valuation: number, trend: number): string | null {
  if (health >= 65 && valuation <= 38) return "Strong fundamentals, but valuation is stretched — the market is pricing in significant future growth.";
  if (valuation >= 65 && trend <= 38) return "Attractive valuation, but price momentum has not yet confirmed the thesis — patience required.";
  if (health <= 38 && trend >= 65) return "Price is rallying but fundamentals are deteriorating — momentum without fundamental support.";
  if (health >= 65 && valuation >= 65 && trend <= 38) return "Strong fundamentals and reasonable valuation, but market sentiment is not yet on board.";
  return null;
}

export function buildAnalystSummary(
  m: StockMetricsInput,
  health: QuestionScore,
  valuation: QuestionScore,
  trend: QuestionScore,
  overallScore: number,
  overallLabel: string,
): { summary: string; bull: string; bear: string; watch: string[] } {
  const ticker = m.ticker;

  let summary: string;
  if (overallScore >= 70) {
    summary = `${ticker} presents a compelling investment case with ${health.score >= 65 ? "strong fundamentals" : "reasonable health"} and ${valuation.score >= 65 ? "attractive valuation" : "fair pricing"}. ${health.explanation} ${valuation.explanation}`;
  } else if (overallScore >= 50) {
    summary = `${ticker} shows a mixed picture. ${health.explanation} On valuation, ${valuation.explanation.toLowerCase()} The overall setup is ${overallLabel.toLowerCase()}, warranting selective positioning.`;
  } else {
    summary = `${ticker} faces headwinds across multiple dimensions. ${health.explanation} ${valuation.explanation} Investors should monitor closely before adding exposure.`;
  }

  const bull = health.score >= 60
    ? `Strong business fundamentals — ${m.grossMargin !== null ? `gross margin of ${fmtPct(m.grossMargin)}` : "solid profitability"} and ${m.freeCashFlow !== null ? `FCF of ${fmtMoney(m.freeCashFlow)}` : "cash generation"} support continued shareholder value creation.`
    : `If margin trends stabilize and revenue growth re-accelerates, the fundamental case improves significantly.`;

  const bear = valuation.score <= 45
    ? `At ${m.evEbitda !== null ? `${fmtX(m.evEbitda)} EV/EBITDA` : "current multiples"}, the stock has limited room for error. Any disappointment in growth or margins could trigger a meaningful de-rating.`
    : health.score <= 45
    ? `Deteriorating fundamentals — ${health.warning ?? "margin or cash flow pressure"} — could accelerate if macro conditions weaken.`
    : `Execution risk: the business must sustain current margins and growth trajectory to justify the valuation.`;

  const watch: string[] = [];
  watch.push("Quarterly revenue growth trajectory");
  if (m.operatingMargin !== null) watch.push("Operating margin trend (expanding or contracting)");
  if (m.fcfMargin !== null) watch.push("Free cash flow generation vs. net income");
  watch.push("Forward EPS estimates and revision direction");
  if (m.netDebt !== null && m.netDebt > 0) watch.push("Debt reduction pace and interest coverage");

  // suppress unused trend warning
  void trend;

  return { summary: summary.trim(), bull, bear, watch: watch.slice(0, 5) };
}
