/**
 * The 6-category condition builder (v3.1 §4, 問財 pattern).
 *
 * Each column holds PILLS; each pill opens a dropdown of concrete OPTIONS.
 * Picking an option does two things:
 *   1. appends `phrase` to the query — so the user reads back exactly what
 *      they asked for, and can edit it as text;
 *   2. contributes `rule` to the live match count.
 *
 * **The phrases are chosen to round-trip through the backend's
 * `screen_rule_parser`.** That keeps the query string the single source of
 * truth: whatever the builder writes, submitting the box re-parses the same
 * way as if it had been typed by hand. If you add an option here whose phrase
 * the extractor can't read, the count will be right but the submitted screen
 * won't match it — add the phrase to the backend vocabulary too.
 *
 * ONLY pills that actually filter are listed (Mr Gu's call). Every
 * `primitive_id` and `operator` below was verified against
 * `app/data/signal_primitives.py` — operators follow PRD-22c kind dispatch
 * (VALUE gt/gte/lt/lte · CROSS crosses_up/down · LEVEL is_true · EVENT fires),
 * because a rule carrying the wrong operator for its kind silently fails to
 * evaluate rather than erroring.
 *
 * The Fundamentals column carries NO primitives: those constraints are served
 * by `ScreenerFilters` through the mixed-query path, so a fundamental pill and
 * a technical pill compose into one screen automatically.
 */

export interface ConditionOption {
  /** Menu label. */
  label: string;
  /** Appended to the query; must be readable by the backend extractor. */
  phrase: string;
  /** Composer-shaped rule, or null for a fundamental (filter-path) pill. */
  rule: {
    primitive_id: string;
    operator: string;
    threshold?: number;
    primitive_params?: Record<string, number | string>;
  } | null;
}

export interface ConditionPill {
  label: string;
  options: ConditionOption[];
}

export interface ConditionGroup {
  key: string;
  label: string;
  pills: ConditionPill[];
}

const rsi = (op: string, n: number) => ({
  primitive_id: "rsi",
  operator: op,
  threshold: n,
  primitive_params: { period: 14 },
});

export const CONDITION_GROUPS: ConditionGroup[] = [
  {
    key: "technical",
    label: "Technical",
    pills: [
      {
        label: "Moving average",
        options: [
          { label: "Above the 200-day", phrase: "above the 200 day",
            rule: { primitive_id: "price_above_ma", operator: "is_true",
                    primitive_params: { period: 200 } } },
          { label: "Above the 50-day", phrase: "above the 50 day",
            rule: { primitive_id: "price_above_ma", operator: "is_true",
                    primitive_params: { period: 50 } } },
          { label: "Rising average", phrase: "uptrend",
            rule: { primitive_id: "ma_slope_positive", operator: "is_true",
                    primitive_params: { period: 50 } } },
          { label: "Golden cross", phrase: "golden cross",
            rule: { primitive_id: "golden_cross", operator: "crosses_up" } },
          { label: "Death cross", phrase: "death cross",
            rule: { primitive_id: "death_cross", operator: "crosses_down" } },
        ],
      },
      {
        label: "MACD",
        options: [
          { label: "Crossing up", phrase: "macd crossing up",
            rule: { primitive_id: "macd_signal_cross", operator: "crosses_up" } },
          { label: "Crossing down", phrase: "macd crossing down",
            rule: { primitive_id: "macd_signal_cross", operator: "crosses_down" } },
          { label: "Above zero line", phrase: "macd above zero",
            rule: { primitive_id: "macd_zero_line_cross", operator: "crosses_up" } },
        ],
      },
      {
        label: "RSI",
        options: [
          { label: "Oversold (below 30)", phrase: "oversold", rule: rsi("lt", 30) },
          { label: "Overbought (above 70)", phrase: "overbought", rule: rsi("gt", 70) },
          { label: "Below 40", phrase: "rsi below 40", rule: rsi("lt", 40) },
          { label: "Above 60", phrase: "rsi above 60", rule: rsi("gt", 60) },
        ],
      },
      {
        label: "Stochastic",
        options: [
          { label: "K crosses above D", phrase: "stochastic crossing up",
            rule: { primitive_id: "stoch_k_d_cross", operator: "crosses_up" } },
          { label: "K crosses below D", phrase: "stochastic crossing down",
            rule: { primitive_id: "stoch_k_d_cross", operator: "crosses_down" } },
        ],
      },
      {
        label: "Trend strength",
        options: [
          { label: "Trending (ADX ≥ 25)", phrase: "trending",
            rule: { primitive_id: "adx", operator: "gte", threshold: 25,
                    primitive_params: { period: 14 } } },
          { label: "Strongly trending (≥ 40)", phrase: "strong trend",
            rule: { primitive_id: "adx", operator: "gte", threshold: 40,
                    primitive_params: { period: 14 } } },
        ],
      },
    ],
  },
  {
    key: "quote",
    label: "Market / quote",
    pills: [
      {
        label: "Relative volume",
        options: [
          { label: "Volume surge", phrase: "volume surge",
            rule: { primitive_id: "rvol_surge", operator: "fires" } },
          { label: "2× normal or more", phrase: "unusual volume",
            rule: { primitive_id: "rvol", operator: "gte", threshold: 2,
                    primitive_params: { lookback: 20 } } },
        ],
      },
      {
        label: "Momentum (20d)",
        options: [
          { label: "Up more than 10%", phrase: "roc above 10",
            rule: { primitive_id: "roc", operator: "gt", threshold: 10,
                    primitive_params: { period: 20 } } },
          { label: "Down more than 10%", phrase: "roc below -10",
            rule: { primitive_id: "roc", operator: "lt", threshold: -10,
                    primitive_params: { period: 20 } } },
        ],
      },
      {
        label: "VWAP",
        options: [
          { label: "Above VWAP", phrase: "above vwap",
            rule: { primitive_id: "vwap", operator: "gt", threshold: 0,
                    primitive_params: { period: 20 } } },
        ],
      },
    ],
  },
  {
    key: "stage",
    label: "Stage performance",
    pills: [
      {
        label: "52-week range",
        options: [
          { label: "Within 5% of the high", phrase: "near the 52 week high",
            rule: { primitive_id: "distance_to_52w_high", operator: "gte",
                    threshold: -5, primitive_params: { lookback: 252 } } },
          { label: "Within 10% of the high", phrase: "near the 52 week high",
            rule: { primitive_id: "distance_to_52w_high", operator: "gte",
                    threshold: -10, primitive_params: { lookback: 252 } } },
        ],
      },
      {
        label: "Breakout",
        options: [
          { label: "20-day breakout", phrase: "breaking out",
            rule: { primitive_id: "donchian_breakout", operator: "fires",
                    primitive_params: { period: 20 } } },
        ],
      },
      {
        label: "Consolidation",
        options: [
          { label: "Volatility squeeze", phrase: "squeeze",
            rule: { primitive_id: "ttm_squeeze", operator: "is_true" } },
        ],
      },
    ],
  },
  {
    key: "financials",
    label: "Financials",
    pills: [
      {
        label: "P/E",
        options: [
          // Fundamental: served by ScreenerFilters via the mixed-query path.
          { label: "Under 15", phrase: "p/e under 15", rule: null },
          { label: "Under 25", phrase: "p/e under 25", rule: null },
        ],
      },
      {
        label: "Dividend yield",
        options: [
          { label: "Above 2%", phrase: "yielding more than 2%", rule: null },
          { label: "Above 4%", phrase: "yielding more than 4%", rule: null },
        ],
      },
      {
        label: "Value",
        options: [
          { label: "High book-to-market", phrase: "book to market above 0.5",
            rule: { primitive_id: "book_to_market", operator: "gt", threshold: 0.5 } },
          { label: "High FCF yield", phrase: "fcf yield above 5",
            rule: { primitive_id: "fcf_yield", operator: "gt", threshold: 0.05 } },
        ],
      },
      {
        label: "Quality",
        options: [
          { label: "Piotroski F-score ≥ 7", phrase: "f score above 7",
            rule: { primitive_id: "f_score", operator: "gte", threshold: 7 } },
        ],
      },
    ],
  },
  {
    key: "fundamentals",
    label: "Fundamentals",
    pills: [
      {
        label: "Market cap",
        options: [
          { label: "Mega cap", phrase: "mega cap", rule: null },
          { label: "Large cap", phrase: "large cap", rule: null },
          { label: "Mid cap", phrase: "mid cap", rule: null },
          { label: "Small cap", phrase: "small cap", rule: null },
        ],
      },
      {
        label: "Sector",
        options: [
          { label: "Technology", phrase: "technology", rule: null },
          { label: "Health care", phrase: "healthcare", rule: null },
          { label: "Financials", phrase: "financials", rule: null },
          { label: "Energy", phrase: "energy", rule: null },
          { label: "Industrials", phrase: "industrials", rule: null },
          { label: "Consumer discretionary", phrase: "consumer discretionary", rule: null },
          { label: "Consumer staples", phrase: "consumer staples", rule: null },
          { label: "Utilities", phrase: "utilities", rule: null },
          { label: "Real estate", phrase: "real estate", rule: null },
          { label: "Materials", phrase: "materials", rule: null },
          { label: "Communication services", phrase: "communication services", rule: null },
        ],
      },
    ],
  },
  {
    key: "special",
    label: "Special data",
    pills: [
      {
        label: "News sentiment",
        options: [
          { label: "Bullish (30d)", phrase: "sentiment above 0.2",
            rule: { primitive_id: "sentiment_score", operator: "gt", threshold: 0.2,
                    primitive_params: { window_days: 30 } } },
        ],
      },
      {
        label: "Insider buying",
        options: [
          { label: "Net buying (90d)", phrase: "insider buying",
            rule: { primitive_id: "insider_net_buy", operator: "gt", threshold: 0,
                    primitive_params: { window_days: 90 } } },
        ],
      },
      {
        label: "Earnings",
        options: [
          { label: "Positive surprise", phrase: "positive earnings surprise",
            rule: { primitive_id: "earnings_surprise", operator: "gt", threshold: 0,
                    primitive_params: { window_days: 60 } } },
          { label: "Estimates rising", phrase: "estimates rising",
            rule: { primitive_id: "estimate_revision_3m", operator: "gt", threshold: 0 } },
        ],
      },
    ],
  },
];
