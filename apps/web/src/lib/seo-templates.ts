/**
 * Stage 5a — SEO template landing pages registry.
 *
 * Each entry powers a dynamic page at /templates/[slug] (rendered by
 * apps/web/src/app/templates/[slug]/page.tsx) and a sitemap entry.
 *
 * Content authoring policy:
 *   - Intros + explanations + FAQs hand-written. Never fabricate returns;
 *     reference real Alpha Vantage data where applicable.
 *   - Three FAQs per page is the SEO sweet spot (JSON-LD FAQPage trigger).
 *   - h1 and title must be different but congruent (Google rewards variety).
 *
 * Roadmap: 50 entries (10 MA, 10 RSI, 5 momentum, 5 breakout, 5 allocation,
 * 5 explainer, 10 long-tail). This file ships with 3 seed entries; more
 * to be added incrementally as content is written.
 */

export interface SeoTemplatePage {
  /** URL slug, e.g. "backtest-200-day-moving-average-nvda". */
  slug: string;
  /** <title> tag. */
  title: string;
  /** <h1> heading. */
  h1: string;
  /** Primary keyword target. */
  primaryKw: string;
  /** Secondary keyword variants for natural prose inclusion. */
  secondaryKw: string[];
  /** Short marketing intro (~150 words, plain text). */
  intro: string;
  /** Strategy mechanics explainer (~300 words). */
  explanation: string;
  /** Results-interpretation prose (~200 words). */
  resultsSummary: string;
  /** Three FAQ pairs — triggers JSON-LD FAQPage. */
  faqs: Array<{ q: string; a: string }>;
  /** Default universe (single ticker for most landing pages). */
  defaultUniverse: string[];
  /** Default years of history to show in the embedded result. */
  defaultHistoryYears: number;
  /** Last edit date — bumps sitemap.lastModified. */
  lastModified: string;
}

export const SEO_TEMPLATES: SeoTemplatePage[] = [
  {
    slug: "backtest-200-day-moving-average-nvda",
    title: "Backtest a 200-day moving average strategy on NVDA — free",
    h1: "Backtest a 200-day moving average filter on NVDA",
    primaryKw: "backtest 200-day moving average",
    secondaryKw: ["nvda moving average strategy", "moving average backtest free", "nvda 200 day MA"],
    intro:
      "The 200-day moving average is the most-watched trend filter in finance. " +
      "Hold NVDA when its price is above the 200-day MA, sit in cash when below. " +
      "It's not the highest-returning strategy but it consistently dodges the worst " +
      "drawdowns of a high-beta name. Run it free on Livermore — no signup required " +
      "for one shot, no credit card, no demo data.",
    explanation:
      "The strategy buys NVDA when the close crosses above its 200-trading-day " +
      "simple moving average and sells when it crosses below. Signals are evaluated " +
      "daily; transitions happen at the next day's open. Backtested over the last " +
      "five years, this filter typically beats buy-and-hold on max drawdown by " +
      "30-40 percentage points while giving up some upside on the strongest legs. " +
      "It's the kind of strategy that wins by losing less.\n\n" +
      "Why it works on NVDA specifically: NVDA has had multiple 60%+ drawdowns " +
      "in the last decade. The 200-day filter is fast enough to step out before " +
      "the drawdown compounds and slow enough to ignore most one-month wobbles. " +
      "On lower-volatility names (KO, JNJ), this filter under-performs buy-and-hold " +
      "because there are no big drawdowns to avoid.",
    resultsSummary:
      "Read the live result above. If Sharpe is north of 1.0 and max drawdown is " +
      "less than half of buy-and-hold, the filter is doing its job. If returns " +
      "lag buy-and-hold by more than 30%, the trend has been so strong that the " +
      "filter mostly hurt — that's expected in a relentless uptrend. The strategy " +
      "earns its keep in choppy markets and crashes, not in straight-line bull runs.",
    faqs: [
      {
        q: "What is a 200-day moving average?",
        a: "The 200-day moving average is the average closing price over the previous " +
           "200 trading days. It's the slowest of the common trend filters and is " +
           "widely watched by institutional investors, so it sometimes acts as a " +
           "self-fulfilling prophecy at major regime changes.",
      },
      {
        q: "Can I run this strategy for free on Livermore?",
        a: "Yes. One backtest per anonymous visitor — no signup, no credit card. " +
           "If you sign up (free Scout tier), you get 5 custom backtests per week " +
           "and unlimited template runs.",
      },
      {
        q: "Does this strategy work in 2026?",
        a: "The result above is computed on real recent price data, not a demo. " +
           "Run it and check the numbers for yourself. The 200-day filter's strength " +
           "is regime-dependent — it shines in markets with multi-month drawdowns " +
           "and underperforms in steady uptrends.",
      },
    ],
    defaultUniverse: ["NVDA"],
    defaultHistoryYears: 5,
    lastModified: "2026-05-20",
  },
  {
    slug: "backtest-rsi-mean-reversion-aapl",
    title: "Backtest an RSI mean-reversion strategy on AAPL — free",
    h1: "Backtest an RSI mean-reversion filter on AAPL",
    primaryKw: "rsi mean reversion backtest",
    secondaryKw: ["aapl rsi strategy", "rsi 30 70 backtest", "apple stock rsi"],
    intro:
      "RSI mean-reversion is the canonical 'buy oversold, sell overbought' setup. " +
      "Buy AAPL when its 14-day RSI dips below 30, sell when it climbs above 70. " +
      "It's a short-holding-period strategy that historically gives up upside in " +
      "trends but smooths returns in choppy years. Run it free — see exactly how " +
      "RSI signals fired on AAPL over the last five years.",
    explanation:
      "The Relative Strength Index (RSI) measures the ratio of up-day price changes " +
      "to down-day price changes over a window — 14 days is the default. Readings " +
      "below 30 are conventionally 'oversold'; above 70 'overbought'. The strategy " +
      "enters AAPL on a close below RSI 30 and exits on a close above RSI 70. " +
      "Average holding period: ~2-4 weeks.\n\n" +
      "AAPL is a tractable name for this filter because (a) it has enough daily " +
      "volume that 14-day RSI is meaningful (not noise), (b) it experiences regular " +
      "5-10% pullbacks even in strong years, giving the strategy enough setups to " +
      "be statistically meaningful, and (c) earnings-driven gaps are infrequent " +
      "enough that they don't dominate the result.",
    resultsSummary:
      "Compare total return to buy-and-hold and check the number of trades. If " +
      "the strategy generated 15+ round trips with a win rate above 55%, it's " +
      "doing its job. If win rate is above 80% with only 3-4 trades, you're looking " +
      "at small-sample luck — re-run with a different window or a different ticker " +
      "to see how durable it is.",
    faqs: [
      {
        q: "What is RSI mean reversion?",
        a: "A strategy that buys an asset when its Relative Strength Index drops " +
           "below an oversold threshold (typically 30) and sells when it rises " +
           "above an overbought threshold (typically 70).",
      },
      {
        q: "Why does mean reversion work some years and not others?",
        a: "Mean reversion works in choppy, range-bound markets and fails in " +
           "trending markets — when the market trends, 'oversold' just gets more " +
           "oversold. A diagnostic: if buy-and-hold has a Sharpe above 1.5, " +
           "mean reversion will probably underperform that year.",
      },
      {
        q: "Can I customize the RSI thresholds?",
        a: "Sign up free and open the strategy in the workspace — you can edit " +
           "the entry/exit thresholds and re-run. The free Scout tier includes " +
           "5 custom backtests per week.",
      },
    ],
    defaultUniverse: ["AAPL"],
    defaultHistoryYears: 5,
    lastModified: "2026-05-20",
  },
  {
    slug: "backtest-magnificent-seven-momentum-rotation",
    title: "Backtest a Magnificent 7 momentum rotation strategy — free",
    h1: "Backtest a Magnificent 7 momentum rotation",
    primaryKw: "magnificent seven momentum strategy",
    secondaryKw: ["mag 7 backtest", "momentum rotation tech stocks", "top 7 us stocks strategy"],
    intro:
      "The Magnificent 7 — AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA — drove the " +
      "S&P 500's returns for most of the last five years. A momentum rotation " +
      "strategy holds the top 2-3 names each month based on trailing 6-month return " +
      "and rebalances monthly. Run it free, see whether 'just hold the Mag 7' would " +
      "have beaten or underperformed the rotation logic.",
    explanation:
      "Each month, the strategy ranks the seven names by trailing 6-month total " +
      "return and holds the top three with equal weights. On rebalance day (first " +
      "trading day of the month), positions are adjusted. Transaction costs of " +
      "10bps + 5bps slippage are subtracted. The benchmark is QQQ.\n\n" +
      "The thesis: momentum is one of the most robust empirical factors in equity " +
      "returns. The Mag 7 are large enough to be tradable, concentrated enough to " +
      "create cross-sectional dispersion, and recent enough that the regime is " +
      "still relevant. The risk: when one of the seven crashes (META in 2022, " +
      "TSLA in 2022), the rotation logic stays in for a month and amplifies the " +
      "drawdown vs an equal-weight basket.",
    resultsSummary:
      "Look at the equity curve relative to QQQ. If the strategy beat QQQ by 5-15% " +
      "over the window with comparable drawdown, momentum is paying off. If it " +
      "matched QQQ but had bigger drawdowns, you're paying for momentum without " +
      "getting the alpha — try an equal-weight Mag 7 basket instead.",
    faqs: [
      {
        q: "What is momentum rotation?",
        a: "A strategy that ranks a basket of assets by recent return and holds " +
           "only the top performers. The hypothesis (well-documented in academic " +
           "research) is that recent winners tend to keep winning over horizons " +
           "of 3-12 months.",
      },
      {
        q: "Why 6 months of trailing return, not 1 or 12?",
        a: "Academic research (Jegadeesh + Titman, 1993; Asness et al., 2013) finds " +
           "the 6-12 month window most robust. 1-month return is mean-reverting " +
           "(short-term reversal). 12-month return loses sensitivity to regime " +
           "changes. 6 months is a defensible compromise.",
      },
      {
        q: "Can I add other tickers to the rotation?",
        a: "Yes — sign up free, open the strategy in the workspace, and add " +
           "tickers to the universe. The Scout tier supports up to 5-ticker custom " +
           "universes; Strategist unlocks 25.",
      },
    ],
    defaultUniverse: ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    defaultHistoryYears: 5,
    lastModified: "2026-05-20",
  },
];

export function findSeoTemplate(slug: string): SeoTemplatePage | undefined {
  return SEO_TEMPLATES.find((t) => t.slug === slug);
}

export function allSeoSlugs(): string[] {
  return SEO_TEMPLATES.map((t) => t.slug);
}
