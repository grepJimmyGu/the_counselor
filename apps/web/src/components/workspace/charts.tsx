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

import type { BacktestResult } from "@/lib/contracts";

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
    <div className="h-[320px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} minTickGap={36} />
          <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} width={88} />
          <Tooltip />
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
    <div className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} minTickGap={36} />
          <YAxis tick={{ fill: "var(--color-muted-foreground)", fontSize: 12 }} width={72} />
          <Tooltip />
          <Line type="monotone" dataKey="drawdown" stroke="var(--color-chart-4)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

