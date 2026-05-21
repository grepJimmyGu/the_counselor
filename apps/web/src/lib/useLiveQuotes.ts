"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// Poll interval. Should be >= backend cache TTL so a poll matches the
// freshest cached value. 30s here pairs with the TTL_SECONDS=30 in
// apps/api/app/services/live_quote_service.py.
const POLL_INTERVAL_MS = 30_000;

export interface LiveQuote {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  day_high: number | null;
  day_low: number | null;
  volume: number | null;
  market_cap: number | null;
  name: string | null;
  exchange: string | null;
  fetched_at: number;
}

interface UseLiveQuotesResult {
  quotes: Record<string, LiveQuote>;
  loading: boolean;
}

/**
 * Poll live quotes for a list of tickers. Mounting fires an immediate fetch;
 * subsequent fetches every 30s while the component is mounted.
 *
 * Symbols are case-insensitive and de-duplicated upstream. Missing keys in
 * the returned `quotes` map mean FMP didn't return data for that ticker
 * (bad symbol, outage); callers render a placeholder.
 *
 * Single source of truth: any component that renders a price (ticker bar,
 * stock detail page, workspace preview, community card chip) consumes this.
 */
export function useLiveQuotes(symbols: string[]): UseLiveQuotesResult {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [loading, setLoading] = useState(false);

  // Stabilize the dep — symbols.join() prevents re-renders from triggering
  // a new effect just because the array identity changed.
  const key = symbols.map(s => s.trim().toUpperCase()).filter(Boolean).sort().join(",");

  useEffect(() => {
    if (!key) {
      setQuotes({});
      return;
    }

    let cancelled = false;
    const url = `${API_BASE}/api/live/quotes?symbols=${encodeURIComponent(key)}`;

    const tick = async () => {
      setLoading(true);
      try {
        const res = await fetch(url);
        if (!res.ok) return;
        const data: { quotes: Record<string, LiveQuote> } = await res.json();
        if (!cancelled) setQuotes(data.quotes ?? {});
      } catch {
        // Network failures are silent — keep the last-known quotes visible.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void tick();
    const interval = setInterval(tick, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [key]);

  return { quotes, loading };
}
