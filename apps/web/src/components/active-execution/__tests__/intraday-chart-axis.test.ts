/**
 * Session-aware intraday axis — the fix for "multi-day data on a time-only
 * axis is misleading." Bars become evenly-spaced ordinals (gaps collapse),
 * ticks carry ET date + time, day boundaries are labelled with the date.
 */
import { describe, expect, it } from "vitest";

import type { IntradayChartBar } from "@/lib/api";
import { buildIntradayAxis, nearestIndex } from "../intraday-chart-axis";

// ET-aware ISO strings (as the backend emits them, -04:00 in June/EDT).
function bar(iso: string, close: number): IntradayChartBar {
  return { t: iso, close };
}

describe("buildIntradayAxis", () => {
  it("maps bars to evenly-spaced ordinals regardless of the real-time gap", () => {
    // Two bars 30min apart, then a ~17h overnight gap to the next day.
    const axis = buildIntradayAxis([
      bar("2026-06-10T15:30:00-04:00", 100),
      bar("2026-06-10T16:00:00-04:00", 101), // session close
      bar("2026-06-11T09:30:00-04:00", 102), // next-day open (big wall-clock gap)
    ]);
    // Ordinals are 0,1,2 — the overnight gap is collapsed, not stretched.
    expect(axis.points.map((p) => p.idx)).toEqual([0, 1, 2]);
    expect(axis.points.map((p) => p.close)).toEqual([100, 101, 102]);
  });

  it("labels each new trading day with its DATE, and intraday ticks with time", () => {
    const axis = buildIntradayAxis([
      bar("2026-06-10T15:30:00-04:00", 100),
      bar("2026-06-10T16:00:00-04:00", 101),
      bar("2026-06-11T09:30:00-04:00", 102),
      bar("2026-06-11T10:00:00-04:00", 103),
    ]);
    // idx 0 is the first bar of Jun 10 → date label; idx 2 is the first bar
    // of Jun 11 → date label. Both are day boundaries.
    expect(axis.tickLabel(0)).toMatch(/Jun 10/);
    expect(axis.tickLabel(2)).toMatch(/Jun 11/);
    // A non-boundary tick shows only the ET time, no date.
    expect(axis.tickLabel(3)).toMatch(/^\d{2}:\d{2}/);
    expect(axis.tickLabel(3)).not.toMatch(/Jun/);
  });

  it("renders ET wall-clock (not the viewer's local zone)", () => {
    // 16:00 ET = 20:00 UTC. The label must read the ET time.
    const axis = buildIntradayAxis([bar("2026-06-10T16:00:00-04:00", 101)]);
    expect(axis.fullLabel(0)).toContain("ET");
    expect(axis.fullLabel(0)).toMatch(/04:00\s?PM|16:00/); // ET, not 20:00
  });

  it("includes day boundaries + the last bar in the tick set", () => {
    const bars = Array.from({ length: 20 }, (_, i) =>
      bar(`2026-06-10T${String(9 + Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}:00-04:00`, 100 + i),
    );
    const axis = buildIntradayAxis(bars, 6);
    expect(axis.tickIndices).toContain(0); // first / day boundary
    expect(axis.tickIndices).toContain(bars.length - 1); // last bar
    expect(axis.tickIndices.length).toBeLessThanOrEqual(7);
  });

  it("drops bars with unparseable timestamps", () => {
    const axis = buildIntradayAxis([
      bar("not-a-date", 1),
      bar("2026-06-10T09:30:00-04:00", 2),
    ]);
    expect(axis.points).toHaveLength(1);
    expect(axis.points[0].close).toBe(2);
  });
});

describe("nearestIndex", () => {
  const pts = [
    { ms: Date.parse("2026-06-10T09:30:00-04:00") },
    { ms: Date.parse("2026-06-10T10:00:00-04:00") },
    { ms: Date.parse("2026-06-10T10:30:00-04:00") },
  ];

  it("maps an event time to the closest bar ordinal", () => {
    // 10:05 ET is closest to the 10:00 bar (idx 1).
    expect(nearestIndex(pts, Date.parse("2026-06-10T10:05:00-04:00"))).toBe(1);
    // 10:29 is closest to 10:30 (idx 2).
    expect(nearestIndex(pts, Date.parse("2026-06-10T10:29:00-04:00"))).toBe(2);
  });

  it("returns -1 for an empty series", () => {
    expect(nearestIndex([], Date.now())).toBe(-1);
  });
});
