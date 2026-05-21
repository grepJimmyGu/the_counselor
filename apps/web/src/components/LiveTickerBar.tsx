"use client";

import { useLiveQuotes } from "@/lib/useLiveQuotes";

// Hot list — indices + Mag-7 + a few high-volume tickers. The frontend
// drives the symbol list (no backend "hot list" config) so it's trivially
// editable here.
const TICKER_BAR_SYMBOLS = [
  "SPY",   // S&P 500
  "QQQ",   // Nasdaq 100
  "DIA",   // Dow
  "IWM",   // Russell 2000
  "AAPL",
  "MSFT",
  "NVDA",
  "GOOGL",
  "AMZN",
  "META",
  "TSLA",
];

function formatPrice(price: number): string {
  return price >= 1000
    ? price.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : price.toFixed(2);
}

function formatChangePercent(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

/**
 * Global live ticker bar — mounted in app/layout.tsx beneath NavHeader.
 *
 * Renders nothing while the first fetch is in flight (no skeleton flash);
 * once data lands, the bar appears with a horizontal scroll. Auto-refreshes
 * every 30s via useLiveQuotes.
 */
export function LiveTickerBar() {
  const { quotes } = useLiveQuotes(TICKER_BAR_SYMBOLS);

  const rendered = TICKER_BAR_SYMBOLS.filter(sym => quotes[sym]);
  if (rendered.length === 0) return null;

  return (
    <div
      className="border-b border-border bg-muted/30 backdrop-blur-sm"
      aria-label="Live market prices"
    >
      <div className="flex items-center gap-6 overflow-x-auto px-4 py-2 text-xs whitespace-nowrap scrollbar-hide">
        {rendered.map(sym => {
          const q = quotes[sym];
          const up = q.change_percent >= 0;
          return (
            <div key={sym} className="inline-flex items-baseline gap-2 shrink-0">
              <span className="font-semibold text-foreground">{sym}</span>
              <span className="tabular-nums text-foreground">${formatPrice(q.price)}</span>
              <span
                className={`tabular-nums font-medium ${
                  up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {formatChangePercent(q.change_percent)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
