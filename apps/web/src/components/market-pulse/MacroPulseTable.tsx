"use client";

import { useState } from "react";
import { ArrowRight, ArrowUpRight, ArrowDownRight, CircleHelp } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Section 2 — Macro Pulse table.
 *
 * Replaces `MacroPanels` per Jimmy's 2026-05-21 feedback. The user wants:
 *   - 4 macro signals (Growth / Inflation / Rates / Stress), not 6 ETF
 *     cards
 *   - A clean tabular layout (Signal | Latest | Trend | Takeaway)
 *     matching the attached Seeking Alpha-style screenshot
 *   - Each row carries a sparkline + a 1M/1Y/3Y toggle at the section
 *     level (one toggle affects all 4 sparklines)
 *   - Plain-English takeaway per row + a metric explanation tooltip
 *
 * **Phase 0a status:** all data is HARDCODED MOCK so the layout is
 * reviewable. Phase 1 wires a backend service that pulls real ISM PMI,
 * Core CPI, 10Y yield, and HY OAS from FRED or AV's economic-indicator
 * API.
 *
 * Layout: full table on `sm+`; stacked cards on mobile so the columns
 * don't have to horizontally scroll.
 */

type Range = "1M" | "1Y" | "3Y";

interface MacroSignal {
  category: "Growth" | "Inflation" | "Rates" | "Stress";
  latestLabel: string;
  trendDirection: "up" | "down" | "flat";
  trendLabel: string;
  takeaway: string;
  explanation: string;
  series1M: number[];
  series1Y: number[];
  series3Y: number[];
}

const MOCK_MACRO: MacroSignal[] = [
  {
    category: "Growth",
    latestLabel: "ISM Services PMI: 52.0",
    trendDirection: "up",
    trendLabel: "Improving",
    takeaway: "Economy still expanding",
    explanation:
      "ISM Services PMI — monthly diffusion index of services sector activity. >50 = expansion, <50 = contraction. Above 52 implies steady growth; below 48 starts to signal recession risk.",
    series1M: [51.4, 51.7, 51.9, 52.1, 52.0, 52.0, 52.2, 52.0],
    series1Y: gen("growth-1y", 52, 4, 52, 0.3),
    series3Y: gen("growth-3y", 36, 4, 53, 0.4),
  },
  {
    category: "Inflation",
    latestLabel: "Core CPI: 3.4%",
    trendDirection: "down",
    trendLabel: "Cooling",
    takeaway: "Supports future rate cuts",
    explanation:
      "Core CPI — year-over-year change in consumer prices ex-food and energy. The Fed's primary inflation gauge for policy decisions. Target is 2.0%. Above 3% = restrictive policy stance; trending lower = cuts on the table.",
    series1M: [3.6, 3.5, 3.5, 3.5, 3.4, 3.4, 3.4, 3.4],
    series1Y: gen("inflation-1y", 52, 6, 3.8, -0.02),
    series3Y: gen("inflation-3y", 36, 6, 5.5, -0.08),
  },
  {
    category: "Rates",
    latestLabel: "10Y Yield: 4.3%",
    trendDirection: "up",
    trendLabel: "Rising",
    takeaway: "Headwind for growth stocks",
    explanation:
      "10-year US Treasury yield — the global risk-free rate benchmark. Discount rate for long-duration equity cash flows. Rising = pressure on growth multiples; falling = relief rally for duration-sensitive sectors (tech, REITs, utilities).",
    series1M: [4.15, 4.18, 4.22, 4.25, 4.27, 4.29, 4.30, 4.30],
    series1Y: gen("rates-1y", 52, 5, 4.1, 0.005),
    series3Y: gen("rates-3y", 36, 5, 3.5, 0.025),
  },
  {
    category: "Stress",
    latestLabel: "HY Spread: 3.4%",
    trendDirection: "flat",
    trendLabel: "Stable",
    takeaway: "Credit risk contained",
    explanation:
      "ICE BofA US High-Yield Option-Adjusted Spread — extra yield investors demand to hold junk bonds vs Treasuries. Below 4% = risk-on; 4-6% = stretched; above 7% = credit stress. Widely watched as the canary for cycle turns.",
    series1M: [3.35, 3.40, 3.42, 3.38, 3.40, 3.41, 3.40, 3.40],
    series1Y: gen("stress-1y", 52, 4, 3.6, -0.005),
    series3Y: gen("stress-3y", 36, 4, 4.2, -0.02),
  },
];

export function MacroPulseTable() {
  const [range, setRange] = useState<Range>("1Y");

  return (
    <TooltipProvider delayDuration={200}>
      <section
        id="macro"
        aria-labelledby="macro-heading"
        className="space-y-3"
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-baseline gap-2">
            <h2
              id="macro-heading"
              className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
            >
              Macro Pulse
            </h2>
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-900">
              Preview · mock data
            </span>
          </div>
          <RangeTabs range={range} onChange={setRange} />
        </div>

        {/* Desktop / tablet table */}
        <div className="hidden sm:block rounded-xl border border-border bg-white overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="text-left font-semibold px-3 py-2 w-28">
                  Macro Signal
                </th>
                <th className="text-left font-semibold px-3 py-2">Latest</th>
                <th className="text-left font-semibold px-3 py-2 w-32">
                  Trend ({range})
                </th>
                <th className="text-left font-semibold px-3 py-2 w-36">Trend</th>
                <th className="text-left font-semibold px-3 py-2">Takeaway</th>
                <th className="w-8 px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {MOCK_MACRO.map((m) => (
                <MacroRow key={m.category} signal={m} range={range} />
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile — stacked cards */}
        <div className="sm:hidden space-y-2">
          {MOCK_MACRO.map((m) => (
            <MacroCardMobile key={m.category} signal={m} range={range} />
          ))}
        </div>
      </section>
    </TooltipProvider>
  );
}

function RangeTabs({
  range,
  onChange,
}: {
  range: Range;
  onChange: (r: Range) => void;
}) {
  const opts: Range[] = ["1M", "1Y", "3Y"];
  return (
    <div className="inline-flex items-center gap-1 rounded-md border border-border bg-white p-0.5">
      {opts.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(o)}
          className={cn(
            "rounded px-2 py-1 font-mono text-[10px] font-semibold transition-colors",
            range === o
              ? "bg-foreground text-white"
              : "text-muted-foreground hover:bg-muted/40",
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function MacroRow({ signal, range }: { signal: MacroSignal; range: Range }) {
  const series = pickSeries(signal, range);
  return (
    <tr>
      <td className="px-3 py-3 font-semibold">{signal.category}</td>
      <td className="px-3 py-3 font-mono tabular-nums">{signal.latestLabel}</td>
      <td className="px-3 py-3">
        <Sparkline data={series} direction={signal.trendDirection} />
      </td>
      <td className="px-3 py-3">
        <TrendChip
          direction={signal.trendDirection}
          label={signal.trendLabel}
        />
      </td>
      <td className="px-3 py-3 text-foreground/80">{signal.takeaway}</td>
      <td className="px-3 py-3">
        <ExplanationIcon explanation={signal.explanation} />
      </td>
    </tr>
  );
}

function MacroCardMobile({
  signal,
  range,
}: {
  signal: MacroSignal;
  range: Range;
}) {
  const series = pickSeries(signal, range);
  return (
    <div className="rounded-xl border border-border bg-white p-3 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold">{signal.category}</span>
        <ExplanationIcon explanation={signal.explanation} />
      </div>
      <div className="mt-1 font-mono tabular-nums">{signal.latestLabel}</div>
      <div className="mt-2">
        <Sparkline data={series} direction={signal.trendDirection} />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <TrendChip
          direction={signal.trendDirection}
          label={signal.trendLabel}
        />
        <span className="text-foreground/80 text-right">{signal.takeaway}</span>
      </div>
    </div>
  );
}

function TrendChip({
  direction,
  label,
}: {
  direction: "up" | "down" | "flat";
  label: string;
}) {
  const Icon =
    direction === "up"
      ? ArrowUpRight
      : direction === "down"
        ? ArrowDownRight
        : ArrowRight;
  return (
    <span className="inline-flex items-center gap-1 font-medium text-foreground/80">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      {label}
    </span>
  );
}

function ExplanationIcon({ explanation }: { explanation: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="What this metric means"
          className="inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground/60 hover:text-foreground hover:bg-muted/40"
        >
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="left"
        className="max-w-[260px] leading-relaxed text-xs"
      >
        {explanation}
      </TooltipContent>
    </Tooltip>
  );
}

function Sparkline({
  data,
  direction,
}: {
  data: number[];
  direction: "up" | "down" | "flat";
}) {
  if (data.length < 2)
    return <span className="text-muted-foreground">—</span>;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 100;
  const h = 24;
  const stepX = w / (data.length - 1);
  const points = data
    .map(
      (v, i) =>
        `${(i * stepX).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`,
    )
    .join(" ");
  const color =
    direction === "up"
      ? "#10b981"
      : direction === "down"
        ? "#ef4444"
        : "#6b7280";

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="w-24 h-6"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
    </svg>
  );
}

function pickSeries(s: MacroSignal, range: Range): number[] {
  if (range === "1M") return s.series1M;
  if (range === "1Y") return s.series1Y;
  return s.series3Y;
}

// ── Mock series generator ───────────────────────────────────────────────────
//
// Deterministic-ish synthetic walk so the sparklines look plausible without
// a real backend call. Phase 1 wires real macroeconomic data.

function gen(seed: string, n: number, base: number, start: number, drift: number): number[] {
  const h = hashString(seed);
  const out: number[] = [];
  let v = start;
  for (let i = 0; i < n; i++) {
    const noise = Math.sin((h + i) * 0.41) * (base * 0.04) + Math.sin((h + i) * 0.13) * (base * 0.02);
    v = v + drift + noise * 0.15;
    out.push(v);
  }
  return out;
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
