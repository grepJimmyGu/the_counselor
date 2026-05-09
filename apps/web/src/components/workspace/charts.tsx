"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipContentProps } from "recharts";

import type { BacktestResult } from "@/lib/contracts";

const tooltipStyle = {
  backgroundColor: "var(--color-card)",
  border: "1px solid var(--color-border)",
  borderRadius: "0.5rem",
  fontSize: "12px",
  color: "var(--color-foreground)",
  padding: "8px 12px",
};

const tooltipLabelStyle = {
  color: "var(--color-muted-foreground)",
  marginBottom: "4px",
  fontFamily: "var(--font-mono)",
};

function formatTooltipValue(value: number | null, asPercent = false): string {
  if (value == null) return "—";
  if (asPercent) return `${(value * 100).toFixed(2)}%`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function EquityTooltip({ active, payload, label }: TooltipContentProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div style={tooltipStyle} role="tooltip">
      <div style={tooltipLabelStyle}>{label}</div>
      {payload.map((entry, i) => (
        <div key={`${String(entry.dataKey)}-${i}`} style={{ color: entry.color, display: "flex", gap: "8px", justifyContent: "space-between" }}>
          <span>{entry.name}</span>
          <span style={{ fontFamily: "var(--font-mono)", fontWeight: 500 }}>
            {formatTooltipValue(entry.value as number)}
          </span>
        </div>
      ))}
    </div>
  );
}

function DrawdownTooltip({ active, payload, label }: TooltipContentProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div style={tooltipStyle} role="tooltip">
      <div style={tooltipLabelStyle}>{label}</div>
      {payload.map((entry, i) => (
        <div key={`${String(entry.dataKey)}-${i}`} style={{ color: entry.color, display: "flex", gap: "8px", justifyContent: "space-between" }}>
          <span>{entry.name}</span>
          <span style={{ fontFamily: "var(--font-mono)", fontWeight: 500 }}>
            {formatTooltipValue(entry.value as number, true)}
          </span>
        </div>
      ))}
    </div>
  );
}

function chartData(result: BacktestResult) {
  return result.equity_curve.map((point, index) => ({
    date: point.date,
    strategy: point.value,
    benchmark: result.benchmark_curve[index]?.value ?? null,
    buy_and_hold: result.buy_and_hold_curve[index]?.value ?? null,
    drawdown: result.drawdown_curve[index]?.value ?? null,
  }));
}

export function EquityCurveChart({ result }: { result: BacktestResult }) {
  const data = chartData(result);

  return (
    <div className="h-[320px] w-full" role="img" aria-label="Equity curve chart comparing strategy vs benchmark performance over time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} minTickGap={36} />
          <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} width={88} />
          <Tooltip content={EquityTooltip} />
          <Legend />
          <Line type="monotone" dataKey="strategy" stroke="var(--color-chart-1)" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="benchmark" stroke="var(--color-chart-2)" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="buy_and_hold" stroke="var(--color-chart-3)" dot={false} strokeWidth={2} strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DrawdownChart({ result }: { result: BacktestResult }) {
  const data = chartData(result);

  return (
    <div className="h-[260px] w-full" role="img" aria-label="Drawdown chart showing strategy underwater periods">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} minTickGap={36} />
          <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} width={72} />
          <Tooltip content={DrawdownTooltip} />
          <Line type="monotone" dataKey="drawdown" stroke="var(--color-chart-4)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

