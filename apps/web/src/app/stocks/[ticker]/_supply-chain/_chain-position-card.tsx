"use client";

import { TierBadge } from "@/components/stocks/tier-badge";
import type { EvidenceTier, SupplyChainSummary } from "@/lib/contracts";

const VERDICT_LABEL: Record<string, string> = {
  chokepoint: "Chokepoint",
  adjacent_supplier: "Adjacent supplier",
  theme_exposure: "Theme exposure",
  no_chain_structure: "Doesn't apply here",
  insufficient_evidence: "Insufficient evidence",
};

// theme_exposure / no_chain_structure / insufficient_evidence are deliberately
// muted — a chokepoint should never be visually "downgraded" into them, and
// these are correct, useful answers, not failed tests.
function verdictClass(v: string): string {
  if (v === "chokepoint") return "border-primary/30 bg-primary/10 text-primary";
  if (v === "adjacent_supplier") return "border-border bg-muted text-foreground/80";
  return "border-border bg-muted/60 text-muted-foreground";
}

function tierMix(summary: SupplyChainSummary): Array<[EvidenceTier, number]> {
  const counts: Partial<Record<EvidenceTier, number>> = {};
  for (const t of summary.tests) {
    counts[t.evidence_tier] = (counts[t.evidence_tier] ?? 0) + 1;
  }
  return (["A", "B", "C", "D", "E", "F"] as EvidenceTier[])
    .filter((t) => counts[t])
    .map((t) => [t, counts[t] as number]);
}

/**
 * PRD-26: the headline of the Supply Chain tab. One card, one verdict, one
 * confidence — plus the layer/vertical/stage and (when extracted) the break
 * statement and evidence mix. Renders a first-class state for
 * `no_chain_structure` (a confident "doesn't apply here", never an error).
 */
export function ChainPositionCard({ summary }: { summary: SupplyChainSummary }) {
  const v = summary.verdict;

  if (v === "no_chain_structure") {
    return (
      <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
        <div className="mb-2 text-base font-medium">Supply-chain analysis doesn&apos;t apply here</div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {summary.message ??
            "This company's economics are not driven by a physical input chain."}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          {summary.fallback_role && (
            <span className="rounded-full border border-border bg-muted px-3 py-1 text-muted-foreground">
              Sector role: {summary.fallback_role}
            </span>
          )}
          <span className="text-muted-foreground">Confidence: {summary.confidence}</span>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          The Fundamental and News lenses are the relevant views for this company.
        </p>
      </div>
    );
  }

  const mix = tierMix(summary);
  return (
    <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Chain position
        </span>
        <span className={`rounded-full border px-3 py-0.5 text-xs font-medium ${verdictClass(v)}`}>
          {VERDICT_LABEL[v] ?? v}
        </span>
      </div>

      {(summary.layer || summary.vertical || (summary.stage && summary.stage !== "unknown")) && (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          {summary.layer && (
            <span>
              Layer: <span className="font-medium capitalize">{summary.layer.replace(/_/g, " ")}</span>
            </span>
          )}
          {summary.vertical && (
            <span>
              Vertical: <span className="font-medium capitalize">{summary.vertical.replace(/_/g, " ")}</span>
            </span>
          )}
          {summary.stage && summary.stage !== "unknown" && (
            <span>
              Stage: <span className="font-medium capitalize">{summary.stage.replace(/_/g, "-")}</span>
              {!summary.trailing_metrics_meaningful && (
                <span className="ml-2 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-700 dark:text-amber-400">
                  trailing metrics not meaningful
                </span>
              )}
            </span>
          )}
        </div>
      )}

      {summary.break_statement && (
        <blockquote className="mt-3 border-l-2 border-primary/40 pl-3 text-sm leading-relaxed text-foreground">
          {summary.break_statement}
        </blockquote>
      )}
      {summary.message && !summary.break_statement && (
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{summary.message}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          Confidence: <span className="font-medium capitalize">{summary.confidence.replace(/_/g, " ")}</span>
        </span>
        {mix.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            Evidence
            {mix.map(([t, n]) => (
              <span key={t} className="inline-flex items-center gap-1">
                <TierBadge tier={t} /> {n}
              </span>
            ))}
          </span>
        )}
        {summary.dropped_edge_count > 0 && (
          <span title="Relationships discarded for lacking a verifiable source">
            {summary.dropped_edge_count} discarded
          </span>
        )}
      </div>
    </div>
  );
}
