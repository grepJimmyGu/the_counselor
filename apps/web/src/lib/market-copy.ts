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

const EN_COPY: Record<string, string> = {
  section_heading: "Market Pulse",
  toggle_us: "US",
  toggle_cn: "CN",
  refresh: "Refresh",
  error_unavailable: "Market data unavailable — price history may still be loading.",
  brief_loading: "Loading…",
  brief_narrative_fallback: "Index performance · sector flows · what to watch",
  sectors_heading: "Sector Rotation",
  sectors_sort_cmf: "Sort: CMF flow",
  sectors_sort_perf: "Sort: 1D performance",
  sectors_sort_rs: "Sort: RS vs SPY",
  sectors_view_heatmap: "Heatmap",
  sectors_view_table: "Table",
  sectors_chart_vs: "vs S&P 500",
  movers_heading: "Top Movers",
  movers_sort: "Sort top movers by",
  movers_all: "All",
  movers_gainers: "Sort: Top gainers",
  movers_losers: "Sort: Top losers",
  movers_etf: "ETF",
  movers_stock: "Stock",
  screener_heading: "Stock Screener",
  footer_disclaimer:
    "Live FMP snapshot powers rankings and prices · EOD history powers 5D context and freshness details · Not financial advice.",
};

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
  sectors_sort_cmf: "排序: CMF资金流",
  sectors_sort_perf: "排序: 当日涨跌",
  sectors_sort_rs: "排序: 相对强度",
  sectors_view_heatmap: "热力图",
  sectors_view_table: "表格",
  sectors_chart_vs: "vs 沪深300",

  // ── Top Movers ─────────────────────────────────────────────────────
  movers_heading: "热门股票",
  movers_sort: "排序方式",
  movers_all: "全部",
  movers_gainers: "排序: 涨幅最大",
  movers_losers: "排序: 跌幅最大",
  movers_etf: "ETF",
  movers_stock: "股票",

  // ── Screener ───────────────────────────────────────────────────────
  screener_heading: "股票筛选器",

  // ── Footer ─────────────────────────────────────────────────────────
  footer_disclaimer:
    "实时FMP行情驱动排名与价格 · 历史日线数据驱动五日走势 · 不构成投资建议",
};

export function useMarketCopy(key: string, market: "US" | "CN"): string {
  if (market === "CN") return CN_COPY[key] ?? key;
  return EN_COPY[key] ?? key;
}
