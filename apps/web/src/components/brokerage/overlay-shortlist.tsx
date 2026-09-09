"use client";

/**
 * <OverlayShortlist> — the six overlays as six lines.
 *
 * REPLACES a grid of six <StrategyCard>s that measured 8,138px on its own and
 * made the page 9,831px tall, with the flow's own CTA sitting in the final
 * 0.7% of it. Those cards are right where the CHOICE is made — the picker
 * step — and wrong as a wall between someone and the button.
 *
 * WHAT THE READER NEEDS HERE is not six research cards; it is one fact: is
 * there anything here for MY book. So the summary leads with the count that
 * qualifies, which is computable now that this renders beside real holdings —
 * and on a concentrated book "1 of 6 fits" is a finding about concentration,
 * not a catalogue.
 *
 * ⚠ NO PERFORMANCE FIGURE IN A ROW. A collapsed line cannot carry the basis a
 * claim needs, so rows use `oneLine` (what it does) and never `tagline`, which
 * embeds "−28% vs −55%" and cannot travel apart from `historicalEstimate`.
 * That rule is what makes compaction safe rather than merely shorter.
 *
 * Works off typed holdings as readily as broker ones — it only reads a count,
 * so someone who pastes four tickers sees their fits without connecting.
 */

import { OVERLAY_DISPLAY_ORDER, OVERLAY_METADATA } from "@/lib/overlay-metadata";

export function OverlayShortlist({
  holdingsCount,
  title,
  emptyHint,
}: {
  holdingsCount: number;
  title: string;
  /** Shown instead of the fit count while the book is still empty. */
  emptyHint: string;
}) {
  const total = OVERLAY_DISPLAY_ORDER.length;
  const fits = OVERLAY_DISPLAY_ORDER.filter(
    (k) => holdingsCount >= OVERLAY_METADATA[k].minHoldings,
  ).length;

  return (
    <details className="rounded-lg border border-border bg-card px-3.5 py-2.5">
      <summary
        className="flex cursor-pointer list-none items-baseline justify-between gap-3 text-[13px] marker:hidden"
        data-testid="overlay-shortlist-summary"
      >
        <span className="font-semibold text-foreground">{title}</span>
        <span className="text-muted-foreground">
          {holdingsCount === 0 ? (
            <>
              {total} overlays &middot;{" "}
              <span className="font-medium text-foreground">{emptyHint}</span>
            </>
          ) : (
            <span
              className={
                "font-medium " + (fits === 0 ? "text-amber-700" : "text-foreground")
              }
              data-testid="overlay-shortlist-fit"
            >
              {fits} of {total} fit{fits === 1 ? "s" : ""} this book
            </span>
          )}
        </span>
      </summary>

      <div className="mt-1.5" data-testid="overlay-shortlist-rows">
        {OVERLAY_DISPLAY_ORDER.map((kind) => {
          const meta = OVERLAY_METADATA[kind];
          const ok = holdingsCount >= meta.minHoldings;
          return (
            <div
              key={kind}
              data-testid={`overlay-row-${kind}`}
              className="grid grid-cols-[7.5rem_1fr_auto] items-baseline gap-3 border-t border-border py-1.5 text-[12.5px]"
            >
              <span className="font-medium text-foreground">{meta.label}</span>
              <span className="text-muted-foreground">{meta.oneLine}</span>
              {/* Before any holdings exist there is nothing to qualify against,
                  and "needs 3+" against an empty book reads as a refusal. */}
              {holdingsCount === 0 ? (
                <span className="text-[11px] text-muted-foreground">
                  needs {meta.minHoldings}+
                </span>
              ) : ok ? (
                <span className="text-[11px] font-semibold text-emerald-700">fits</span>
              ) : (
                <span className="text-[11px] text-muted-foreground">
                  needs {meta.minHoldings}+
                </span>
              )}
            </div>
          );
        })}
        <p className="border-t border-border pt-1.5 text-[11px] text-muted-foreground">
          The full card — track record, research, what to watch for — opens at the
          choice itself, once we&rsquo;ve diagnosed the book.
        </p>
      </div>
    </details>
  );
}
