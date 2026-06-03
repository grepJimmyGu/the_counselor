import type { OverlayKind, StrategyType } from "@/lib/contracts";

export interface TrackRecordMetric {
  label: string;
  value: string;
}

export interface OverlayMeta {
  kind: OverlayKind;
  label: string;
  tier: "core" | "advanced";
  /** One-sentence thesis — the bet this overlay makes. */
  idea: string;
  /** Multi-line execution description: signal + action + frequency. */
  execution: string;
  /** Example narrative with {ticker} placeholder replaced at render time. */
  exampleTemplate: string;
  /** Pair of key metrics shown in the track record section. */
  trackRecord: [TrackRecordMetric, TrackRecordMetric];
  /** From diagnosis — shown as a badge when holdings match. */
  fitLabel: string;
  /** Best market regime for this overlay. */
  bestRegime: string;
  /** Worst market regime for this overlay. */
  worstRegime: string;
  /** Strategy type literal for backend. */
  strategyType: StrategyType;
  /** Minimum holdings required. */
  minHoldings: number;
  /** Expandable: economic rationale. */
  whyItWorks: string;
  /** Expandable: detailed mechanic explanation. */
  mechanicDetail: string;
  /** Expandable: academic citations. */
  research: string;
  /** Expandable: common pitfalls. */
  watchFor: string;
  // ── Legacy fields (kept for backward compatibility) ──────────────────────
  /** @deprecated Use execution + idea instead. */
  shortDesc: string;
  /** @deprecated Use mechanicDetail instead. */
  mechanicSummary: string;
  /** @deprecated Use research instead. */
  researchSource: string;
  /** @deprecated Use trackRecord instead. */
  historicalEstimate: string;
  /** @deprecated Use fitLabel + bestRegime + worstRegime instead. */
  suitableFor: string;
}

export const OVERLAY_METADATA: Record<OverlayKind, OverlayMeta> = {
  defensive: {
    kind: "defensive",
    label: "Defensive",
    tier: "core",
    idea:
      "Falling knives are more dangerous than missed rallies. Step aside when a stock is hurting, re-enter when it's healed.",
    execution:
      "Sell a holding when its price drops below its 200-day moving average · moves to cash\nBuy back when price reclaims the MA\nChecks every position every day",
    exampleTemplate:
      "You hold {ticker} at ${price}. It slides to ${dropPrice} and breaks its 200-day MA. The overlay sells your {ticker} to cash. Two months later it climbs back above the MA at ${recoveryPrice} — the overlay buys back in. You missed the dip from ${dropPrice} to ${recoveryPrice}, but you also missed the crash from ${price} to ${dropPrice}. That's the trade.",
    trackRecord: [
      { label: "Worst loss", value: "−28% (vs −55% without it)" },
      { label: "Bull markets", value: "Keeps ~70% of the upside" },
    ],
    fitLabel: "Good fit for your portfolio",
    bestRegime: "Best in trending markets",
    worstRegime: "Weak in sideways chop",
    strategyType: "portfolio_defensive_overlay",
    minHoldings: 1,
    whyItWorks:
      "Markets trend. Academic research going back to 1900 shows that a simple trend-following rule — be in when the price is above a long-term moving average, be out when it's below — has reduced drawdowns and improved risk-adjusted returns across virtually every asset class tested. The economic rationale: investors are slow to process bad news. A stock that's fallen below its 200-day moving average tends to keep falling before the full story is priced in. Stepping aside early is cheaper than riding it all the way down.",
    mechanicDetail:
      "Each holding in your portfolio has its own independent trend signal. The overlay checks each holding's price vs its own 200-day MA, not the portfolio average. This matters: a tech selloff shouldn't kick you out of your utility stocks. Each name earns its place on its own merit. When a holding drops below its MA, only that holding's allocation goes to cash — the rest stay invested.",
    research:
      "Hurst, Ooi & Pedersen (2013): 'A Century of Evidence on Trend-Following Investing' — tested across 100+ years of global data spanning equities, bonds, commodities, and currencies. Found positive returns in every decade, with the strongest performance during extended bear markets (1930s, 1970s, 2000s, 2008). The strategy's Sharpe ratio was roughly double that of buy-and-hold over the full sample.",
    watchFor:
      "Choppy, range-bound markets are frustrating. A stock that oscillates around its 200-day MA will generate repeated small losses — buying back in above the MA only to get kicked out again days later. The overlay works best when trends are sustained; it underperforms in sideways chop. This is the price of admission: you accept small, frequent losses in flat markets in exchange for missing the big ones.",
    // Legacy
    shortDesc:
      "Holds each name only when above its 200-day trend; sells back to cash when it breaks down. Best when you want to limit downside.",
    mechanicSummary:
      "Each holding is checked independently: if its price is above its 200-day moving average, it stays in your portfolio at your target weight. If it falls below, that holding's allocation moves to cash until the trend recovers. No holding is sold because of what other holdings are doing — each name earns its place on its own.",
    researchSource:
      "Trend following is one of the oldest and most studied strategies in finance, with documented outperformance across 100+ years of market data (Hurst, Ooi & Pedersen, 2013).",
    historicalEstimate:
      "In backtests from 2000-2024, a 200-day MA filter on the S&P 500 reduced max drawdown from -55% to -28% while capturing ~70% of the upside.",
    suitableFor: "Portfolios with 5+ holdings where capital preservation matters.",
  },

  rotation: {
    kind: "rotation",
    label: "Rotation",
    tier: "core",
    idea:
      "Yesterday's winners tend to keep winning. Concentrate into what's working, drop what isn't, and don't get sentimental about either.",
    execution:
      "Once a month, rank your holdings by their 6-month return\nTop 3 get equal weight · the rest go to cash\nRepeat next month with fresh rankings",
    exampleTemplate:
      "Your portfolio has {ticker} (+42%), plus two others at +18% and +8%, and two that are down over the past 6 months. The overlay puts equal weight into the top 3 performers — the laggards sit in cash until their momentum improves. Next month {ticker} might cool off and a laggard might wake up. The overlay doesn't care — it follows the math.",
    trackRecord: [
      { label: "Added return", value: "+2–4%/yr vs buy-and-hold" },
      { label: "Biggest risk", value: "Whipsaws in choppy markets" },
    ],
    fitLabel: "Good fit for your diversified portfolio",
    bestRegime: "Best in trending markets",
    worstRegime: "Weak in choppy, range-bound markets",
    strategyType: "portfolio_rotation_overlay",
    minHoldings: 3,
    whyItWorks:
      "Cross-sectional momentum — buying recent winners and selling recent losers within the same universe — has been documented across stocks, bonds, commodities, and currencies for decades. The behavioral explanation: investors underreact to good news and overreact to bad news, creating a persistence effect that takes months to fully correct. A disciplined monthly rebalance exploits that before it fades.",
    mechanicDetail:
      "Every month, your holdings are ranked by their total return over the past 6 months (126 trading days). The top 3 get equal weight; the rest go to cash. There's no opinion, no 'but I like this stock' — the math decides. Next month, fresh returns produce fresh rankings. A holding that was #1 last month might be #5 this month and get dropped. The overlay doesn't care about loyalty.",
    research:
      "Jegadeesh & Titman (1993): the original paper that established momentum as a factor. Tested US stocks 1965-1989: buying past 6-month winners and holding for 6 months generated ~1% per month in excess returns. Subsequent research replicated this across 40+ countries. Moskowitz, Ooi & Pedersen (2012) documented time-series momentum across 58 liquid instruments spanning four asset classes.",
    watchFor:
      "Momentum reversals are violent when they happen. In a sharp sector rotation — like the March 2020 COVID crash when everything flipped simultaneously — the overlay can be caught holding last month's winners right as they become this month's losers. These events are rare but painful when they hit; they're the reason the strategy compounds over years, not months.",
    // Legacy
    shortDesc:
      "Rebalances monthly to the top-3 holdings by 6-month return. Best when you want to follow strength.",
    mechanicSummary:
      "Every month, each holding is ranked by its return over the past 6 months. The top 3 (by default) get equal weight; the rest go to cash. This means your portfolio is always concentrated in whatever is working right now.",
    researchSource:
      "Cross-sectional momentum has been documented across asset classes and geographies since Jegadeesh & Titman (1993). It remains one of the most robust factors in empirical finance.",
    historicalEstimate:
      "A top-3 rotation on a 10-stock equal-weight universe has historically added ~2-4% annualized return vs buy-and-hold, with similar or lower drawdowns in trending markets.",
    suitableFor:
      "Diversified portfolios (8+ holdings across sectors) where you're comfortable concentrating into 2-4 names.",
  },

  rebalance: {
    kind: "rebalance",
    label: "Rebalance",
    tier: "core",
    idea:
      "Your portfolio drifts over time — winners grow too big, losers shrink. A disciplined rebalance sells high and buys low without you having to decide when.",
    execution:
      "Monthly, each holding is reset back to your target weight\nOverweight → trimmed  |  Underweight → topped up\nNo market-timing · no cash-outs · just discipline",
    exampleTemplate:
      "You set {ticker} at 20% of your portfolio. After a strong quarter it's now 31%. The overlay sells ~11% of {ticker} and redistributes to your underweight holdings. Six months later if {ticker} has fallen back to 19%, the overlay buys more to bring it back to 20%. You're systematically selling high and buying low.",
    trackRecord: [
      { label: "Volatility", value: "Reduced 1–2pp vs never rebalancing" },
      { label: "Return", value: "Slight boost from harvesting swings" },
    ],
    fitLabel: "Good fit for any portfolio with target weights",
    bestRegime: "Best when you have clear allocation targets",
    worstRegime: "No bad regime — discipline, not timing",
    strategyType: "portfolio_rebalance_overlay",
    minHoldings: 2,
    whyItWorks:
      "Your portfolio drifts. A stock that outperforms grows from 20% to 30% of your book without you doing anything. That's not a free lunch — it's unintended concentration risk. Rebalancing forces you to trim winners (sell high) and add to laggards (buy low) on a fixed schedule. The benefit isn't from timing — it's from discipline. The math: selling overweights and buying underweights mechanically harvests mean-reversion in relative performance.",
    mechanicDetail:
      "On your chosen schedule (monthly, quarterly, annually), each holding is compared to its target weight. If a holding has grown beyond its target, the overlay trims it back. If a holding has shrunk below its target, the overlay buys more. There's no market signal — it's purely arithmetic. Cash is never used; every dollar stays invested.",
    research:
      "Vanguard (2019): 'Best Practices for Portfolio Rebalancing' — analyzed monthly, quarterly, and annual rebalancing across a 60/40 stock/bond portfolio from 1926-2018. Found that disciplined rebalancing added ~0.3-0.5% annualized return through volatility harvesting. More importantly, it kept risk close to the target level: an unrebalanced portfolio drifted from 60/40 to nearly 80/20 during long bull markets.",
    watchFor:
      "In a strong, sustained bull market where one sector dominates, rebalancing underperforms letting winners run. It also generates taxable events if you're not in a tax-advantaged account. The overlay is about discipline, not outperformance — it keeps your risk where you set it.",
    // Legacy
    shortDesc:
      "Periodically re-weights back to your target allocation. Best when you want discipline without timing.",
    mechanicSummary:
      "On a fixed schedule, your portfolio is re-weighted to match your target allocation. If a holding has grown too large, the overlay trims it back. There is no market-timing signal — just disciplined rebalancing.",
    researchSource:
      "Periodic rebalancing is a foundational portfolio management practice. Vanguard research (2019) found that rebalancing historically added ~0.3-0.5% annualized return through volatility harvesting.",
    historicalEstimate:
      "Monthly rebalancing on a 60/40 portfolio has historically reduced annual volatility by ~1-2 percentage points vs never rebalancing, with a small return benefit from selling high and buying low.",
    suitableFor:
      "Any portfolio where you have a clear target allocation you want to maintain.",
  },

  dual_momentum: {
    kind: "dual_momentum",
    label: "Dual Momentum",
    tier: "advanced",
    idea:
      "A stock needs to do two things to earn your money — be stronger than its peers AND be going up in absolute terms. If nothing passes both tests, cash wins.",
    execution:
      "Step 1: rank holdings by 6-month return (like Rotation)\nStep 2: each winner must also be up over the past 12 months\nPass both → invested  |  Fail either → cash\nIf nothing passes, 100% cash until conditions improve",
    exampleTemplate:
      "You hold {ticker} (+22%), plus another at +8%, and a third at −2%. {ticker} is ranked #1 (passes step 1) AND it's up 15% over 12 months (passes step 2) → invested. The +8% holding is ranked #2 but down 4% over 12 months (fails step 2) → cash. The −2% holding fails both → cash. Your portfolio is 100% {ticker}. If {ticker} also fails next month, it all goes to cash until something qualifies.",
    trackRecord: [
      { label: "Added return", value: "Matches Rotation in good years" },
      { label: "Drawdown", value: "~30% lower worst loss vs pure Rotation" },
    ],
    fitLabel: "Good fit for your diversified portfolio",
    bestRegime: "Best in strong trends",
    worstRegime: "Can sit in cash for months",
    strategyType: "portfolio_dual_momentum_overlay",
    minHoldings: 3,
    whyItWorks:
      "Relative momentum (ranking) tells you which holdings are better than others. Absolute momentum (trend) tells you whether any of them are actually worth holding at all. The combination is more powerful than either alone: during a broad market crash, everything fails the absolute momentum filter and the portfolio moves to cash instead of rotating into the 'least bad' loser. That's the edge — the cash option.",
    mechanicDetail:
      "Step 1: rank your holdings by 6-month return (same as Rotation) and pick the top N. Step 2: check each winner's 12-month return. If it's positive, you invest. If it's negative, that holding goes to cash — even if it 'won' the relative ranking. If no holding passes both tests, the portfolio is 100% cash. This matters most when everything is falling — instead of rotating into the smallest loser, you simply step aside.",
    research:
      "Gary Antonacci formalized dual momentum in 'Risk Premia Harvesting Through Dual Momentum' (2014) and the subsequent book 'Dual Momentum Investing' (2015). The strategy combined relative strength momentum (12-month lookback) with absolute momentum (a trend filter) across US equities, international equities, bonds, and real estate from 1974-2013. The dual momentum portfolio produced a Sharpe ratio of 1.11 vs 0.47 for the S&P 500, with max drawdown of −22% vs −51%.",
    watchFor:
      "Cash can feel like failure, but it's the strategy working as designed. During 2022, dual momentum strategies sat in cash for months while the S&P 500 fell 19% — the cash allocation was the best performer that year. The hard part is psychological: watching the market go up while you're in cash because nothing clears the absolute filter. This requires trusting the process over any single month's outcome.",
    // Legacy
    shortDesc:
      "Invest in your strongest holdings, but only if they're actually going up. When everything's falling, your portfolio moves to cash.",
    mechanicSummary:
      "This overlay asks two questions. First: which of my holdings have performed best recently? Second: is each of those winners actually going up? A holding must pass BOTH tests to stay invested. If nothing passes both, the portfolio sits in cash until conditions improve.",
    researchSource:
      "Gary Antonacci formalized dual momentum in 2014. Pavlovic, Korenak & Stakic (European Journal of Applied Economics, 2025) validated it for retail ETF portfolios.",
    historicalEstimate:
      "Adding an absolute momentum filter to a relative momentum rotation has historically reduced max drawdown by ~30% on average while capturing ~80% of the upside (2000-2024 backtests).",
    suitableFor:
      "Portfolios of 5+ holdings where you want to stay invested in good times but protect capital in broad downturns.",
  },

  defense_first: {
    kind: "defense_first",
    label: "Defense-First",
    tier: "advanced",
    idea:
      "Before you worry about which holding to sell, ask whether the whole ship is tilting. If most of your positions look weak, reduce everything — not just one.",
    execution:
      "Counts how many holdings are above their 200-day MA\n≥ half above → stay fully invested\n< half above → scale all positions to 50% until breadth recovers",
    exampleTemplate:
      "You hold 8 stocks including {ticker}. On a normal day, 6 of 8 are above their 200-day MA — you're fully invested. Next month, only 3 of 8 are above (breadth < 50%). The overlay cuts every position to 50% of its target weight. You're still in the market, but at half exposure. When breadth climbs back above 50%, exposure returns to 100%.",
    trackRecord: [
      { label: "Worst loss", value: "Roughly cut in half vs buy-and-hold" },
      { label: "Bull markets", value: "Sacrifices ~15% of the upside" },
    ],
    fitLabel: "Good fit for your diversified portfolio",
    bestRegime: "Best in broad downturns",
    worstRegime: "Less useful for single-stock crashes",
    strategyType: "portfolio_defense_first_overlay",
    minHoldings: 2,
    whyItWorks:
      "Most drawdown protection strategies look at individual holdings. Defense-First looks at the whole portfolio first. When a selloff is broad-based — multiple sectors falling simultaneously — individual stop-losses trigger one by one while you watch your portfolio bleed. A breadth signal catches the regime change earlier: 'most of my holdings look weak → reduce everything.' It's a circuit breaker, not a scalpel.",
    mechanicDetail:
      "Every day, the overlay checks: what fraction of your target holdings are above their 200-day MA? If 50% or more are above → you're fully invested at your target weights. If fewer than 50% are above → every position is scaled down to 50% of its target weight. The overlay doesn't pick which holdings to sell — it scales all of them equally, because breadth deterioration suggests the problem is systemic, not stock-specific. When breadth recovers above 50%, exposure returns to 100%.",
    research:
      "Thomas Carlson, 'Defense First: A Tactical Approach to Portfolio Protection' (SSRN, July 2025). Tested across 1971–2025: the strategy produced a Sharpe ratio of 0.70 vs 0.50 for the benchmark 60/40 portfolio. Max drawdown was −17.2% vs −29.5%. Critically, the strategy only reduced exposure in 23% of months — it spent most of its time fully invested, only stepping back when breadth was genuinely weak.",
    watchFor:
      "This overlay is a sledgehammer, not a scalpel. In a single-stock crash (accounting fraud, FDA rejection) that doesn't affect the rest of your portfolio, the breadth signal won't fire — you'd want Defensive for that. And in a slow, rolling bear market where leadership rotates but a majority of stocks stay above their MAs, the overlay may stay fully invested while individual names quietly deteriorate.",
    // Legacy
    shortDesc:
      "Check the market's health first. When most of your holdings look weak, automatically reduce your exposure until conditions improve.",
    mechanicSummary:
      "Instead of looking at each holding individually, this overlay looks at the whole portfolio first. It asks: what fraction of my holdings are currently above their 200-day moving average? If more than half are above, you stay fully invested. If fewer than half are above, the overlay scales down all positions to 50% exposure until breadth recovers.",
    researchSource:
      "Thomas Carlson's 'Defense First' paper (SSRN, July 2025) demonstrated that checking defensive conditions before committing capital produced a Sharpe ratio of 0.70 vs 0.50 for the benchmark.",
    historicalEstimate:
      "Reducing exposure when fewer than half of holdings are above their 200-day MA has historically cut portfolio drawdowns roughly in half while sacrificing only ~15% of bull market returns.",
    suitableFor:
      "Portfolios of 8+ holdings across at least 2-3 sectors. Larger portfolios give the breadth signal more statistical meaning.",
  },

  stability_tilt: {
    kind: "stability_tilt",
    label: "Stability Tilt",
    tier: "advanced",
    idea:
      "Not all returns are equal. A stock that drifts up 10% is a smoother ride than one that swings wildly to get there. Give the calm ones more weight.",
    execution:
      "Monthly, measure each holding's trailing volatility (63 days)\nHigher vol → smaller position  |  Lower vol → larger position\nAll holdings stay invested, just sized differently\nSingle holding capped at 25%",
    exampleTemplate:
      "You hold {ticker} (volatility 52%) alongside a calmer holding at 16% vol. {ticker} swings 3x more than the calmer one day to day. So the overlay gives the calmer holding roughly 3x the weight of {ticker}. Both stay in your portfolio — you don't sell anything. Next month if {ticker} calms down, its weight drifts back up.",
    trackRecord: [
      { label: "Volatility", value: "Reduced 20–30% vs equal-weight" },
      { label: "Return", value: "Similar long-term, less drama" },
    ],
    fitLabel: "Good fit for your mixed-volatility portfolio",
    bestRegime: "Best with mixed vol (tech + staples)",
    worstRegime: "Less useful when all holdings have similar vol",
    strategyType: "portfolio_stability_tilt_overlay",
    minHoldings: 2,
    whyItWorks:
      "The low-volatility anomaly: stocks with lower volatility have historically produced equal or better risk-adjusted returns than high-volatility stocks. The intuition: investors overpay for lottery-like stocks (high vol, chance of a huge payoff) and underpay for boring stocks (low vol, steady compounders). Weighting inversely to volatility systematically tilts toward the boring names that the market undervalues — without requiring you to pick which ones.",
    mechanicDetail:
      "Every month, each holding's trailing 63-day (one quarter) realized volatility is calculated from daily price changes. Holdings are weighted inversely — a stock with 15% annualized vol gets roughly 3x the weight of a stock with 45% vol. All holdings stay invested — nothing is sold. The only thing that changes is position size. A 25% cap prevents over-concentration in any single calm holding. The overlay re-weights monthly, so the tilts adapt as volatility patterns shift.",
    research:
      "Ang, Hodrick, Xing & Zhang (2006): 'The Cross-Section of Volatility and Expected Returns' — documented that stocks with high idiosyncratic volatility had abnormally low average returns, across US and international markets. The low-volatility anomaly has been replicated in 30+ countries. Lu, Rojas, Yeung & Convery's TrendFolios framework (arXiv, June 2025) validates inverse-volatility weighting as the position-sizing layer in a multi-signal retail system.",
    watchFor:
      "The tilt is always toward the calm — which means in a raging tech bull market, you'll be underweight the highest-returning, highest-vol names. You capture less of the euphoria. It's also most effective when your holdings have genuinely different volatility profiles (mixing tech with consumer staples); if everything in your portfolio swings similarly, the tilt has little to work with.",
    // Legacy
    shortDesc:
      "Give larger positions to your calmest holdings and smaller ones to your wildest — same stocks, less drama.",
    mechanicSummary:
      "Every month, each holding's recent volatility is measured. Holdings are weighted inversely to their volatility: a stock that's been swinging 15% a year gets roughly 3x the weight of one swinging 45% a year. All holdings stay in the portfolio — none are dropped — but position sizes shift toward the steadier names, capped at 25% each to avoid over-concentration.",
    researchSource:
      "The low-volatility anomaly was documented by Ang, Hodrick, Xing & Zhang (2006) and replicated across global markets. Lu, Rojas, Yeung & Convery's 'TrendFolios' framework (arXiv, June 2025) validates inverse-volatility weighting.",
    historicalEstimate:
      "Inverse-volatility weighting has historically reduced portfolio volatility by 20-30% compared to equal-weighting, with negligible difference in long-term returns.",
    suitableFor:
      "Portfolios with a mix of volatile and steady holdings (e.g., tech + consumer staples). The more volatility dispersion, the more the overlay matters.",
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
