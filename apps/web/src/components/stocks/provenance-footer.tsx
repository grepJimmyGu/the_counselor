"use client";

import type { EvidenceRow } from "@/lib/contracts";
import { inferTierFromSource } from "@/lib/evidence-tiers";
import { EvidenceTable } from "./evidence-table";

/**
 * PRD-26 P1: surface the provenance we already store instead of discarding it
 * at the view layer. Renders a section's `confidence` + its `source_notes`,
 * each graded against the evidence ladder.
 *
 * This is the per-record provenance we have today. Per-claim tiers, dates and
 * quote spans arrive with the extraction backend — this component swaps to the
 * full (non-compact) evidence table then, with no caller changes.
 */
export function ProvenanceFooter({
  confidence,
  sourceNotes,
}: {
  confidence: string;
  sourceNotes: string[];
}) {
  const notes = sourceNotes.filter((n) => n && n.trim().length > 0);
  if (notes.length === 0 && !confidence) return null;

  const rows: EvidenceRow[] = notes.map((note) => ({
    claim: note,
    tier: inferTierFromSource(note),
    source: note,
  }));

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3.5">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Sources &amp; evidence
        </span>
        {confidence && (
          <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] font-medium capitalize text-muted-foreground">
            {confidence} confidence
          </span>
        )}
      </div>
      {rows.length > 0 ? (
        <EvidenceTable rows={rows} compact />
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Underlying sources are not itemised for this section yet.
        </p>
      )}
    </div>
  );
}
