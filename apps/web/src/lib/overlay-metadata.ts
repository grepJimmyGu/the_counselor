import type { OverlayKind } from "@/lib/contracts";

export interface OverlayMeta {
  kind: OverlayKind;
  label: string;
  shortDesc: string;
  mechanicSummary: string;
  researchSource: string;
  historicalEstimate: string;
  suitableFor: string;
  strategyType: string;
  tier: "core" | "advanced";
}

export const OVERLAY_METADATA: Record<OverlayKind, OverlayMeta> = {
  defensive: {
    kind: "defensive",
    label: "Defensive",
    shortDesc:
      "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside.",
    mechanicSummary:
      "Each holding is checked independently: if its price is above its 200-day moving average, it stays in your portfolio at your target weight. If it falls below, that holding's allocation moves to cash until the trend recovers. No holding is sold because of what other holdings are doing — each name earns its place on its own.",
    researchSource:
      "Trend following is one of the oldest and most studied strategies in finance, with documented outperformance across 100+ years of market data (Hurst, Ooi & Pedersen, 2013).",
    historicalEstimate:
      "In backtests from 2000-2024, a 200-day MA filter on the S&P 500 reduced max drawdown from -55% to -28% while capturing ~70% of the upside.",
    suitableFor: "Portfolios with 5+ holdings where capital preservation matters.",
    strategyType: "portfolio_defensive_overlay",
    tier: "core",
  },

  rotation: {
    kind: "rotation",
    label: "Rotation",
    shortDesc:
      "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength.",
    mechanicSummary:
      "Every month, each holding is ranked by its return over the past 6 months. The top 3 (by default) get equal weight; the rest go to cash. This means your portfolio is always concentrated in whatever is working right now — it follows strength and drops weakness automatically.",
    researchSource:
      "Cross-sectional momentum has been documented across asset classes and geographies since Jegadeesh & Titman (1993). It remains one of the most robust factors in empirical finance.",
    historicalEstimate:
      "A top-3 rotation on a 10-stock equal-weight universe has historically added ~2-4% annualized return vs buy-and-hold, with similar or lower drawdowns in trending markets.",
    suitableFor:
      "Diversified portfolios (8+ holdings across sectors) where you're comfortable concentrating into 2-4 names.",
    strategyType: "portfolio_rotation_overlay",
    tier: "core",
  },

  rebalance: {
    kind: "rebalance",
    label: "Rebalance",
    shortDesc:
      "Periodically re-weights back to your target allocation. Best when you want discipline without timing.",
    mechanicSummary:
      "On a fixed schedule (monthly, quarterly, or annually), your portfolio is re-weighted to match your target allocation. If a holding has grown to 30% of your portfolio when you wanted it at 20%, the overlay trims it back. There is no market-timing signal — just disciplined rebalancing.",
    researchSource:
      "Periodic rebalancing is a foundational portfolio management practice. Vanguard research (2019) found that rebalancing historically added ~0.3-0.5% annualized return through volatility harvesting.",
    historicalEstimate:
      "Monthly rebalancing on a 60/40 portfolio has historically reduced annual volatility by ~1-2 percentage points vs never rebalancing, with a small return benefit from selling high and buying low.",
    suitableFor:
      "Any portfolio where you have a clear target allocation you want to maintain.",
    strategyType: "portfolio_rebalance_overlay",
    tier: "core",
  },

  dual_momentum: {
    kind: "dual_momentum",
    label: "Dual Momentum",
    shortDesc:
      "Invest in your strongest holdings, but only if they're actually going up. When everything's falling, your portfolio moves to cash.",
    mechanicSummary:
      "This overlay asks two questions. First: which of my holdings have performed best recently? (Relative momentum — same as Rotation.) Second: is each of those winners actually going up? (Absolute momentum — a safety check.) A holding must pass BOTH tests to stay invested. If nothing passes both, the portfolio sits in cash until conditions improve.",
    researchSource:
      "Gary Antonacci formalized dual momentum in 2014. Pavlovic, Korenak & Stakic (European Journal of Applied Economics, 2025) validated it for retail ETF portfolios. AllocateSmartly independently tracks 90+ tactical strategies built on this framework.",
    historicalEstimate:
      "Adding an absolute momentum filter to a relative momentum rotation has historically reduced max drawdown by ~30% on average while capturing ~80% of the upside (2000-2024 backtests).",
    suitableFor:
      "Portfolios of 5+ holdings where you want to stay invested in good times but protect capital in broad downturns.",
    strategyType: "portfolio_dual_momentum_overlay",
    tier: "advanced",
  },

  defense_first: {
    kind: "defense_first",
    label: "Defense-First",
    shortDesc:
      "Check the market's health first. When most of your holdings look weak, automatically reduce your exposure until conditions improve.",
    mechanicSummary:
      "Instead of looking at each holding individually, this overlay looks at the whole portfolio first. It asks: what fraction of my holdings are currently above their 200-day moving average? If more than half are above (healthy breadth), you stay fully invested at your target weights. If fewer than half are above (weak breadth), the overlay scales down all positions to 50% exposure until breadth recovers. It's a circuit breaker, not a stock picker.",
    researchSource:
      "Thomas Carlson's 'Defense First' paper (SSRN, July 2025) demonstrated that checking defensive conditions before committing capital produced a Sharpe ratio of 0.70 vs 0.50 for the benchmark, with max drawdown of -17.2% vs -29.5% (1971-2025).",
    historicalEstimate:
      "Reducing exposure when fewer than half of holdings are above their 200-day MA has historically cut portfolio drawdowns roughly in half while sacrificing only ~15% of bull market returns.",
    suitableFor:
      "Portfolios of 8+ holdings across at least 2-3 sectors. Larger portfolios give the breadth signal more statistical meaning.",
    strategyType: "portfolio_defense_first_overlay",
    tier: "advanced",
  },

  stability_tilt: {
    kind: "stability_tilt",
    label: "Stability Tilt",
    shortDesc:
      "Give larger positions to your calmest holdings and smaller ones to your wildest — same stocks, less drama.",
    mechanicSummary:
      "Every month, each holding's recent volatility (how much its price has swung day-to-day over the past quarter) is measured. Holdings are weighted inversely to their volatility: a stock that's been swinging 15% a year gets roughly 3x the weight of one swinging 45% a year. All holdings stay in the portfolio — none are dropped — but position sizes shift toward the steadier names, capped at 25% each to avoid over-concentration.",
    researchSource:
      "The low-volatility anomaly was documented by Ang, Hodrick, Xing & Zhang (2006) and replicated across global markets. Lu, Rojas, Yeung & Convery's 'TrendFolios' framework (arXiv, June 2025) validates inverse-volatility weighting as the position-sizing layer in a multi-signal retail system.",
    historicalEstimate:
      "Inverse-volatility weighting has historically reduced portfolio volatility by 20-30% compared to equal-weighting, with negligible difference in long-term returns. The benefit is largest in portfolios mixing high- and low-volatility names.",
    suitableFor:
      "Portfolios with a mix of volatile and steady holdings (e.g., tech + consumer staples). The more volatility dispersion, the more the overlay matters.",
    strategyType: "portfolio_stability_tilt_overlay",
    tier: "advanced",
  },
};

export const OVERLAY_DISPLAY_ORDER: OverlayKind[] = [
  "defensive",
  "rotation",
  "rebalance",
  "dual_momentum",
  "defense_first",
  "stability_tilt",
];
