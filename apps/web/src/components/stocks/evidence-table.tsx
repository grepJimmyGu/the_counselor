"use client";

import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EvidenceRow, EvidenceTier } from "@/lib/contracts";
import { TIER_ORDER } from "@/lib/evidence-tiers";
import { TierBadge } from "./tier-badge";

function tierRank(t: EvidenceTier): number {
  return TIER_ORDER.indexOf(t);
}

function sortByTier(rows: EvidenceRow[]): EvidenceRow[] {
  return [...rows].sort((a, b) => tierRank(a.tier) - tierRank(b.tier));
}

/**
 * Tier-mix summary — always shown above the rows. An all-D basket tells its
 * story at a glance ("4A · 2B · 0C · 3D").
 */
function TierMix({ rows }: { rows: EvidenceRow[] }) {
  const counts = rows.reduce<Partial<Record<EvidenceTier, number>>>((acc, r) => {
    acc[r.tier] = (acc[r.tier] ?? 0) + 1;
    return acc;
  }, {});
  const present = TIER_ORDER.filter((t) => counts[t]);
  if (present.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      <span className="font-medium">Evidence mix</span>
      {present.map((t) => (
        <span key={t} className="inline-flex items-center gap-1">
          <TierBadge tier={t} />
          <span className="font-mono">{counts[t]}</span>
        </span>
      ))}
    </div>
  );
}

interface EvidenceTableProps {
  rows: EvidenceRow[];
  /**
   * Compact: source + tier only — the per-record provenance we surface today.
   * Full (default): claim / tier / source / date / falsifier — the per-claim
   * table the extraction backend populates (Slice 2+).
   */
  compact?: boolean;
  className?: string;
}

/**
 * PRD-26: reusable, page-wide evidence table. The tier badge is the only
 * coloured element per row — it is the thing being communicated. Rows sort
 * strongest-first; empty falsifier/date cells render as "—", never blank.
 */
export function EvidenceTable({ rows, compact = false, className }: EvidenceTableProps) {
  if (rows.length === 0) return null;
  const sorted = sortByTier(rows);

  return (
    <div className={cn("space-y-2", className)}>
      <TierMix rows={rows} />

      {compact ? (
        <ul className="space-y-1.5">
          {sorted.map((r, i) => (
            <li key={`${r.claim}-${i}`} className="flex items-start gap-2 text-xs">
              <TierBadge tier={r.tier} className="mt-0.5 shrink-0" />
              <span className="leading-relaxed text-foreground/80">{r.claim}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="pb-1.5 pr-3 text-left font-medium">Claim</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Tier</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Source</th>
                <th className="pb-1.5 pr-3 text-left font-medium">Date</th>
                <th className="pb-1.5 text-left font-medium">What would falsify it</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={`${r.claim}-${i}`} className="border-b border-border/30 align-top last:border-0">
                  <td className="py-2 pr-3 text-foreground/85">{r.claim}</td>
                  <td className="py-2 pr-3">
                    <TierBadge tier={r.tier} />
                  </td>
                  <td className="py-2 pr-3 text-muted-foreground">
                    {r.source_url ? (
                      <a
                        href={r.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 hover:text-foreground hover:underline"
                      >
                        {r.source}
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    ) : (
                      r.source
                    )}
                  </td>
                  <td className="py-2 pr-3 font-mono text-muted-foreground">{r.as_of_date ?? "—"}</td>
                  <td className="py-2 text-muted-foreground">{r.falsifier ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
