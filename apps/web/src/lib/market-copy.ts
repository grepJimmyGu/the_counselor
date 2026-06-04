/**
 * i18n copy for the CN market view of the Market Pulse page.
 *
 * Pattern: `useMarketCopy(key, market)` returns the Chinese label
 * when `market === "CN"`, English otherwise. Lightweight — no
 * dependency needed; the lookup table sits right here.
 *
 * Usage:
 *   const label = useMarketCopy("section_heading", market);
 *   // "CN" → "市场脉搏"  |  "US" → "Market Pulse"
 *
 * Only the top-level Market Pulse page and its direct children
 * use this hook. Flow bricks and strategy builder use their own
 * `useFlowCopy` lexicon (separate concern).
 */

const CN_COPY: Record<string, string> = {
  // ── Page chrome ───────────────────────────────────────────────────
  section_heading: "市场脉搏",
  toggle_us: "美股",
  toggle_cn: "A股",
  refresh: "刷新",
  error_unavailable: "市场数据暂不可用 — 历史价格可能仍在加载中。",

  // ── Market Brief ───────────────────────────────────────────────────
  brief_loading: "加载中…",
  brief_narrative_fallback: "主要指数表现 · 板块资金流向 · 值得关注的动态",

  // ── Sector Rotation ────────────────────────────────────────────────
  sectors_heading: "行业板块轮动",
  sectors_chart_vs: "vs 沪深300",

  // ── Top Movers ─────────────────────────────────────────────────────
  movers_heading: "热门股票",
  movers_gainers: "涨幅最大",
  movers_losers: "跌幅最大",
  movers_etf: "ETF",
  movers_stock: "股票",

  // ── Screener ───────────────────────────────────────────────────────
  screener_heading: "股票筛选器",

  // ── Footer ─────────────────────────────────────────────────────────
  footer_disclaimer:
    "实时FMP行情驱动排名与价格 · 历史日线数据驱动五日走势 · 不构成投资建议",
};

export function useMarketCopy(key: string, market: "US" | "CN"): string {
  if (market === "CN") {
    return CN_COPY[key] ?? key;
  }
  // US: return the key itself — components render their English defaults.
  // This hook is additive; when market=US, components use their existing
  // hardcoded English strings unchanged.
  return key;
}
