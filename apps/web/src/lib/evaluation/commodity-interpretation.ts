/**
 * Rule-based interpretation for commodity evaluations.
 * No LLM — all logic is deterministic from the input metrics.
 */
import type {
  CommodityMetricsInput,
  QuestionScore,
  MetricRow,
  ScoreStatus,
  DollarTrend,
} from "./types";
import { getScoreStatus, getFinalScore, getFinalLabel } from "./scoring";

// ── Formatting helpers ────────────────────────────────────────────────────────

function fmtPct(v: number | null, digits = 1): string {
  if (v === null) return "N/A";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

function fmtPrice(v: number | null, unit: string): string {
  if (v === null) return "N/A";
  return `$${v.toFixed(2)}/${unit}`;
}

function fmtPctile(v: number | null): string {
  if (v === null) return "N/A";
  return `${Math.round(v)}th percentile`;
}

function metricStatus(good: boolean | null): ScoreStatus | null {
  if (good === null) return null;
  return good ? "strong" : "weak";
}

// ── Health interpretation ─────────────────────────────────────────────────────

export function interpretCommodityHealth(
  m: CommodityMetricsInput,
  score: number,
): QuestionScore {
  const status = getScoreStatus(score);

  let answer: string;
  if (score >= 72) {
    answer = `The physical ${m.name} market is tight — ${m.supplyDemandLabel === "deficit" ? "supply deficit" : "low inventories"} support near-term pricing power.`;
  } else if (score >= 52) {
    answer = `Market fundamentals are broadly balanced with mixed signals across supply, demand, and inventories.`;
  } else {
    answer = `The physical market looks loose — ${m.supplyDemandLabel === "surplus" ? "a supply surplus" : "elevated inventories"} create headwinds for prices.`;
  }

  const parts: string[] = [];
  if (m.inventoryPercentile !== null)
    parts.push(`Inventory at ${fmtPctile(m.inventoryPercentile)}.`);
  if (m.supplyDemandLabel)
    parts.push(`Market in ${m.supplyDemandLabel}.`);
  if (m.spareCapacity)
    parts.push(`Spare capacity: ${m.spareCapacity}.`);
  const explanation = parts.slice(0, 2).join(" ") || answer;

  const topMetrics: MetricRow[] = [
    {
      name: "Inventory Level",
      value: m.inventoryPercentile,
      formatted: m.inventoryPercentile !== null
        ? `${fmtPctile(m.inventoryPercentile)} vs history`
        : "N/A",
      status: m.inventoryPercentile !== null
        ? (m.inventoryPercentile < 25 ? "strong" : m.inventoryPercentile < 60 ? "neutral" : "weak")
        : null,
      interpretation: m.inventoryPercentile !== null
        ? m.inventoryPercentile < 20
          ? "Critically low inventories — strong physical tightness"
          : m.inventoryPercentile < 40
          ? "Below-average inventories — constructive for prices"
          : m.inventoryPercentile < 65
          ? "Inventories near the historical median — balanced"
          : "Elevated inventories — ample supply weighing on prices"
        : "Inventory data unavailable",
      quality: m.inventoryPercentile !== null ? "estimated" : "unavailable",
      tooltip: "Where current inventory sits relative to its 10-year seasonal history. Below 25th percentile = historically tight.",
    },
    {
      name: "Supply / Demand Balance",
      value: m.supplyDemandLabel,
      formatted: m.supplyDemandLabel
        ? m.supplyDemandLabel.charAt(0).toUpperCase() + m.supplyDemandLabel.slice(1)
        : "N/A",
      status: m.supplyDemandLabel === "deficit"
        ? "strong"
        : m.supplyDemandLabel === "balanced"
        ? "neutral"
        : "weak",
      interpretation: m.supplyDemandLabel === "deficit"
        ? "Demand exceeds supply — draws down inventories and supports prices"
        : m.supplyDemandLabel === "balanced"
        ? "Supply and demand roughly matched — price direction driven by sentiment"
        : "Supply exceeds demand — builds inventories and pressures prices",
      quality: m.supplyDemandLabel !== null ? "estimated" : "unavailable",
      tooltip: "Whether the physical commodity market is producing more or less than it consumes.",
    },
    {
      name: "Spare Capacity",
      value: m.spareCapacity,
      formatted: m.spareCapacity
        ? m.spareCapacity.charAt(0).toUpperCase() + m.spareCapacity.slice(1)
        : "N/A",
      status: m.spareCapacity === "low"
        ? "strong"
        : m.spareCapacity === "medium"
        ? "neutral"
        : "weak",
      interpretation: m.spareCapacity === "low"
        ? "Little spare capacity — market vulnerable to supply disruptions"
        : m.spareCapacity === "medium"
        ? "Moderate spare capacity — some buffer against demand shocks"
        : "Ample spare capacity — producers can easily offset disruptions",
      quality: m.spareCapacity !== null ? "estimated" : "unavailable",
      tooltip: "How much unused production capacity is available. Low spare capacity amplifies any supply disruption.",
    },
    {
      name: "Cost Curve Support",
      value: m.marginalCostEstimate,
      formatted: m.marginalCostEstimate !== null && m.spotPrice !== null
        ? `Spot ${fmtPct((m.spotPrice - m.marginalCostEstimate) / m.marginalCostEstimate)} vs marginal cost`
        : "N/A",
      status: m.spotPrice !== null && m.marginalCostEstimate !== null
        ? m.spotPrice > m.marginalCostEstimate * 1.1
          ? "strong"
          : m.spotPrice > m.marginalCostEstimate * 0.9
          ? "neutral"
          : "weak"
        : null,
      interpretation: m.spotPrice !== null && m.marginalCostEstimate !== null
        ? m.spotPrice > m.marginalCostEstimate
          ? `Spot ($${m.spotPrice.toFixed(0)}) above marginal cost ($${m.marginalCostEstimate.toFixed(0)}) — producers incentivised`
          : `Spot below marginal cost — high-cost producers losing money; supply curtailments likely`
        : "Marginal cost data unavailable",
      quality: m.marginalCostEstimate !== null ? "estimated" : "unavailable",
      tooltip: "Marginal cost of production is the floor for sustainable pricing. Prices below this trigger supply shutdowns.",
    },
  ];

  // Warning
  let warning: string | null = null;
  if (m.inventoryPercentile !== null && m.inventoryPercentile > 80) {
    warning = `Inventory at ${fmtPctile(m.inventoryPercentile)} — historically elevated, overhang likely limits upside`;
  } else if (m.spareCapacity === "high" && m.supplyDemandLabel === "surplus") {
    warning = "High spare capacity combined with surplus — market can absorb demand increases easily";
  } else if (m.disruptionRisk === "high") {
    warning = "High geopolitical or weather disruption risk — supply volatility elevated";
  } else if (m.productionGrowthYoy !== null && m.productionGrowthYoy > 0.05 &&
             (m.consumptionGrowthYoy ?? 0) < m.productionGrowthYoy) {
    warning = `Production growing ${fmtPct(m.productionGrowthYoy)} faster than consumption — inventory build likely`;
  }

  return {
    question: "Is the physical market tight or oversupplied?",
    answer,
    score,
    status,
    explanation,
    topMetrics,
    warning,
  };
}

// ── Valuation interpretation ──────────────────────────────────────────────────

export function interpretCommodityValuation(
  m: CommodityMetricsInput,
  score: number,
): QuestionScore {
  const status = getScoreStatus(score);

  let answer: string;
  if (score >= 72) {
    answer = m.futuresCurve === "backwardation"
      ? `${m.name} appears attractively valued — spot price is supported by backwardation and not stretched vs history.`
      : `${m.name} looks inexpensive relative to its historical range and cost of production.`;
  } else if (score >= 48) {
    answer = `Valuation is broadly fair — spot is in the middle of its historical range without extreme premium or discount.`;
  } else {
    answer = m.futuresCurve === "contango"
      ? `${m.name} looks expensive — contango structure and elevated historical percentile suggest limited near-term upside.`
      : `Spot price appears stretched relative to fundamentals and cost of production.`;
  }

  const parts: string[] = [];
  if (m.spotPercentile10yr !== null)
    parts.push(`10yr price percentile: ${fmtPctile(m.spotPercentile10yr)}.`);
  if (m.futuresCurve)
    parts.push(`Curve in ${m.futuresCurve}.`);
  const explanation = parts.join(" ") || answer;

  const topMetrics: MetricRow[] = [
    {
      name: "Futures Curve Shape",
      value: m.futuresCurve,
      formatted: m.futuresCurve
        ? m.futuresCurve.charAt(0).toUpperCase() + m.futuresCurve.slice(1)
          + (m.frontBackSpread !== null ? ` (${fmtPct(m.frontBackSpread)} spread)` : "")
        : "N/A",
      status: m.futuresCurve === "backwardation"
        ? "strong"
        : m.futuresCurve === "flat"
        ? "neutral"
        : "weak",
      interpretation: m.futuresCurve === "backwardation"
        ? "Backwardation: near-term contracts trade above longer-dated — physical market is tight, immediate demand dominates"
        : m.futuresCurve === "contango"
        ? "Contango: longer-dated contracts above spot — market expects future supply; holding physical commodity has a cost"
        : "Flat curve — market has no strong view on near vs future supply/demand",
      quality: m.futuresCurve !== null ? "estimated" : "unavailable",
      tooltip: "Backwardation (near > far) signals physical tightness and is generally bullish. Contango (far > near) signals ample supply.",
    },
    {
      name: "10-Year Price Percentile",
      value: m.spotPercentile10yr,
      formatted: m.spotPercentile10yr !== null
        ? `${fmtPctile(m.spotPercentile10yr)} of 10yr range`
        : "N/A",
      status: m.spotPercentile10yr !== null
        ? (m.spotPercentile10yr < 30 ? "strong" : m.spotPercentile10yr < 65 ? "neutral" : "weak")
        : null,
      interpretation: m.spotPercentile10yr !== null
        ? m.spotPercentile10yr < 25
          ? "Historically cheap — near cycle lows; strong value entry if fundamentals stabilise"
          : m.spotPercentile10yr < 50
          ? "Below-median historical price — reasonable entry from a long-term perspective"
          : m.spotPercentile10yr < 75
          ? "Above-median price — fair to mildly elevated; requires fundamental support"
          : "Near cycle highs — limited historical upside; elevated reversal risk"
        : "Historical price data unavailable",
      quality: m.spotPercentile10yr !== null ? "estimated" : "unavailable",
      tooltip: "Where current spot price sits within its 10-year range. Below 30th = historically cheap; above 75th = historically expensive.",
    },
    {
      name: "Spot vs Marginal Cost",
      value: m.spotVsMarginalCostPct,
      formatted: m.spotVsMarginalCostPct !== null
        ? `${fmtPct(m.spotVsMarginalCostPct)} premium to marginal cost`
        : "N/A",
      status: m.spotVsMarginalCostPct !== null
        ? (m.spotVsMarginalCostPct < 0.15 ? "strong" : m.spotVsMarginalCostPct < 0.50 ? "neutral" : "weak")
        : null,
      interpretation: m.spotVsMarginalCostPct !== null
        ? m.spotVsMarginalCostPct < 0
          ? "Trading below marginal cost — unsustainable; production cuts likely provide a floor"
          : m.spotVsMarginalCostPct < 0.20
          ? "Modest premium to cost of production — fair value zone"
          : m.spotVsMarginalCostPct < 0.60
          ? "Elevated premium — incentivises new supply; watch production response"
          : "Very large premium to cost — historically this attracts new supply and weighs on prices"
        : "Marginal cost estimate unavailable",
      quality: m.spotVsMarginalCostPct !== null ? "estimated" : "unavailable",
      tooltip: "How much spot price exceeds the marginal cost of production. Large premiums attract new supply; discounts force shutdowns.",
    },
  ];

  let warning: string | null = null;
  if (m.spotPercentile10yr !== null && m.spotPercentile10yr > 85) {
    warning = `Price at ${fmtPctile(m.spotPercentile10yr)} of 10yr range — historically elevated; mean reversion risk`;
  } else if (m.futuresCurve === "contango" && (m.frontBackSpread ?? 0) > 0.08) {
    warning = "Deep contango — rolling futures position incurs a significant negative carry cost";
  } else if (m.spotVsMarginalCostPct !== null && m.spotVsMarginalCostPct > 0.80) {
    warning = `Spot is ${fmtPct(m.spotVsMarginalCostPct)} above marginal cost — high enough to incentivise significant new supply`;
  }

  return {
    question: "Is the commodity cheap, fair, or expensive?",
    answer,
    score,
    status,
    explanation,
    topMetrics,
    warning,
  };
}

// ── Trend interpretation ──────────────────────────────────────────────────────

export function interpretCommodityTrend(
  m: CommodityMetricsInput,
  score: number,
): QuestionScore {
  const status = getScoreStatus(score);
  const hasData = m.perf3m !== null || m.perf12m !== null || m.ma200 !== null;

  let answer: string;
  if (!hasData) {
    answer = "Price momentum data not yet available.";
  } else if (score >= 68) {
    const crowded = m.cftcPositioningPct !== null && m.cftcPositioningPct > 80;
    answer = `Momentum is positive${m.perf3m !== null ? ` — up ${fmtPct(m.perf3m)} over 3 months` : ""}.${crowded ? " However, CFTC positioning is crowded — watch for reversal risk." : ""}`;
  } else if (score >= 48) {
    answer = `Trend is mixed — some positive momentum signals but not a clear directional setup.`;
  } else {
    answer = `Trend is negative — price action and macro backdrop are working against the position.`;
  }

  const parts: string[] = [];
  if (m.perf3m !== null) parts.push(`3M: ${fmtPct(m.perf3m)}`);
  if (m.perf12m !== null) parts.push(`12M: ${fmtPct(m.perf12m)}`);
  if (m.cftcPositioningPct !== null) parts.push(`CFTC: ${Math.round(m.cftcPositioningPct)}th pct`);
  if (m.dollarIndexTrend) parts.push(`USD ${m.dollarIndexTrend}`);
  const explanation = parts.join("  ·  ") || answer;

  const ma200pct = m.spotPrice && m.ma200 ? (m.spotPrice / m.ma200 - 1) : null;

  const topMetrics: MetricRow[] = [
    {
      name: "Price Momentum",
      value: m.perf3m,
      formatted: [
        m.perf1m !== null ? `1M ${fmtPct(m.perf1m)}` : null,
        m.perf3m !== null ? `3M ${fmtPct(m.perf3m)}` : null,
        m.perf12m !== null ? `12M ${fmtPct(m.perf12m)}` : null,
      ].filter(Boolean).join("  ·  ") || "Pending",
      changeDir: (m.perf3m ?? 0) > 0 ? "up" : "down",
      status: m.perf3m !== null
        ? (m.perf3m > 0.05 ? "strong" : m.perf3m > -0.05 ? "neutral" : "weak")
        : null,
      interpretation: m.perf3m !== null
        ? m.perf3m > 0.15
          ? "Strong upward momentum — trend is firmly in favor of bulls"
          : m.perf3m > 0.02
          ? "Mild positive drift — market slowly validating the thesis"
          : m.perf3m > -0.05
          ? "Sideways price action — no clear directional conviction"
          : "Negative momentum — sellers are in control"
        : "Price history unavailable",
      quality: m.perf3m !== null ? "live" : "unavailable",
      sparkline: m.priceSeries.slice(-20).map(p => p.price),
      tooltip: "1M, 3M, 12M price returns. Consistent positive momentum across timeframes is the strongest trend signal.",
    },
    {
      name: "CFTC Speculative Positioning",
      value: m.cftcPositioningPct,
      formatted: m.cftcPositioningPct !== null
        ? `${Math.round(m.cftcPositioningPct)}th percentile (net long)`
        : "N/A",
      status: m.cftcPositioningPct !== null
        ? (m.cftcPositioningPct > 80
          ? "weak"        // crowded = contrarian risk
          : m.cftcPositioningPct < 20
          ? "strong"      // crowded short = contrarian bullish
          : "neutral")
        : null,
      interpretation: m.cftcPositioningPct !== null
        ? m.cftcPositioningPct > 85
          ? "Extremely crowded net long — high reversal risk if sentiment shifts"
          : m.cftcPositioningPct > 70
          ? "Positioning is stretched long — momentum is positive but upside may be limited by crowding"
          : m.cftcPositioningPct > 30
          ? "Positioning at moderate levels — not a contrarian signal in either direction"
          : m.cftcPositioningPct < 15
          ? "Extremely crowded net short — contrarian bullish; short covering can drive sharp rallies"
          : "Positioning is light long or net short — upside potential from covering"
        : "CFTC positioning data unavailable",
      quality: m.cftcPositioningPct !== null ? "estimated" : "unavailable",
      tooltip: "CFTC Commitment of Traders data shows where speculative money is positioned. Crowded longs (>80th pct) are a contrarian warning.",
    },
    {
      name: "Macro Backdrop",
      value: null,
      formatted: [
        m.dollarIndexTrend ? `USD ${m.dollarIndexTrend}` : null,
        m.realYieldTrend ? `Real yields ${m.realYieldTrend}` : null,
        m.chinaPMI !== null ? `China PMI ${m.chinaPMI.toFixed(1)}` : null,
      ].filter(Boolean).join("  ·  ") || "N/A",
      status: (() => {
        let bullish = 0;
        if ((m.dollarIndexTrend as DollarTrend | null) === "weakening") bullish++;
        if (m.realYieldTrend === "falling" && m.category === "metals") bullish++;
        if (m.chinaPMI !== null && m.chinaPMI > 50) bullish++;
        if (m.inflationExpectationTrend === "rising") bullish++;
        return bullish >= 3 ? "strong" : bullish >= 1 ? "neutral" : "weak";
      })(),
      interpretation: (() => {
        const signals: string[] = [];
        const dollarTrend = m.dollarIndexTrend as DollarTrend | null;
        if (dollarTrend === "weakening") signals.push("Weakening dollar supports commodity prices");
        else if (dollarTrend === "strengthening") signals.push("Strengthening dollar creates headwinds");
        if (m.realYieldTrend === "falling" && m.category === "metals") signals.push("Falling real yields reduce opportunity cost of holding gold");
        if (m.chinaPMI !== null) signals.push(m.chinaPMI > 51 ? "China manufacturing expanding — supports industrial demand" : "China manufacturing soft — demand headwind for industrial commodities");
        return signals.length > 0 ? signals[0] : "Macro signals mixed — no strong directional driver";
      })(),
      quality: "estimated",
      tooltip: "Key macro drivers for commodity prices: dollar strength (inverse), real yields (inverse for gold), China PMI (industrial metals).",
    },
  ];

  let warning: string | null = null;
  if (m.cftcPositioningPct !== null && m.cftcPositioningPct > 85) {
    warning = `CFTC net long at ${Math.round(m.cftcPositioningPct)}th percentile — crowded positioning increases reversal risk`;
  } else if ((m.dollarIndexTrend as DollarTrend | null) === "strengthening" && m.perf3m !== null && m.perf3m < -0.05) {
    warning = "Negative momentum combined with dollar strength — macro and price action both headwinds";
  } else if (m.spotPrice && m.ma200 && m.spotPrice < m.ma200) {
    warning = `Spot is ${Math.abs((ma200pct ?? 0) * 100).toFixed(1)}% below 200d MA — long-term downtrend in effect`;
  }

  return {
    question: "Is the market moving in favor of or against this commodity?",
    answer,
    score,
    status,
    explanation,
    topMetrics,
    warning,
  };
}

// ── Contradiction + summary ───────────────────────────────────────────────────

export function buildCommodityContradictionWarning(
  health: number,
  valuation: number,
  trend: number,
  m: CommodityMetricsInput,
): string | null {
  if (health >= 68 && valuation <= 35) {
    return "Tight physical market, but spot price appears expensive relative to history — strong fundamentals already priced in.";
  }
  if (valuation >= 68 && trend <= 35) {
    return "Commodity looks inexpensive but price momentum is negative — value trap risk; wait for trend confirmation.";
  }
  if (trend >= 68 && m.cftcPositioningPct !== null && m.cftcPositioningPct > 82) {
    return "Positive momentum, but crowded long positioning increases reversal risk — new entrants late to the move.";
  }
  if (health >= 68 && m.futuresCurve === "contango") {
    return "Physical market is tight, but contango structure creates negative roll yield — futures investors pay to hold the position.";
  }
  if (health <= 35 && trend >= 68) {
    return "Price is rallying but physical fundamentals are weakening — momentum without supply/demand support.";
  }
  return null;
}

export function buildCommodityAnalystSummary(
  m: CommodityMetricsInput,
  health: QuestionScore,
  valuation: QuestionScore,
  trend: QuestionScore,
  overallScore: number,
  overallLabel: string,
): { summary: string; bull: string; bear: string; watch: string[] } {
  const tight = m.inventoryPercentile !== null && m.inventoryPercentile < 30;
  const expensive = m.spotPercentile10yr !== null && m.spotPercentile10yr > 70;
  const crowded = m.cftcPositioningPct !== null && m.cftcPositioningPct > 80;

  let summary: string;
  if (overallScore >= 68) {
    summary = `${m.name} presents a constructive setup. ${health.explanation} ${valuation.explanation} The risk/reward appears skewed to the upside given current physical market conditions.`;
  } else if (overallScore >= 48) {
    summary = `${m.name} offers a mixed picture. ${health.explanation} ${valuation.explanation} The setup requires patience — wait for clearer directional signals before adding exposure.`;
  } else {
    summary = `${m.name} faces headwinds across fundamentals and price. ${health.explanation} The overall setup suggests caution — better entry points are likely ahead.`;
  }

  const bull = tight
    ? `Inventory drawdowns continue — if the ${m.supplyDemandLabel ?? "tight"} physical balance persists, prices could re-rate sharply. Backwardation would steepen, attracting producer hedging and confirming the bull thesis.`
    : `Any demand acceleration or supply disruption could rapidly tighten the currently balanced market. A structural deficit would create a multi-year upcycle similar to prior commodity supercycles.`;

  const bear = expensive
    ? `Spot is in the ${Math.round(m.spotPercentile10yr ?? 70)}th percentile of its 10-year range — limited historical upside and mean reversion risk. ${crowded ? "Crowded long positioning amplifies any selloff." : "A demand disappointment could trigger a swift correction."}`
    : `If macro headwinds intensify (stronger dollar, rising real yields, China slowdown), demand could soften faster than supply responds, building inventories and pressuring prices below the cost of production.`;

  const watch: string[] = [
    "Weekly inventory reports for draw or build",
    "Futures curve shape — backwardation deepening or flipping to contango",
    "CFTC Commitment of Traders positioning trend",
  ];
  if (m.category === "metals" || m.category === "energy") watch.push("China PMI and industrial production data");
  if (m.category === "metals") watch.push("Real yield direction — key macro driver for precious metals");
  if (m.category === "energy") watch.push("OPEC+ production decisions and US shale rig count");

  return { summary, bull, bear, watch: watch.slice(0, 5) };
}
