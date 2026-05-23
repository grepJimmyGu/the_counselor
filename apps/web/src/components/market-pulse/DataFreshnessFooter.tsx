"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { getDataLatency } from "@/lib/api";
import type {
  DataLatencyResponse,
  DataLatencySource,
  DataLatencyStatus,
} from "@/lib/contracts";

/**
 * Phase 1g — Market Pulse data freshness footer.
 *
 * Renders one terse line at the foot of `/stocks`:
 *
 *   ✓ Snapshot as of May 22 · oldest source: 0h
 *
 * Hover (or `details` click on touch devices) expands a per-group
 * breakdown so users can see WHICH data source is stale. Backend
 * `/api/market/data-latency` consolidates the answer in one call so
 * the component only fires a single fetch on mount.
 *
 * Status colors mirror Jimmy's preferred semantic palette (emerald
 * for fresh, amber for stale, red for very_stale / missing).
 */

export function DataFreshnessFooter() {
  const [data, setData] = useState<DataLatencyResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDataLatency()
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch(() => {
        /* silent — footer is a nice-to-have */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return (
      <div className="text-[10px] text-muted-foreground/40">
        Checking data freshness…
      </div>
    );
  }

  const StatusIcon = _iconForStatus(data.overall_status);
  const statusColor = _colorForStatus(data.overall_status);

  return (
    <details className="group text-[10px] text-muted-foreground">
      <summary className="cursor-pointer list-none flex items-center gap-1.5 select-none">
        <StatusIcon className={cn("h-3 w-3", statusColor)} />
        <span>
          Snapshot as of{" "}
          <span className="font-mono">{_fmtDate(data.overall_latest_date)}</span>
          {data.overall_hours_stale != null && (
            <>
              {" · oldest source: "}
              <span className="font-mono">{_fmtHours(data.overall_hours_stale)}</span>
            </>
          )}
        </span>
        <span className="text-muted-foreground/40 group-open:hidden">(details)</span>
      </summary>
      <div className="mt-2 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-4">
        {data.sources.map((s) => (
          <SourceCard key={s.group} source={s} />
        ))}
      </div>
    </details>
  );
}

function SourceCard({ source }: { source: DataLatencySource }) {
  const Icon = _iconForStatus(source.status);
  const color = _colorForStatus(source.status);
  return (
    <div className="rounded-md border border-border/60 bg-white/40 px-2 py-1.5">
      <div className="flex items-center justify-between gap-1.5">
        <span className="font-semibold text-foreground/80">{source.group}</span>
        <Icon className={cn("h-3 w-3", color)} />
      </div>
      <div className="text-[10px] text-muted-foreground/80">{source.description}</div>
      <div className="mt-1 font-mono text-[10px]">
        {_fmtDate(source.latest_date)}
        {source.hours_stale != null && (
          <> · {_fmtHours(source.hours_stale)}</>
        )}
      </div>
    </div>
  );
}

// ── helpers ──────────────────────────────────────────────────────────────────

function _iconForStatus(status: DataLatencyStatus) {
  switch (status) {
    case "fresh":
      return CheckCircle2;
    case "stale":
      return AlertCircle;
    case "very_stale":
      return AlertTriangle;
    case "missing":
      return XCircle;
  }
}

function _colorForStatus(status: DataLatencyStatus): string {
  switch (status) {
    case "fresh":
      return "text-emerald-600";
    case "stale":
      return "text-amber-600";
    case "very_stale":
      return "text-orange-600";
    case "missing":
      return "text-red-500";
  }
}

function _fmtDate(iso: string | null): string {
  if (!iso) return "—";
  // Manual parse to avoid timezone drift (new Date("2025-05-21") is UTC midnight)
  const [_y, m, d] = iso.split("-");
  if (!m || !d) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
}

function _fmtHours(hours: number): string {
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
