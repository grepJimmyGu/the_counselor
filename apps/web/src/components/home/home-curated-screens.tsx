"use client";

/**
 * Home block 2 — **Hot Market Picks**.
 *
 * The five `kind: "composer"` starting points from `RECOMMENDED_TEMPLATES` —
 * the same cards, copy and category chips as the "Screen the market" gallery,
 * rendered through the same `<StartingPointCard>` at `compact` density. One
 * registry, one card component, two surfaces.
 *
 * WHY THESE FIVE AND NOT THE NINE SCREENER PRESETS. A composer template carries
 * real `rules` — `primitive_id` conditions already in the daily snapshot's
 * vocabulary — so a card can hand them straight to a scan and land the user on
 * a stock list. The `sentiment` five can't; they route to the sentiment hub, so
 * they live in the Catalysts block instead.
 *
 * "Traders ask" is its top section, merged in on 2026-08-13. The chips and the
 * picks do the same job — start a screen — and land on the same results
 * surface; typed vs ready-made is the only difference. Grouping them makes that
 * relationship visible, and it retires the `items-start` workaround the grid
 * needed when "Traders ask" was too short to stand as its own box.
 *
 * FOUR PICKS SHOWN, NOT FIVE. Five in a two-column grid leaves an orphan in row
 * three, which is what made this block 505px against its row-mate's 389px. The
 * fifth is named in a line beneath rather than dropped silently.
 *
 * ONE CLICK, STRAIGHT TO THE LIST. `/screen?template=<id>` lands on the exact
 * surface a typed search produces — same chips, same counts, same table, same
 * add-ticker. That matters beyond consistency: from there the user's next move
 * is identical to a search, so a pick is just a faster way to arrive at the
 * same working surface.
 *
 * An earlier draft routed through `/screen?q=<phrase>`, which would have made
 * every card's honesty depend on a phrase parsing back to the same set. These
 * rules ARE the scan's vocabulary, so a card cannot promise one screen and
 * return another.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";

import { StartingPointCard } from "@/components/screen/starting-point-card";
import { TradersAsk } from "@/components/home/home-example-queries";
import { screenCount } from "@/lib/api";
import { RECOMMENDED_TEMPLATES } from "@/lib/recommended-templates";

/** The composer five, in registry order. */
const PICKS = RECOMMENDED_TEMPLATES.filter(
  (t): t is Extract<typeof t, { kind: "composer" }> => t.kind === "composer",
);

export function HomeCuratedScreens() {
  /** id → live match count. Absent = still counting. */
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    // Counted per card, in parallel: each lands on its own so one slow scan
    // never holds up the rest of the grid.
    Promise.allSettled(
      PICKS.map((t) =>
        screenCount({ universe_id: t.universe_id, rules: t.rules }).then((r) => ({
          id: t.id,
          n: r.matched_count,
        })),
      ),
    ).then((settled) => {
      if (!live) return;
      const got: Record<string, number> = {};
      for (const s of settled) {
        if (s.status === "fulfilled") got[s.value.id] = s.value.n;
      }
      // Every count failing means the scan is down, not that the market is
      // quiet — showing five cards that all lead nowhere is worse than none.
      if (Object.keys(got).length === 0) setFailed(true);
      setCounts(got);
    });
    return () => {
      live = false;
    };
  }, []);

  if (failed) return null;

  // A pick matching nothing today is hidden rather than shown as "0". A
  // zero-count card on the home page reads as a broken product, and the count
  // is most of what the card is for.
  const shown = PICKS.filter((t) => counts[t.id] === undefined || counts[t.id] > 0);

  return (
    <section
      className="rounded-xl border border-border bg-white p-4"
      data-testid="home-curated-screens"
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-semibold">Hot Market Picks</h2>
        <Link
          href={"/flow/custom_build_mode" as Route}
          className="text-xs text-primary hover:underline"
        >
          Screen the market →
        </Link>
      </div>

      <TradersAsk />

      <div className="my-3 h-px bg-border" />

      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Ready-made screens
      </div>

      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {shown.slice(0, 4).map((t) => (
          <StartingPointCard
            key={t.id}
            t={t}
            density="compact"
            count={counts[t.id]}
            href={`/screen?template=${encodeURIComponent(t.id)}&universe=${encodeURIComponent(t.universe_id)}`}
            testId={`home-pick-${t.id}`}
          />
        ))}
      </div>

      {/* The fifth (and any pick hidden for matching nothing) is named rather
          than silently absent — "see all" is a link, not a disappearance. */}
      {shown.length > 4 && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          {shown[4].name}
          {shown.length > 5 ? ` and ${shown.length - 5} more` : ""} ·{" "}
          <Link href={"/flow/custom_build_mode" as Route} className="text-primary hover:underline">
            see all {shown.length}
          </Link>
        </p>
      )}
    </section>
  );
}
