"use client";

/**
 * "Additional metrics" — the column picker on the results table.
 *
 * Grouped by where the number comes from, because that's what decides whether
 * we can show it at all: quote fields are already fetched, fundamentals come
 * from `/api/screener/by-symbols`, technicals from the daily snapshot via
 * `/api/screen/metric-values`.
 *
 * Only metrics we can actually source are listed. A picker that offers a field
 * we can't fill produces a column of em dashes, which reads as broken data
 * rather than as an unavailable metric.
 */

import { useEffect, useRef, useState } from "react";
import { Check, Plus, X } from "lucide-react";

import { METRIC_GROUPS, type MetricDef } from "./result-metrics";

export function MetricPicker({
  selected,
  onToggle,
  onClear,
  max,
  alreadyShown = [],
}: {
  selected: string[];
  onToggle: (key: string) => void;
  onClear: () => void;
  /** Cap on ADDED metrics, mirroring the backend's per-request primitive cap. */
  max: number;
  /**
   * Keys already on the table as screened-condition columns. Screening on RSI
   * puts RSI on screen; offering it again here would add a second, identical
   * column. Hidden rather than disabled — a greyed row invites a click that
   * can never do anything.
   */
  alreadyShown?: string[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Click-outside and Escape both close it. Without the outside handler the
  // panel survives navigating the table underneath it, which reads as stuck.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: globalThis.MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const atCap = selected.length >= max;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid="metric-picker-toggle"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        Additional metrics
        {selected.length > 0 && (
          <span className="rounded-full bg-primary/10 px-1.5 text-xs font-medium text-primary">
            {selected.length}
          </span>
        )}
      </button>

      {open && (
        <div
          data-testid="metric-picker-panel"
          className="absolute left-0 z-30 mt-2 max-h-[24rem] w-72 overflow-y-auto rounded-lg border border-border bg-white p-3 shadow-lg"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Add columns
            </span>
            {selected.length > 0 && (
              <button
                type="button"
                onClick={onClear}
                data-testid="metric-picker-clear"
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>

          {/* Stated before you hit it, not after — a checkbox that silently
              refuses to tick reads as a broken control. */}
          {atCap && (
            <p className="mb-2 text-xs text-amber-700" data-testid="metric-picker-cap">
              {max} columns max. Remove one to add another.
            </p>
          )}

          {METRIC_GROUPS.map((group) => {
            const options = group.metrics.filter((m) => !alreadyShown.includes(m.key));
            if (options.length === 0) return null;
            return (
            <div key={group.key} className="mb-3 last:mb-0">
              <div className="mb-1 text-xs font-medium text-muted-foreground">{group.label}</div>
              <div className="space-y-0.5">
                {options.map((m: MetricDef) => {
                  const on = selected.includes(m.key);
                  return (
                    <button
                      key={m.key}
                      type="button"
                      role="checkbox"
                      aria-checked={on}
                      disabled={!on && atCap}
                      onClick={() => onToggle(m.key)}
                      data-testid={`metric-option-${m.key}`}
                      className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                        on ? "bg-primary/10 text-foreground" : "hover:bg-muted"
                      }`}
                    >
                      <span
                        className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${
                          on ? "border-primary bg-primary text-white" : "border-border"
                        }`}
                      >
                        {on && <Check className="h-2.5 w-2.5" aria-hidden="true" />}
                      </span>
                      {m.label}
                    </button>
                  );
                })}
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Numeric range filters over any column on screen — default, added, or
 * screened condition.
 *
 * Rendered as chips beside the condition chips, because they're the same kind
 * of thing from the user's side: something narrowing the list. The distinction
 * that matters is where they narrow. A CONDITION re-runs the screen against
 * the whole universe; a metric filter is applied client-side to the rows
 * already fetched. Mixing them up would be a real bug — filtering "P/E < 15"
 * here narrows the matched names, it does not go find new ones — so the copy
 * says so.
 */
export interface MetricFilter {
  key: string;
  min?: number;
  max?: number;
}

export function MetricFilterBar({
  columns,
  filters,
  onAdd,
  onRemove,
}: {
  /** Every column currently on screen, in table order. */
  columns: { key: string; label: string }[];
  filters: MetricFilter[];
  onAdd: (f: MetricFilter) => void;
  onRemove: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [min, setMin] = useState("");
  const [max, setMax] = useState("");

  const unfiltered = columns.filter((c) => !filters.some((f) => f.key === c.key));

  const submit = () => {
    const lo = min.trim() === "" ? undefined : Number(min);
    const hi = max.trim() === "" ? undefined : Number(max);
    // A filter with neither bound matches everything — accepting it would add
    // a chip that visibly does nothing.
    if (!key || (lo === undefined && hi === undefined)) return;
    if ((lo !== undefined && !Number.isFinite(lo)) || (hi !== undefined && !Number.isFinite(hi))) return;
    onAdd({ key, min: lo, max: hi });
    setKey("");
    setMin("");
    setMax("");
    setOpen(false);
  };

  const labelFor = (k: string) => columns.find((c) => c.key === k)?.label ?? k;

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="metric-filters">
      {filters.map((f) => (
        <span
          key={f.key}
          data-testid={`metric-filter-${f.key}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-sm"
        >
          {labelFor(f.key)}{" "}
          <span className="tabular-nums text-muted-foreground">
            {f.min !== undefined && f.max !== undefined
              ? `${f.min} – ${f.max}`
              : f.min !== undefined
                ? `≥ ${f.min}`
                : `≤ ${f.max}`}
          </span>
          <button
            type="button"
            onClick={() => onRemove(f.key)}
            aria-label={`Remove ${labelFor(f.key)} filter`}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      ))}

      {unfiltered.length > 0 && (
        <div className="relative">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            data-testid="metric-filter-toggle"
            aria-expanded={open}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Filter by metric
          </button>

          {open && (
            <div
              data-testid="metric-filter-panel"
              className="absolute left-0 z-30 mt-2 w-64 rounded-lg border border-border bg-white p-3 shadow-lg"
            >
              <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="metric-filter-key">
                Metric
              </label>
              <select
                id="metric-filter-key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                data-testid="metric-filter-key"
                className="mb-2 w-full rounded border border-border px-2 py-1 text-sm"
              >
                <option value="">Choose…</option>
                {unfiltered.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>

              <div className="mb-2 flex items-center gap-2">
                <input
                  type="number"
                  value={min}
                  onChange={(e) => setMin(e.target.value)}
                  placeholder="min"
                  aria-label="Minimum"
                  data-testid="metric-filter-min"
                  className="w-full rounded border border-border px-2 py-1 text-sm"
                />
                <span className="text-xs text-muted-foreground">to</span>
                <input
                  type="number"
                  value={max}
                  onChange={(e) => setMax(e.target.value)}
                  placeholder="max"
                  aria-label="Maximum"
                  data-testid="metric-filter-max"
                  className="w-full rounded border border-border px-2 py-1 text-sm"
                />
              </div>

              <button
                type="button"
                onClick={submit}
                data-testid="metric-filter-apply"
                className="w-full rounded bg-primary px-2 py-1 text-sm font-medium text-white transition-opacity hover:opacity-90"
              >
                Apply
              </button>
              <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                Narrows the matches above — it doesn&apos;t search the universe again.
                Add a condition for that.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
