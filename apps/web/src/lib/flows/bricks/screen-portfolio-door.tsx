"use client";

/**
 * <ScreenPortfolioDoor> — PRD-26b §2, "Create a Portfolio".
 *
 * The screen's second outcome: freeze today's matched names into a
 * portfolio-overlay strategy and backtest it. The other door (Save Live Rule)
 * keeps the RULE and re-runs it; this one keeps the NAMES as they stand.
 *
 * WHY FROZEN, AND NOT A LIVE LINK TO THE SCREEN (§2.2). Backtesting a living
 * screen needs to know what the basket was on every historical date. Basket
 * membership exists only from the day a screen was saved forward
 * (`screen_basket_members.entered_date`), and `signal_snapshot` holds each
 * primitive's LAST value, not a series — so there is nothing to reconstruct
 * from. A live link would produce a strategy that cannot be validated, which is
 * the same error as shipping a rule that can never reach `tested`.
 *
 * COMPACT ON PURPOSE. The full `<StrategyCard>` grid renders ~1,300px per card;
 * six of them is an 8,900px wall, measured on the portfolio upload step. Here
 * the overlay choice sits between the user and a button, so it is one row each.
 * The full cards still live at the picker step, where the choice is the page.
 */

import * as React from "react";
import type { OverlayKind, StrategyJson } from "@/lib/contracts";
import { OVERLAY_METADATA, OVERLAY_DISPLAY_ORDER } from "@/lib/overlay-metadata";
import {
  OVERLAYS_NEEDING_WEIGHTS,
  overlayStrategyFromTickers,
} from "../overlay-strategy-json";

/** §2.4 — a screen can match 200 names; that is not a portfolio. `ordered` is
 *  already ranked, so the cut is free. The user can change it. */
const DEFAULT_TOP_K = 20;
const LOOKBACK_YEARS = 5;

/** One line each, drawn from the overlay's own `idea` — the number-free half.
 *  `tagline` is NOT used here: it carries figures ("worst loss −28% vs −55%")
 *  that must travel with `historicalEstimate`, and a one-line row has no room
 *  for the basis. A number without its basis is the thing this repo bans. */
function firstSentence(idea: string): string {
  const cut = idea.indexOf(". ");
  return cut === -1 ? idea : idea.slice(0, cut + 1);
}

export function ScreenPortfolioDoor({
  ordered,
  onCreate,
}: {
  /** Matched names, best first. */
  ordered: string[];
  onCreate: (json: StrategyJson, overlay: OverlayKind, tickers: string[]) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [overlay, setOverlay] = React.useState<OverlayKind | null>(null);
  const [topK, setTopK] = React.useState(() =>
    Math.min(DEFAULT_TOP_K, ordered.length),
  );

  const basket = React.useMemo(
    () => ordered.slice(0, Math.max(1, Math.min(topK, ordered.length))),
    [ordered, topK],
  );

  // `rebalance` targets explicit weights a screen basket does not have, and
  // equal-weight rebalance is `defensive` without the filter (§2.3). Excluded
  // WITH the reason rather than quietly absent.
  const choices = OVERLAY_DISPLAY_ORDER.filter(
    (k) => !OVERLAYS_NEEDING_WEIGHTS.includes(k),
  );

  const meta = overlay ? OVERLAY_METADATA[overlay] : null;
  const shortBy = meta ? meta.minHoldings - basket.length : 0;
  const canCreate = Boolean(meta) && shortBy <= 0;

  if (!open) {
    return (
      <button
        type="button"
        data-testid="screen-door-portfolio"
        onClick={() => setOpen(true)}
        className="flex w-full flex-col items-start rounded-lg border border-primary/30 bg-primary/[0.03] p-3.5 text-left transition-colors hover:border-primary/50 hover:bg-primary/[0.06]"
      >
        <span className="text-sm font-semibold">Create a Portfolio →</span>
        <span className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          Keeps the <strong className="font-medium text-foreground">names</strong>,
          frozen as they stand today. Backtest them together as one portfolio
          with an overlay, then save it to your strategies.
        </span>
      </button>
    );
  }

  return (
    <div
      data-testid="screen-door-portfolio-open"
      className="rounded-lg border border-primary/30 bg-primary/[0.03] p-3.5"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">Create a Portfolio</span>
        <span className="font-mono text-[11px] text-muted-foreground">
          top {basket.length} of {ordered.length}
        </span>
      </div>

      <label className="mt-2 flex items-center gap-2 text-[12px] text-muted-foreground">
        How many names
        <input
          type="number"
          min={1}
          max={ordered.length}
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value) || 1)}
          data-testid="screen-portfolio-topk"
          className="w-16 rounded border border-border bg-background px-2 py-1 font-mono text-[12px]"
        />
      </label>

      <div className="mt-2.5">
        {choices.map((kind) => {
          const m = OVERLAY_METADATA[kind];
          const short = m.minHoldings - basket.length;
          return (
            <button
              key={kind}
              type="button"
              onClick={() => setOverlay(kind)}
              disabled={short > 0}
              data-testid={`screen-overlay-${kind}`}
              aria-pressed={overlay === kind}
              className={
                "flex w-full items-baseline gap-2 border-t border-border px-1 py-1.5 text-left text-[12.5px] transition-colors first:border-t-0 disabled:opacity-45 " +
                (overlay === kind ? "bg-primary/10" : "hover:bg-muted/40")
              }
            >
              <span className="w-28 shrink-0 font-medium">{m.label}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">
                {firstSentence(m.idea)}
              </span>
              <span className="shrink-0 text-[11px] text-muted-foreground">
                {short > 0 ? `needs ${m.minHoldings}` : "fits"}
              </span>
            </button>
          );
        })}
      </div>

      {/* Excluded, with the reason — never a card that silently isn't there. */}
      <p className="mt-2 text-[11px] text-muted-foreground">
        Rebalance isn&rsquo;t offered: it targets weights you set per holding,
        and a screen gives names without weights.
      </p>

      {meta && shortBy > 0 && (
        <p
          data-testid="screen-portfolio-short"
          className="mt-2 text-[12px] text-amber-700"
        >
          {meta.label} needs {meta.minHoldings} names; this basket has{" "}
          {basket.length}. Raise the count or pick another overlay.
        </p>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={!canCreate}
          data-testid="screen-portfolio-create"
          onClick={() => {
            if (!overlay) return;
            onCreate(
              overlayStrategyFromTickers(overlay, basket, LOOKBACK_YEARS),
              overlay,
              basket,
            );
          }}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          Backtest these {basket.length} →
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-[12px] text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
