"use client";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import type { RevenueSegmentSection, BusinessMapSection } from "@/lib/contracts";

function fmtMoney(v: number): string {
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

// ── Stacked bar chart ─────────────────────────────────────────────────────────

function RevenueStackedBar({ seg }: { seg: RevenueSegmentSection }) {
  // Recharts needs [{year, SegA: v, SegB: v, ...}] flat format, oldest → newest
  const chartData = [...seg.product_years].reverse().map((y) => ({
    year: String(y.year),
    ...y.segments,
  }));

  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Revenue by Segment (5 years)
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="year" tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={(v) => fmtMoney(v)} tick={{ fontSize: 9 }} width={52} />
          <Tooltip formatter={(v) => (typeof v === "number" ? fmtMoney(v) : String(v))} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {seg.segment_names.map((name, i) => (
            <Bar
              key={name}
              dataKey={name}
              stackId="a"
              fill={seg.segment_colors[i] ?? "#6366f1"}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Geographic donut ──────────────────────────────────────────────────────────

function GeoDonut({ seg }: { seg: RevenueSegmentSection }) {
  const latest = seg.geo_years[0];
  if (!latest) return null;

  const donutData = seg.geo_names.map((name) => ({
    name,
    value: latest.segments[name] ?? 0,
  })).filter((d) => d.value > 0);

  const total = donutData.reduce((s, d) => s + d.value, 0);

  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        Geographic Mix — {latest.year}
      </div>
      <div className="flex items-center gap-4">
        <ResponsiveContainer width={140} height={140}>
          <PieChart>
            <Pie
              data={donutData}
              innerRadius="52%"
              outerRadius="78%"
              dataKey="value"
              strokeWidth={1}
            >
              {donutData.map((_, i) => (
                <Cell key={i} fill={seg.geo_colors[i] ?? "#3b82f6"} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => [typeof v === "number" ? fmtMoney(v) : String(v), ""]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="space-y-1 text-[11px]">
          {donutData.map((d, i) => (
            <div key={d.name} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: seg.geo_colors[i] ?? "#3b82f6" }}
              />
              <span className="text-foreground/70">{d.name}</span>
              <span className="ml-auto font-mono font-medium pl-2">
                {total > 0 ? `${((d.value / total) * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Business characteristics chips ───────────────────────────────────────────

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-1.5 rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs">
      <span className="font-semibold text-muted-foreground shrink-0">{label}:</span>
      <span className="text-foreground/80">{value}</span>
    </div>
  );
}

// ── Composed section ──────────────────────────────────────────────────────────

interface Props {
  seg: RevenueSegmentSection;
  bm: BusinessMapSection;
}

export function BusinessModelSection({ seg, bm }: Props) {
  const hasProductSeg = seg.product_years.length > 0 && seg.segment_names.length > 0;
  const hasGeoSeg = seg.geo_years.length > 0 && seg.geo_names.length > 0;
  const hasChips = bm.revenue_model || bm.customer_types.length > 0
    || bm.cyclicality_implication || bm.pricing_power_implication;

  return (
    <div className="space-y-5">
      {/* Charts row */}
      {(hasProductSeg || hasGeoSeg) ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {hasProductSeg && <RevenueStackedBar seg={seg} />}
          {hasGeoSeg && <GeoDonut seg={seg} />}
        </div>
      ) : seg.fallback_note ? (
        <p className="text-xs text-muted-foreground italic">{seg.fallback_note}</p>
      ) : null}

      {/* Business characteristics chips */}
      {hasChips && (
        <div className="flex flex-wrap gap-2">
          {bm.revenue_model && (
            <Chip label="Revenue model" value={bm.revenue_model} />
          )}
          {bm.customer_types.length > 0 && (
            <Chip label="Customers" value={bm.customer_types.join(" · ")} />
          )}
          {bm.cyclicality_implication && (
            <Chip label="Cyclicality" value={bm.cyclicality_implication} />
          )}
          {bm.pricing_power_implication && (
            <Chip label="Pricing power" value={bm.pricing_power_implication} />
          )}
        </div>
      )}

      {/* Business summary if present */}
      {bm.one_line_summary && (
        <p className="text-sm leading-relaxed text-foreground/75">{bm.one_line_summary}</p>
      )}
    </div>
  );
}
