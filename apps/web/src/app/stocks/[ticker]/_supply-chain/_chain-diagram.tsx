"use client";

import { useState } from "react";

import { TierBadge } from "@/components/stocks/tier-badge";
import type { ChainEdge, ChainGraph } from "@/lib/contracts";

/**
 * PRD-26: the chain diagram. Suppliers (upstream) → this company → customers
 * (downstream), each relationship carrying an evidence tier and a verbatim
 * quote revealed on click. Until extraction fills the graph, renders a
 * first-class "being mapped" empty state rather than a blank panel.
 *
 * The richer layer-by-layer column diagram (constrained/abundant/unknown per
 * layer) lands once extraction supplies layer data.
 */
export function ChainDiagram({ graph, symbol }: { graph: ChainGraph; symbol: string }) {
  const [active, setActive] = useState<ChainEdge | null>(null);

  if (graph.edges.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-muted/20 p-5 text-center">
        <p className="text-sm font-medium text-foreground">The supply-chain graph is being mapped</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Sourced supplier and customer relationships will appear here as they&apos;re extracted from
          filings — each edge carries a verbatim quote and an evidence tier, or it isn&apos;t shown.
        </p>
      </div>
    );
  }

  const isTarget = (sym: string | null | undefined, name: string) =>
    (sym && sym.toUpperCase() === symbol) || name.toUpperCase() === symbol;
  const upstream = graph.edges.filter((e) => isTarget(e.target_symbol, e.target_name));
  const downstream = graph.edges.filter((e) => isTarget(e.source_symbol, e.source_name));

  const chip = (e: ChainEdge, label: string, key: string) => (
    <button
      key={key}
      type="button"
      onClick={() => setActive(e)}
      className={`block w-full truncate rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors hover:border-primary/40 ${
        active === e ? "border-primary/50 bg-primary/5" : "border-border bg-white"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Suppliers (upstream)
          </div>
          <div className="space-y-1.5">
            {upstream.length ? (
              upstream.map((e, i) => chip(e, e.source_symbol || e.source_name, `up-${i}`))
            ) : (
              <p className="text-xs text-muted-foreground">—</p>
            )}
          </div>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            This company
          </div>
          <div className="rounded-lg border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-center font-mono text-sm font-semibold text-primary">
            {symbol}
          </div>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Customers (downstream)
          </div>
          <div className="space-y-1.5">
            {downstream.length ? (
              downstream.map((e, i) => chip(e, e.target_symbol || e.target_name, `down-${i}`))
            ) : (
              <p className="text-xs text-muted-foreground">—</p>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-border pt-3 text-xs">
        {active ? (
          <div>
            <div className="mb-1 flex items-center gap-2 font-medium">
              {active.source_name} → {active.target_name} <TierBadge tier={active.evidence_tier} />
            </div>
            <p className="italic leading-relaxed text-foreground">{active.quote}</p>
            <p className="mt-1 text-muted-foreground">
              {active.source_url ? (
                <a
                  href={active.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-foreground hover:underline"
                >
                  {active.source_doc_type}
                </a>
              ) : (
                active.source_doc_type
              )}
              {" · "}
              {active.as_of_date}
              {active.stale ? " · stale" : ""}
            </p>
          </div>
        ) : (
          <p className="text-muted-foreground">Click a relationship to see its sourced quote.</p>
        )}
      </div>
    </div>
  );
}
