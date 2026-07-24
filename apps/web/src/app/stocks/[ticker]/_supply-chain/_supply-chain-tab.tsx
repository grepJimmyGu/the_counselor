"use client";

import { useEffect, useState } from "react";

import { EvidenceTable } from "@/components/stocks/evidence-table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getBottleneckThesis,
  getSupplyChainEvidence,
  getSupplyChainGraph,
  getSupplyChainSummary,
} from "@/lib/api";
import type {
  BottleneckThesis,
  ChainGraph,
  EvidenceLedgerRow,
  EvidenceRow,
  SupplyChainSummary,
} from "@/lib/contracts";

import { ChainDiagram } from "./_chain-diagram";
import { ChainPositionCard } from "./_chain-position-card";
import { ThesisPanel } from "./_thesis-panel";

function toEvidenceRows(rows: EvidenceLedgerRow[]): EvidenceRow[] {
  return rows.map((r) => ({
    claim: r.claim,
    tier: r.evidence_tier,
    source: r.source_doc_type ?? "—",
    source_url: r.source_url,
    as_of_date: r.as_of_date,
    falsifier: r.falsifier,
  }));
}

/**
 * PRD-26: the Supply Chain tab. Fetches the summary + graph + evidence for the
 * ticker and renders the chain-position verdict, the chain diagram, and the
 * evidence ledger. Honest empty/degraded states throughout — a bank shows
 * "doesn't apply here"; a name without extracted evidence shows the verdict +
 * a "being mapped" graph rather than a blank or an error.
 */
export function SupplyChainTab({ symbol }: { symbol: string }) {
  const [summary, setSummary] = useState<SupplyChainSummary | null>(null);
  const [graph, setGraph] = useState<ChainGraph | null>(null);
  const [evidence, setEvidence] = useState<EvidenceLedgerRow[]>([]);
  const [thesis, setThesis] = useState<BottleneckThesis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Defer the state resets out of the synchronous effect body (mirrors the
    // page's own loader) so we don't trip react-hooks/set-state-in-effect.
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      Promise.all([
        getSupplyChainSummary(symbol),
        getSupplyChainGraph(symbol),
        getSupplyChainEvidence(symbol),
        // The thesis is enrichment — a failure must not sink the whole tab.
        getBottleneckThesis(symbol).catch(() => null),
      ])
        .then(([s, g, e, th]) => {
          if (cancelled) return;
          setSummary(s);
          setGraph(g);
          setEvidence(e);
          setThesis(th);
        })
        .catch((err) => {
          if (!cancelled) setError(err?.message || "Failed to load supply-chain data");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [symbol]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="rounded-xl border border-border bg-white p-5 text-center text-sm text-muted-foreground shadow-sm">
        {error || "Supply-chain data is unavailable for this company."}
      </div>
    );
  }

  const isNoChain = summary.verdict === "no_chain_structure";
  const evidenceRows = toEvidenceRows(evidence);

  return (
    <div className="space-y-4">
      <ChainPositionCard summary={summary} />

      {!isNoChain && graph && <ChainDiagram graph={graph} symbol={symbol} />}

      {!isNoChain && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-sm">
          <h3 className="mb-3 font-heading text-sm font-semibold">Evidence</h3>
          {evidenceRows.length > 0 ? (
            <EvidenceTable rows={evidenceRows} />
          ) : (
            <p className="text-xs text-muted-foreground">
              No sourced claims yet — the evidence ledger fills as relationships are extracted from
              filings.
            </p>
          )}
        </section>
      )}

      {!isNoChain && thesis && !thesis.message && <ThesisPanel thesis={thesis} />}

      <p className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        Structure and evidence only — never a recommendation. Every claim shown carries a source and
        an evidence tier.
      </p>
    </div>
  );
}
