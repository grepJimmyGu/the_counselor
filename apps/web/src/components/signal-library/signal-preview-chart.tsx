/**
 * PRD-16a-4 — SignalPreviewChart.
 *
 * Lazy-loaded preview chart for one primitive on the default symbol
 * (SPY) over the last ~1 year. Shown when the user hovers (or clicks
 * "Preview") on a `<SignalPrimitiveCard>`.
 *
 * Uses recharts (already in deps for the workspace charts). Skeleton
 * state while loading; null-on-error (the catalog browser keeps working
 * even if a single primitive's preview fails).
 *
 * Parameter overrides via the `params` prop — pass through to the
 * preview endpoint as query-string. The composer (PRD-16b) will pass
 * the user's edited values; the standalone catalog browser passes none
 * (uses each primitive's defaults).
 */
"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { previewSignalPrimitive } from "@/lib/api";
import type { SignalPreviewResponse } from "@/lib/contracts";
import { cn } from "@/lib/utils";

interface Props {
  primitiveId: string;
  symbol?: string;
  days?: number;
  /** Optional parameter overrides — e.g. {period: 21} for RSI(21). */
  params?: Record<string, string | number>;
  className?: string;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; data: SignalPreviewResponse }
  | { kind: "error"; message: string };

export function SignalPreviewChart({
  primitiveId,
  symbol = "SPY",
  days = 252,
  params,
  className,
}: Props) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    previewSignalPrimitive(primitiveId, { symbol, days, paramOverrides: params })
      .then((data) => {
        if (!cancelled) setState({ kind: "ready", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Preview failed";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
    // Stable-stringify params so a same-shape object on re-render
    // doesn't re-fetch.
  }, [primitiveId, symbol, days, JSON.stringify(params ?? {})]);

  if (state.kind === "loading") {
    return (
      <div
        data-testid="preview-chart-skeleton"
        className={cn(
          "h-40 w-full animate-pulse rounded-md bg-slate-100",
          className,
        )}
      />
    );
  }
  if (state.kind === "error") {
    return (
      <div
        className={cn(
          "flex h-40 w-full items-center justify-center rounded-md border border-rose-200 bg-rose-50 px-4",
          className,
        )}
      >
        <p className="text-[12px] text-rose-700">{state.message}</p>
      </div>
    );
  }

  const chartData = state.data.series.map((pt) => ({
    date: pt.date,
    value: pt.value,
  }));

  return (
    <div
      data-testid={`preview-chart-${primitiveId}`}
      className={cn("h-40 w-full", className)}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#64748b" }}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#64748b" }}
            width={36}
            domain={["auto", "auto"]}
          />
          <Tooltip
            wrapperStyle={{ fontSize: 12 }}
            labelStyle={{ color: "#0f172a" }}
            formatter={(v) =>
              typeof v === "number" ? v.toFixed(3) : String(v ?? "")
            }
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#0ea5e9"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
