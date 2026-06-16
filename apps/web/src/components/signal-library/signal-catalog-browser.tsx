/**
 * PRD-16a-4 — SignalCatalogBrowser.
 *
 * The catalog UI: 8-category filter sidebar + search bar + grid of
 * `<SignalPrimitiveCard>`. Fetches the catalog via `getSignalPrimitives`,
 * which uses the localStorage cache so re-renders are instant.
 *
 * The composer (PRD-16b) wraps this brick. The browser surfaces a
 * `onPick(primitive)` callback for the composer to consume; in
 * standalone mode (the `/signal-library` page, if/when it ships), no
 * callback is wired and clicking a card is a no-op.
 */
"use client";

import { useEffect, useMemo, useState } from "react";

import { getSignalPrimitives } from "@/lib/api";
import type {
  SignalCategory,
  SignalOutputKind,
  SignalPrimitive,
} from "@/lib/contracts";
import { SIGNAL_CATEGORY_LABEL } from "@/lib/contracts";
import { cn } from "@/lib/utils";

import { SignalPrimitiveCard } from "./signal-primitive-card";

// PRD-22c: filter the catalog by semantic kind (multi-select; empty = all).
const ALL_KINDS: SignalOutputKind[] = [
  "value", "event", "level", "cross", "regime", "distance", "divergence",
];
const KIND_LABEL: Record<SignalOutputKind, string> = {
  value: "Value",
  event: "Event",
  level: "Level",
  cross: "Cross",
  regime: "Regime",
  distance: "Distance",
  divergence: "Divergence",
};

interface Props {
  onPick?: (primitive: SignalPrimitive) => void;
  /** Set of primitive IDs the user has already selected. Passed through
   *  to each `<SignalPrimitiveCard>` so they render with the selected
   *  state. Empty set in standalone mode. */
  selectedIds?: Set<string>;
  className?: string;
}

export function SignalCatalogBrowser({
  onPick,
  selectedIds,
  className,
}: Props) {
  const [primitives, setPrimitives] = useState<SignalPrimitive[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeCategory, setActiveCategory] = useState<SignalCategory | "all">("all");
  const [activeKinds, setActiveKinds] = useState<Set<SignalOutputKind>>(new Set());
  const [query, setQuery] = useState("");

  const toggleKind = (k: SignalOutputKind) =>
    setActiveKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSignalPrimitives()
      .then((resp) => {
        if (cancelled) return;
        setPrimitives(resp.primitives);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Catalog fetch failed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const lowerQ = query.trim().toLowerCase();
    return primitives.filter((p) => {
      if (activeCategory !== "all" && p.category !== activeCategory) return false;
      if (activeKinds.size > 0 && !activeKinds.has(p.output_kind)) return false;
      if (!lowerQ) return true;
      return (
        p.name.toLowerCase().includes(lowerQ) ||
        p.description.toLowerCase().includes(lowerQ) ||
        p.family.toLowerCase().includes(lowerQ) ||
        p.id.toLowerCase().includes(lowerQ)
      );
    });
  }, [primitives, activeCategory, activeKinds, query]);

  // Counts per category for the sidebar. Computed off the FULL list,
  // not the filtered one — the sidebar shows the same numbers regardless
  // of which category is active.
  const counts = useMemo(() => {
    const c: Record<SignalCategory | "all", number> = {
      all: primitives.length,
      trend: 0,
      mean_reversion: 0,
      momentum: 0,
      volume: 0,
      volatility: 0,
      fundamental: 0,
      sentiment: 0,
      cross_sectional: 0,
    };
    for (const p of primitives) c[p.category] += 1;
    return c;
  }, [primitives]);

  if (loading && primitives.length === 0) {
    return (
      <div className={cn("flex h-64 items-center justify-center", className)}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-slate-700" />
      </div>
    );
  }
  if (error) {
    return (
      <div
        className={cn(
          "rounded-lg border border-rose-200 bg-rose-50 p-4",
          className,
        )}
      >
        <p className="text-sm text-rose-700">{error}</p>
      </div>
    );
  }

  const categories: (SignalCategory | "all")[] = [
    "all",
    "trend",
    "mean_reversion",
    "momentum",
    "volume",
    "volatility",
    "fundamental",
    "sentiment",
    "cross_sectional",
  ];

  return (
    <div
      data-testid="signal-catalog-browser"
      className={cn("grid grid-cols-1 gap-6 md:grid-cols-[180px_1fr]", className)}
    >
      <aside className="flex flex-col gap-1">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Category
        </p>
        {categories.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setActiveCategory(c)}
            data-testid={`category-${c}`}
            className={cn(
              "flex items-center justify-between rounded-md px-3 py-1.5 text-left text-[13px] transition",
              activeCategory === c
                ? "bg-slate-900 text-white"
                : "text-slate-700 hover:bg-slate-100",
            )}
          >
            <span>{c === "all" ? "All" : SIGNAL_CATEGORY_LABEL[c]}</span>
            <span
              className={cn(
                "text-[11px] tabular-nums",
                activeCategory === c ? "text-slate-200" : "text-slate-400",
              )}
            >
              {counts[c]}
            </span>
          </button>
        ))}
      </aside>

      <div className="flex flex-col gap-4">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search primitives by name, description, or family…"
          data-testid="catalog-search"
          className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200"
        />

        {/* PRD-22c — filter by semantic kind (multi-select; none = all). */}
        <div className="flex flex-wrap gap-1.5" data-testid="kind-filter">
          {ALL_KINDS.map((k) => {
            const on = activeKinds.has(k);
            return (
              <button
                key={k}
                type="button"
                onClick={() => toggleKind(k)}
                data-testid={`kind-chip-${k}`}
                aria-pressed={on}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-[12px] transition",
                  on
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 text-slate-600 hover:bg-slate-100",
                )}
              >
                {KIND_LABEL[k]}
              </button>
            );
          })}
        </div>

        {filtered.length === 0 ? (
          <p
            data-testid="catalog-empty"
            className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-[13px] text-slate-500"
          >
            No primitives match your filters.
          </p>
        ) : (
          <div
            className="grid grid-cols-1 gap-3 lg:grid-cols-2"
            data-testid="catalog-grid"
          >
            {filtered.map((p) => (
              <SignalPrimitiveCard
                key={p.id}
                primitive={p}
                onClick={onPick}
                selected={selectedIds?.has(p.id) ?? false}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
