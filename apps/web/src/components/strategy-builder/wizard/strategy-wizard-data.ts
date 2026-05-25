/**
 * 5-question wizard data — direct TypeScript port of the JS data structures
 * from `Quant Strategy/framework/Retail_Strategy_Picker_Framework.html`
 * (lines 540–819 of the source HTML).
 *
 * Three exports:
 *   - `WIZARD_QUESTIONS` — the 5 question definitions (key, title, sub,
 *     options[]).
 *   - `WIZARD_STRATEGIES` — 20 strategy profiles, each with per-answer
 *     score maps + drawdown bucket + evidence tier + a `templateId`
 *     mapping to `researchTemplates` (null if no existing template
 *     matches — those strategies render with a "Coming soon" pill in
 *     the recommendation results and route to the custom flow).
 *   - `ANSWER_KEYS` — the 5 answer-key strings, for type narrowing.
 *
 * Keep this file in sync with the HTML source. The unit tests in
 * `strategy-wizard-recommend.test.ts` use canonical (answers → expected
 * top strategy) pairs from the HTML as oracles.
 */

export type GoalAnswer = "growth" | "defense" | "alpha" | "learn" | "hedge";
export type CadenceAnswer = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";
export type AssetAnswer =
  | "single_stock"
  | "single_commodity"
  | "stock_basket"
  | "sector_etf"
  | "broad_etf"
  | "pair";
export type BehaviorAnswer = "trend" | "mean" | "unknown";
export type DrawdownAnswer = "low" | "medium" | "high";

export interface WizardAnswers {
  goal: GoalAnswer | null;
  cadence: CadenceAnswer | null;
  asset: AssetAnswer | null;
  behavior: BehaviorAnswer | null;
  dd: DrawdownAnswer | null;
}

export interface WizardOption<V extends string = string> {
  val: V;
  label: string;
  desc: string;
}

export interface WizardQuestion {
  key: keyof WizardAnswers;
  title: string;
  sub: string;
  options: WizardOption[];
}

export const ANSWER_KEYS: ReadonlyArray<keyof WizardAnswers> = [
  "asset",
  "goal",
  "cadence",
  "behavior",
  "dd",
] as const;

export const WIZARD_QUESTIONS: WizardQuestion[] = [
  // Asset moved to position 1 per the rebuild spec — when the user
  // enters the wizard from a stock detail page, this question is
  // pre-answered, so it shows up as already-checked at the top.
  {
    key: "asset",
    title: "What's the shape of your asset?",
    sub: "This filters which strategies even make sense.",
    options: [
      { val: "single_stock", label: "A single stock", desc: "AAPL, NVDA, KO, etc. — one name you have a view on." },
      { val: "single_commodity", label: "A single commodity", desc: "Gold (GLD), oil (USO), copper, etc. — one commodity or its proxy ETF." },
      { val: "stock_basket", label: "A basket of stocks", desc: "S&P 500 names, sector members, or your own list of 10+ stocks." },
      { val: "sector_etf", label: "Sector ETFs", desc: "The 11 SPDR sector ETFs (XLE, XLF, XLK, …) or industry ETFs." },
      { val: "broad_etf", label: "A broad market ETF", desc: "SPY, QQQ, VTI — one diversified index ETF." },
      { val: "pair", label: "A pair of related assets", desc: "Two names that move together (KO/PEP, gold/silver, oil/gas, two banks)." },
    ],
  },
  {
    key: "goal",
    title: "What are you trying to do with this asset?",
    sub: "There are no wrong answers — pick the one closest to your intent.",
    options: [
      { val: "growth", label: "Grow money over years", desc: "Compounding wealth. Time horizon: months to years." },
      { val: "defense", label: "Protect from big drops", desc: "Worried about a 2008-style year. Accept lower returns for fewer scary moments." },
      { val: "alpha", label: "Beat the market", desc: "Better risk-adjusted returns than just buying SPY." },
      { val: "learn", label: "Trade actively and learn", desc: "Enjoy watching markets; want hands-on signals to act on." },
      { val: "hedge", label: "Hedge an existing position", desc: "Already own something; want a paired/neutral strategy to offset risk." },
    ],
  },
  {
    key: "cadence",
    title: "How often will you actually check the strategy?",
    sub: "Be honest. A strategy run at the wrong cadence creates noise.",
    options: [
      { val: "daily", label: "Every day", desc: "Active trader; checks before and after market open." },
      { val: "weekly", label: "Once a week", desc: "Weekend or Monday check-in. Most retail prosumers." },
      { val: "monthly", label: "Once a month", desc: "Calendar-driven rebalance. Low effort." },
      { val: "quarterly", label: "Once a quarter", desc: "Slow, deliberate. Earnings-season aligned." },
      { val: "yearly", label: "Once a year", desc: "Set and forget for tax-advantaged accounts." },
    ],
  },
  {
    key: "behavior",
    title: "How does your asset usually behave?",
    sub: "Pick the closest. If unsure, use the third option — it's safe.",
    options: [
      { val: "trend", label: "Strongly trending", desc: "Stretches of one direction (commodities in supply shocks, growth stocks in bull cycles, gold in inflation)." },
      { val: "mean", label: "Range-bound / mean-reverts", desc: "Bounces between levels (utilities, mature defensives, bonds when rates are stable)." },
      { val: "unknown", label: "Mixed / I don't know", desc: "It does both, or you haven't watched it long enough. Default to balanced strategies." },
    ],
  },
  {
    key: "dd",
    title: "How big a temporary drop can you sit through without panicking?",
    sub: "Honest answer beats aspirational answer. This filters high-drawdown strategies.",
    options: [
      { val: "low", label: "Under 15% (sleep-easy mode)", desc: "You'll quit a strategy if it goes −20%. You want defensive templates." },
      { val: "medium", label: "Up to 25%", desc: "You can stomach typical bear-market pain if you understand the strategy." },
      { val: "high", label: "40%+ for higher returns", desc: "Playing for long-run compounding; won't quit during a momentum crash." },
    ],
  },
];

// ── Strategy profiles ───────────────────────────────────────────────────────
// Score maps: 0 = poor / disqualified, 1 = ok, 2 = good. The scoring function
// in `strategy-wizard-recommend.ts` weighs asset = 2x, behavior = 1.5x,
// goal + cadence = 1x. Hard disqualifiers in the scoring function:
//   - `requiresFundamentals: true` + asset in (single_commodity, pair)
//   - dd: 'low' + drawdown: 'high'
//   - asset[answer] === 0 (asset incompatible)

export interface WizardStrategy {
  slug: string;
  name: string;
  blurb: string;
  goals: Record<GoalAnswer, number>;
  cadence: Record<CadenceAnswer, number>;
  asset: Record<AssetAnswer, number>;
  behavior: Record<BehaviorAnswer, number>;
  drawdown: "low" | "medium" | "high";
  evidence: "A" | "B" | "C";
  cap: "Retail" | "Prosumer";
  example: string;
  requiresFundamentals?: boolean;
  /** Slug of the matching `researchTemplate` entry, or null if no
   *  ready template exists yet — those recommendations render with
   *  a "Coming soon" pill and skip the template-brief flow. */
  templateId: string | null;
}

export const WIZARD_STRATEGIES: WizardStrategy[] = [
  {
    slug: "moving_average_filter",
    name: "Moving Average Filter",
    blurb: "Hold the asset only when its price is above a long moving average. The rest of the time, sit in cash. Avoids most of the pain of bear markets.",
    goals: { growth: 2, defense: 2, alpha: 1, learn: 2, hedge: 0 },
    cadence: { daily: 1, weekly: 2, monthly: 2, quarterly: 1, yearly: 0 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 1, sector_etf: 1, broad_etf: 2, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "low",
    evidence: "A",
    cap: "Retail",
    example: "SPY: hold when price > 200-day MA, else cash. Sidestepped most of 2008 and 2022.",
    templateId: "trend-following",
  },
  {
    slug: "moving_average_crossover",
    name: "Moving Average Crossover",
    blurb: "The classic SMA-50 vs SMA-200 trend rule. Long when fast MA is above slow MA, else cash.",
    goals: { growth: 2, defense: 1, alpha: 1, learn: 2, hedge: 0 },
    cadence: { daily: 1, weekly: 2, monthly: 2, quarterly: 1, yearly: 0 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 1, sector_etf: 1, broad_etf: 2, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Retail",
    example: "Gold (GLD): long when SMA(50) > SMA(200). Caught the 2019–2020 rally.",
    templateId: "trend-following",
  },
  {
    slug: "time_series_momentum",
    name: "Time-Series Momentum",
    blurb: "Long when the asset's own past 12-month return is positive. Trend at its simplest.",
    goals: { growth: 2, defense: 1, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 0, weekly: 1, monthly: 2, quarterly: 2, yearly: 1 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 1, sector_etf: 2, broad_etf: 2, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Retail",
    example: "Hold oil (USO) only when its trailing 12-month return is > 0. Otherwise cash.",
    templateId: "time-series-momentum",
  },
  {
    slug: "cross_sectional_momentum",
    name: "Cross-Sectional Momentum (12-1)",
    blurb: "Rank a basket of stocks by their 12-month return (skip last month). Hold the top decile. Replicated for 30+ years.",
    goals: { growth: 2, defense: 0, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 0, weekly: 1, monthly: 2, quarterly: 1, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 1, broad_etf: 0, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "high",
    evidence: "A",
    cap: "Prosumer",
    example: "Universe: S&P 500. Each month, hold the top 50 names by 12-month return (skip last month).",
    templateId: "cross-sectional-momentum",
  },
  {
    slug: "sector_rotation",
    name: "Sector Rotation (SPDR)",
    blurb: "Each month, hold the top-3 of 11 sector ETFs by their 6-month return. Retail favorite — strong evidence, modest turnover.",
    goals: { growth: 2, defense: 1, alpha: 2, learn: 2, hedge: 0 },
    cadence: { daily: 0, weekly: 1, monthly: 2, quarterly: 1, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 0, sector_etf: 2, broad_etf: 0, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "medium",
    evidence: "B",
    cap: "Retail",
    example: "XLE/XLF/XLK/XLV/XLY/XLP/XLU/XLI/XLB/XLRE/XLC — hold top 3 each month.",
    templateId: "sector-rotation-spdr",
  },
  {
    slug: "dual_momentum",
    name: "Dual Momentum (Antonacci)",
    blurb: "Combines cross-sectional and absolute momentum: pick top of a small set by 12-month return; if negative, go to bonds/cash.",
    goals: { growth: 2, defense: 2, alpha: 1, learn: 2, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 2, quarterly: 1, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 1, sector_etf: 2, broad_etf: 1, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "low",
    evidence: "B",
    cap: "Retail",
    example: "Pick best of (SPY, EFA, AGG) by 12-month return. If best is negative, go 100% to BIL.",
    templateId: "dual-momentum",
  },
  {
    slug: "low_volatility",
    name: "Low-Volatility Tilt",
    blurb: "Hold a basket of the lowest-volatility names in a universe. The defensive premium — lower risk has historically not meant lower return.",
    goals: { growth: 1, defense: 2, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 1, quarterly: 2, yearly: 1 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 1, broad_etf: 0, pair: 0 },
    behavior: { trend: 1, mean: 1, unknown: 2 },
    drawdown: "low",
    evidence: "A",
    cap: "Retail",
    example: "S&P 500 universe. Hold the 50 stocks with the lowest 252-day volatility, rebalance quarterly.",
    templateId: "low-volatility",
  },
  {
    slug: "rsi_mean_reversion",
    name: "RSI Mean Reversion",
    blurb: "Buy when RSI(14) < 30, sell when RSI > 60. A classic retail mean-reversion swing trade.",
    goals: { growth: 1, defense: 0, alpha: 1, learn: 2, hedge: 0 },
    cadence: { daily: 2, weekly: 2, monthly: 0, quarterly: 0, yearly: 0 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 0, sector_etf: 1, broad_etf: 1, pair: 0 },
    behavior: { trend: 0, mean: 2, unknown: 1 },
    drawdown: "medium",
    evidence: "B",
    cap: "Retail",
    example: "Hold KO when its RSI(14) drops below 30; exit when RSI crosses above 60.",
    templateId: "bollinger-mean-reversion",
  },
  {
    slug: "bollinger_mean_reversion",
    name: "Bollinger Mean Reversion",
    blurb: "Buy when price drops below the lower Bollinger band (mean − 2σ), exit when it returns to the mean. Mirror of RSI for traders who prefer price levels.",
    goals: { growth: 1, defense: 0, alpha: 1, learn: 2, hedge: 0 },
    cadence: { daily: 2, weekly: 2, monthly: 0, quarterly: 0, yearly: 0 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 0, sector_etf: 1, broad_etf: 1, pair: 0 },
    behavior: { trend: 0, mean: 2, unknown: 1 },
    drawdown: "medium",
    evidence: "B",
    cap: "Retail",
    example: "Copper futures: buy on close < (SMA(20) − 2σ), exit on close > SMA(20).",
    templateId: "bollinger-mean-reversion",
  },
  {
    slug: "breakout",
    name: "Breakout (Donchian)",
    blurb: "Long when price closes above its N-day high. Exit when it closes below its M-day low. The Turtle Traders' rule.",
    goals: { growth: 2, defense: 0, alpha: 2, learn: 2, hedge: 0 },
    cadence: { daily: 1, weekly: 2, monthly: 1, quarterly: 0, yearly: 0 },
    asset: { single_stock: 2, single_commodity: 2, stock_basket: 1, sector_etf: 1, broad_etf: 1, pair: 0 },
    behavior: { trend: 2, mean: 0, unknown: 1 },
    drawdown: "high",
    evidence: "A",
    cap: "Retail",
    example: "GLD: long on 60-day high breakout, exit on 20-day low.",
    templateId: null, // No 'breakout' researchTemplate yet
  },
  {
    slug: "pairs_trading",
    name: "Pairs Trading (Z-score)",
    blurb: "Long the cheaper of a cointegrated pair, exit when the spread normalizes. The market-neutral retail strategy.",
    goals: { growth: 1, defense: 1, alpha: 2, learn: 2, hedge: 2 },
    cadence: { daily: 2, weekly: 2, monthly: 0, quarterly: 0, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 0, sector_etf: 0, broad_etf: 0, pair: 2 },
    behavior: { trend: 0, mean: 2, unknown: 1 },
    drawdown: "medium",
    evidence: "B",
    cap: "Prosumer",
    example: "KO/PEP: long KO when spread z-score < −2; exit at z = 0; stop at z < −3.5.",
    templateId: "pairs-trading-long-only",
  },
  {
    slug: "short_term_reversal",
    name: "Short-Term Reversal (1-week)",
    blurb: "Buy last-week losers, sell next week. High turnover; only profitable with low costs.",
    goals: { growth: 1, defense: 0, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 2, weekly: 2, monthly: 0, quarterly: 0, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 0, mean: 2, unknown: 0 },
    drawdown: "medium",
    evidence: "B",
    cap: "Prosumer",
    example: "Each Monday, buy bottom 10 names by previous week's return. Hold for 5 days.",
    templateId: "short-term-reversal",
  },
  {
    slug: "static_allocation",
    name: "Static Allocation",
    blurb: "Fixed weights, rebalance once a year (e.g. 60/40 SPY/AGG). The benchmark every active strategy is measured against.",
    goals: { growth: 2, defense: 2, alpha: 0, learn: 0, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 0, quarterly: 1, yearly: 2 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 1, sector_etf: 1, broad_etf: 2, pair: 0 },
    behavior: { trend: 1, mean: 1, unknown: 2 },
    drawdown: "medium",
    evidence: "A",
    cap: "Retail",
    example: "Hold 60% VTI / 40% BND; rebalance once a year.",
    templateId: null,
  },
  {
    slug: "multi_factor_composite",
    name: "Multi-Factor Composite",
    blurb: "Combines value, momentum, quality, and low-vol scores into one rank. The defensible Pro template for long-only equity alpha.",
    goals: { growth: 2, defense: 1, alpha: 2, learn: 0, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 1, quarterly: 2, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 1, mean: 1, unknown: 2 },
    drawdown: "medium",
    evidence: "A",
    cap: "Prosumer",
    requiresFundamentals: true,
    example: "S&P 500 universe. Z-score Value/Momentum/Quality/LowVol; average; hold top decile.",
    templateId: "multi-factor-composite",
  },
  {
    slug: "quality_piotroski",
    name: "Quality (Piotroski F-Score)",
    blurb: "Hold stocks with high financial-strength scores (F-Score ≥ 8). Best on small-cap value, but works broadly.",
    goals: { growth: 2, defense: 1, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 0, quarterly: 2, yearly: 1 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 0, mean: 1, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Prosumer",
    requiresFundamentals: true,
    example: "Universe: small-cap value. Hold names with F-Score ≥ 8; rebalance quarterly.",
    templateId: "quality-piotroski-cs",
  },
  {
    slug: "value_composite",
    name: "Value Composite",
    blurb: "Z-score Free-Cash-Flow yield + Book/Market + EBITDA/EV; hold the top decile. Modern multi-metric value.",
    goals: { growth: 2, defense: 1, alpha: 2, learn: 0, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 1, quarterly: 2, yearly: 0 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 0, mean: 1, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Prosumer",
    requiresFundamentals: true,
    example: "S&P 1500 universe. Quarterly rebalance into top-decile of value composite.",
    templateId: "value-composite-cs",
  },
  {
    slug: "buyback_yield",
    name: "Buyback Yield",
    blurb: "Hold companies in the top decile of net share repurchases. Particularly strong when combined with value.",
    goals: { growth: 2, defense: 0, alpha: 2, learn: 0, hedge: 0 },
    cadence: { daily: 0, weekly: 0, monthly: 0, quarterly: 2, yearly: 1 },
    asset: { single_stock: 0, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 1, mean: 1, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Prosumer",
    requiresFundamentals: true,
    example: "S&P 500 universe. Quarterly rebalance into the top 50 by trailing 12-month net buyback yield.",
    templateId: null,
  },
  {
    slug: "pead_drift",
    name: "Post-Earnings Drift (PEAD)",
    blurb: "After an earnings beat, the stock keeps drifting up for ~60 trading days. Hold positive-surprise names through that drift.",
    goals: { growth: 1, defense: 0, alpha: 2, learn: 1, hedge: 0 },
    cadence: { daily: 1, weekly: 2, monthly: 1, quarterly: 0, yearly: 0 },
    asset: { single_stock: 1, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 1, mean: 0, unknown: 1 },
    drawdown: "medium",
    evidence: "A",
    cap: "Prosumer",
    requiresFundamentals: true,
    example: "Each day, hold any name whose latest earnings SUE is top-decile, for 60 trading days.",
    templateId: "pead-drift-cs",
  },
  {
    slug: "news_sentiment_momentum",
    name: "News Sentiment Momentum",
    blurb: "Buy names with the most positive 30-day news sentiment. Mixed evidence — best combined with a price-trend co-signal.",
    goals: { growth: 1, defense: 0, alpha: 1, learn: 1, hedge: 0 },
    cadence: { daily: 1, weekly: 2, monthly: 1, quarterly: 0, yearly: 0 },
    asset: { single_stock: 1, single_commodity: 0, stock_basket: 2, sector_etf: 0, broad_etf: 0, pair: 0 },
    behavior: { trend: 1, mean: 0, unknown: 1 },
    drawdown: "medium",
    evidence: "C",
    cap: "Prosumer",
    example: "S&P 500 universe. Hold top decile of 30-day FinBERT sentiment; combine with 200-day MA filter.",
    templateId: "news-sentiment-momentum",
  },
];
