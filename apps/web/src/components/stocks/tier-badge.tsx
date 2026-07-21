"use client";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { EvidenceTier } from "@/lib/contracts";
import { tierMeta } from "@/lib/evidence-tiers";

/**
 * PRD-26: the atomic trust unit. A small tier pill (A–F) with a hover tooltip
 * carrying the plain-language tier meaning — users learn the ladder one hover
 * at a time, not from a legend. Reused in the evidence table, cards, and inline
 * in prose.
 */
export function TierBadge({ tier, className }: { tier: EvidenceTier; className?: string }) {
  const meta = tierMeta(tier);
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex h-5 min-w-[1.25rem] cursor-help items-center justify-center rounded border px-1 font-mono text-[11px] font-medium leading-none",
              meta.badgeClass,
              className
            )}
            aria-label={`Evidence tier ${tier}`}
          >
            {tier}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[280px] leading-relaxed">
          <span className="font-semibold">Tier {tier}</span> — {meta.meaning}
          <span className="mt-1 block text-background/70">{meta.examples}</span>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
