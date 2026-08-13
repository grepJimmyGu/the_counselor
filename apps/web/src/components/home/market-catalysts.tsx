"use client";

/**
 * Home block 5 — **Catalysts**.
 *
 * The five `kind: "sentiment"` starting points from `RECOMMENDED_TEMPLATES`,
 * over the live news ticker.
 *
 * WHY THESE FIVE ARE HERE AND NOT IN HOT MARKET PICKS. A sentiment template is
 * LLM-mediated — it has a `toolkit_id`, not `rules`, so it cannot be handed to
 * a scan and cannot produce a stock list. Hot Market Picks promises "click and
 * see the names"; these can't keep that promise, and mixing them in would make
 * the promise unreliable rather than making these cards useful.
 *
 * WHY THE TICKER MOVED. It lived at the bottom of "Traders ask", where it was
 * unrelated to the block's subject and consumed more height than the questions
 * did — most of why that block read as empty. Here it has a subject in common
 * with what sits above it: the headline tells you something happened, the
 * catalyst entry is how you act on it.
 */

import { StartingPointCard } from "@/components/screen/starting-point-card";
import { sentimentTemplateHref } from "@/lib/flows/bricks/recommended-templates-gallery";
import { RECOMMENDED_TEMPLATES } from "@/lib/recommended-templates";

import { MarketNewsTicker } from "./market-news-ticker";

const CATALYSTS = RECOMMENDED_TEMPLATES.filter(
  (t): t is Extract<typeof t, { kind: "sentiment" }> => t.kind === "sentiment",
);

export function MarketCatalysts() {
  return (
    <section
      className="rounded-xl border border-border bg-white p-4"
      data-testid="home-catalysts"
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-semibold">Catalysts</h2>
        <span className="text-xs text-muted-foreground">
          What just happened, and how to read it
        </span>
      </div>

      {/* Three across at lg: this block is full-width beneath the 2×2, so it
          has the room the others don't. */}
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {CATALYSTS.map((t) => (
          <StartingPointCard
            key={t.id}
            t={t}
            density="compact"
            href={sentimentTemplateHref(t)}
            testId={`home-catalyst-${t.id}`}
          />
        ))}
      </div>

      <MarketNewsTicker />
    </section>
  );
}
