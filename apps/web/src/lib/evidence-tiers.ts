import type { EvidenceTier } from "@/lib/contracts";

/**
 * The six-tier evidence ladder, for the frontend.
 *
 * Canonical source of truth:
 *   agent-system/skills/bottleneck-research/references/evidence-ladder.md
 * A Claude skill markdown file cannot be imported by the client bundle, so the
 * six definitions are duplicated here. If the ladder changes, update BOTH.
 *
 * The tier of a claim is assigned by the TYPE of its source — never by a
 * model's self-assessment. "Never launder a tier": an unknown source is graded
 * down (Tier D), never up.
 */

export interface TierMeta {
  tier: EvidenceTier;
  /** One-line meaning, shown in the badge tooltip. */
  meaning: string;
  /** Representative sources at this tier. */
  examples: string;
  /** Tailwind classes for the badge pill. */
  badgeClass: string;
}

export const EVIDENCE_TIERS: Record<EvidenceTier, TierMeta> = {
  A: {
    tier: "A",
    meaning: "Can validate or falsify — the only sources that can kill a thesis.",
    examples: "Filings (10-K/20-F/8-K), transcripts, official releases, award notices.",
    badgeClass: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  B: {
    tier: "B",
    meaning: "Strong validation — named, disclosed commercial commitments.",
    examples: "Named design wins, purchase orders, take-or-pay contracts, qualification language.",
    badgeClass: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-400",
  },
  C: {
    tier: "C",
    meaning: "Above inference, below revenue — a real bar passed, but not revenue.",
    examples: "Reference-design inclusion, foundry-platform listing, evaluation programs.",
    badgeClass: "border-border bg-muted text-foreground/70",
  },
  D: {
    tier: "D",
    meaning: "Supports the map, not the thesis — builds the chain, doesn't assert a deal.",
    examples: "Partner pages, patents, papers, BOM estimates, industry-report shares.",
    badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  E: {
    tier: "E",
    meaning: "Context — check incentives. A peer transcript beats a target's own claim.",
    examples: "Peer transcripts, sell-side notes, analyst estimates, trade press.",
    badgeClass: "border-border bg-muted/50 text-muted-foreground",
  },
  F: {
    tier: "F",
    meaning: "Hypothesis generation only — never cite as support for a conclusion.",
    examples: "Social posts, third-party trackers, search snippets, LLM output.",
    badgeClass: "border border-dashed border-border bg-transparent text-muted-foreground italic",
  },
};

export const TIER_ORDER: readonly EvidenceTier[] = ["A", "B", "C", "D", "E", "F"] as const;

export function tierMeta(tier: EvidenceTier): TierMeta {
  return EVIDENCE_TIERS[tier];
}

/**
 * Infer an evidence tier from a free-text source label, following the ladder's
 * source-type rules. Used to grade the per-record `source_notes` we already
 * store, until the extraction backend assigns per-claim tiers directly.
 *
 * Conservative by design: an unrecognised source falls to Tier D ("supports the
 * map"), never to A/B — we never launder an unknown source up the ladder.
 */
export function inferTierFromSource(source: string): EvidenceTier {
  const s = source.toLowerCase();
  // Tier E — context, incentive-laden. Checked first so a *peer* transcript
  // is not mistaken for a company's own earnings-call transcript (Tier A).
  if (/\b(peer[- ]?(company )?transcript|sell-side|analyst (estimate|note)|expert network|trade press)\b/.test(s)) {
    return "E";
  }
  // Tier A — primary disclosure that can validate or kill a thesis.
  if (/\b(10-?k|20-?f|8-?k|s-1|13[dg]|annual report|interim report|filing|transcript|earnings call|official (release|statement)|award notice|export[- ]control)\b/.test(s)) {
    return "A";
  }
  // Tier B — named, disclosed commercial commitment.
  if (/\b(design win|purchase order|take-or-pay|multi-year agreement|qualified customer|customer qualification|signed[a-z ]*contract)\b/.test(s)) {
    return "B";
  }
  // Tier C — a real bar passed, but not revenue.
  if (/\b(reference design|foundry (platform|list)|qualified-supplier|ecosystem member|evaluation program)\b/.test(s)) {
    return "C";
  }
  // Tier F — leads only.
  if (/\b(social|reddit|twitter|tracker|search snippet|aggregator|llm|model-generated)\b/.test(s)) {
    return "F";
  }
  // Tier D — the map (partner pages, papers, industry data) and everything
  // unrecognised. Conservative default: never launder unknowns up the ladder.
  return "D";
}
