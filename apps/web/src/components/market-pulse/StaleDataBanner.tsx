"use client";

import { AlertTriangle } from "lucide-react";

/**
 * Banner shown above Market Pulse content when the page is rendering
 * fallback-cached data because the live `/api/market/pulse` fetch failed
 * (5xx, timeout, network).
 *
 * Why this component is its own surface:
 *   - Lives ABOVE the data, not inline — users need to know everything
 *     they see is from a previous fetch before scanning prices.
 *   - Calendar-anchored timestamp (newspaper-byline pattern from
 *     CLAUDE.md product invariants) — date stamps must be visible, not
 *     buried in 9px footer text.
 *   - Stable color: muted-amber on muted background, NOT alarm-red.
 *     The data is stale, not dangerous; we don't want to make users
 *     panic about correctness.
 */
export interface StaleDataBannerProps {
  /** When the cached data was originally fetched. */
  fetchedAt: Date;
  /** Whether a retry is currently in-flight in the background. */
  retrying?: boolean;
}

function formatTimestamp(d: Date): string {
  // Match user's locale + 12-hour clock for readability. Shows time-only
  // when same day; date+time when older.
  const sameDay = d.toDateString() === new Date().toDateString();
  if (sameDay) {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function StaleDataBanner({ fetchedAt, retrying }: StaleDataBannerProps) {
  const stamp = formatTimestamp(fetchedAt);
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <span className="font-medium">Live market data temporarily unavailable.</span>{" "}
        <span>
          Showing the last successful snapshot from <strong>{stamp}</strong>.
        </span>
      </div>
      {retrying ? (
        <span className="text-[10px] uppercase tracking-wider text-amber-700">
          Retrying…
        </span>
      ) : null}
    </div>
  );
}
