"use client";

/**
 * Which methodology produced these numbers.
 *
 * On 2026-08-18 three changes made backtest results WORSE for an unchanged
 * strategy: scale-out tiers began taking a fraction of the ORIGINAL
 * position rather than of what remained, ladder exits began filling at the
 * next session's open (carrying the overnight gap) instead of at the price
 * that triggered the tier, and transaction cost + slippage stopped
 * defaulting to zero.
 *
 * Stored results were deliberately NOT re-run — silently rewriting
 * someone's saved backtest is worse than a visible version stamp. But that
 * leaves a real trap: re-run an old strategy and the figures no longer
 * match its own saved card, with nothing on screen to explain the gap.
 *
 * This turns "why did my number move?" into a self-answering question.
 * Absent version = computed before any of it, so the result is gross of
 * costs and assumes a fill the user could never have got.
 */

export function MethodologyNote({ version }: { version?: string | null }) {
  const pre = !version;
  return (
    <p
      data-testid="methodology-note"
      className="mt-2 text-[11px] leading-relaxed text-muted-foreground"
    >
      {pre ? (
        <>
          Computed before methodology versioning: <strong>gross of costs</strong>,
          with exits filling at the price that triggered them. A fresh run will
          report lower figures.
        </>
      ) : (
        <>
          Methodology <span className="font-mono">{version}</span> — net of 5 bps
          cost and 5 bps slippage, with exits filling at the next session&apos;s
          open.
        </>
      )}
    </p>
  );
}
