/**
 * The default universe the sentiment toolkits scan (PRD-24a §11 #1 — kept at
 * the curated 20 for v1; watchlist/SP500 scoping is a later decision).
 *
 * Shared so the Sentiment Hub and the Home "Themes Firing Today" cards run the
 * toolkits over the SAME list (no duplicated constant).
 */
export const DEFAULT_SENTIMENT_SYMBOLS: string[] = [
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "UNH",
  "JNJ", "PG", "HD", "MA", "BAC", "XOM", "ABBV", "PFE", "LLY", "COST",
];
