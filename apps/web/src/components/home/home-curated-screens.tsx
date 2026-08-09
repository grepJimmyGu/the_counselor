"use client";

/**
 * Home block 2 — Special list (特色榜單).
 *
 * The nine presets already ship at `GET /api/screener/presets` with a live
 * result count and sample tickers, and `/stocks?preset=<slug>` already renders
 * their results. So this block is pure surfacing: no new backend, no new data.
 *
 * One click, straight to results — no intermediate landing page. A preset that
 * needs an extra click to show its names is a brochure, not a screen.
 *
 * Empty presets are hidden rather than shown as "0 names". Two of the nine
 * (Top Value, Top Rated) were empty until the P/E backfill ran, and a zero-count
 * card on the home page reads as a broken product; hiding is honest because the
 * count really is the whole value of the card.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { getScreenerPresets } from "@/lib/api";
import type { ScreenerPresetSummary } from "@/lib/contracts";

/** Rotating accent per card. Purely decorative — index-based, not meaningful,
 *  so it stays stable as counts change but carries no claim about the screen. */
const ACCENTS = [
  "bg-primary/8 text-primary",
  "bg-emerald-500/10 text-emerald-700",
  "bg-amber-500/10 text-amber-700",
  "bg-violet-500/10 text-violet-700",
];

function PresetCard({ p, i }: { p: ScreenerPresetSummary; i: number }) {
  return (
    <Link
      href={`/stocks?preset=${encodeURIComponent(p.slug)}` as Route}
      className="group rounded-lg border border-border p-3 transition-colors hover:border-primary/40 hover:bg-muted/30"
      data-testid="curated-screen"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold">{p.title}</span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${ACCENTS[i % ACCENTS.length]}`}
        >
          {p.result_count}
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {p.description}
      </p>
      {p.sample_tickers.length > 0 && (
        <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground/80">
          {p.sample_tickers.slice(0, 4).join(" · ")}
        </div>
      )}
    </Link>
  );
}

export function HomeCuratedScreens() {
  const [presets, setPresets] = useState<ScreenerPresetSummary[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    getScreenerPresets()
      .then((d) => live && setPresets((d.presets ?? []).filter((p) => p.result_count > 0)))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return null;

  return (
    <section
      className="rounded-xl border border-border bg-white p-5"
      data-testid="home-curated-screens"
    >
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-heading text-base font-semibold">Special list</h2>
        <Link
          href={"/stocks/screener" as Route}
          className="text-xs text-primary hover:underline"
        >
          Screen the market →
        </Link>
      </div>

      {presets.length > 0 ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {presets.slice(0, 6).map((p, i) => (
            <PresetCard key={p.slug} p={p} i={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted/50" />
          ))}
        </div>
      )}
    </section>
  );
}
