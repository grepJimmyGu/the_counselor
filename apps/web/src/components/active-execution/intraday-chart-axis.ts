/**
 * Session-aware axis model for the intraday chart.
 *
 * Intraday bars span multiple trading days with long market-closed gaps
 * (overnight, weekends). Plotting them on a real-time axis (a) interpolates
 * a misleading straight line across the closed-market gaps and (b) shows
 * only time-of-day, so the same "09:30" appears on different days with no
 * way to tell them apart.
 *
 * This builds an INDEX-based axis: bars are evenly spaced regardless of the
 * wall-clock gap between them, so closed-market periods collapse. Ticks are
 * labelled in US Eastern, with the DATE shown at each new trading day and
 * the time otherwise — so the date/time are never ambiguous.
 *
 * Pure functions, unit-tested separately from the recharts SVG.
 */
import type { IntradayChartBar } from "@/lib/api";

const ET = "America/New_York";

export interface AxisPoint {
  /** Evenly-spaced ordinal position on the x-axis. */
  idx: number;
  close: number;
  /** Absolute instant (ms) — used only to map event markers to a bar. */
  ms: number;
}

export interface IntradayAxis {
  points: AxisPoint[];
  /** Ordinals at which to draw a labelled tick. */
  tickIndices: number[];
  /** Short axis label for a tick ordinal (date at a day boundary, else time). */
  tickLabel: (idx: number) => string;
  /** Full "Jun 10, 09:30 ET" label for the tooltip. */
  fullLabel: (idx: number) => string;
}

/** YYYY-MM-DD in ET — used to detect a trading-day boundary. */
function etDateKey(ms: number): string {
  return new Date(ms).toLocaleDateString("en-CA", { timeZone: ET });
}

function etDate(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", {
    timeZone: ET,
    month: "short",
    day: "numeric",
  });
}

function etTime(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: ET,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function buildIntradayAxis(
  bars: IntradayChartBar[],
  maxTicks = 7,
): IntradayAxis {
  const points: AxisPoint[] = bars
    .map((b) => ({ ms: Date.parse(b.t), close: b.close }))
    .filter((p) => Number.isFinite(p.ms))
    .map((p, idx) => ({ idx, close: p.close, ms: p.ms }));

  // First bar of each distinct ET day → a day boundary worth a date label.
  const dayStart = new Set<number>();
  let prevKey = "";
  for (const p of points) {
    const key = etDateKey(p.ms);
    if (key !== prevKey) {
      dayStart.add(p.idx);
      prevKey = key;
    }
  }

  // Ticks = every day boundary + the last bar + evenly-spaced fillers,
  // capped at maxTicks so the axis stays readable.
  const ticks = new Set<number>(dayStart);
  if (points.length > 0) {
    ticks.add(points.length - 1);
    const need = Math.max(0, maxTicks - ticks.size);
    if (need > 0 && points.length > 1) {
      const step = (points.length - 1) / (need + 1);
      for (let i = 1; i <= need; i++) ticks.add(Math.round(step * i));
    }
  }
  const tickIndices = [...ticks]
    .filter((i) => i >= 0 && i < points.length)
    .sort((a, b) => a - b);

  const tickLabel = (idx: number): string => {
    const p = points[idx];
    if (!p) return "";
    return dayStart.has(idx) ? `${etDate(p.ms)} ${etTime(p.ms)}` : etTime(p.ms);
  };

  const fullLabel = (idx: number): string => {
    const p = points[idx];
    return p ? `${etDate(p.ms)}, ${etTime(p.ms)} ET` : "";
  };

  return { points, tickIndices, tickLabel, fullLabel };
}

/** Index of the bar nearest (in absolute time) to `ms`; -1 if no points. */
export function nearestIndex(points: ReadonlyArray<{ ms: number }>, ms: number): number {
  let best = -1;
  let bestDiff = Infinity;
  for (let i = 0; i < points.length; i++) {
    const diff = Math.abs(points[i].ms - ms);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = i;
    }
  }
  return best;
}
