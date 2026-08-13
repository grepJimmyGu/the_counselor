"use client";

/**
 * <StrategyCard> — mode-agnostic LEGO brick (Sprint 2).
 *
 * Two visual states:
 *   Condensed (unselected) — idea + tagline, scannable in a grid
 *   Expanded (selected)   — two-column split: How it works | Why it works
 *                            each column scrolls independently
 *
 * Pure presentational — all data comes from OverlayMeta. Dynamic content
 * (ticker, fit) is computed by the parent. When `demo` is set, the expanded
 * card leads with a schematic <OverlayDemo> of the mechanic.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import type { OverlayMeta } from "@/lib/overlay-metadata";
import { OverlayDemo } from "./overlay-demo";

// ── Props ────────────────────────────────────────────────────────────────────

export interface StrategyCardProps {
  meta: OverlayMeta;
  /** Ticker for the dynamic example. */
  ticker: string;
  /** Example price for the ticker. */
  examplePrice: number;
  /** Number of holdings in the user's portfolio. */
  holdingsCount: number;
  /** Whether this card is currently selected (shows expanded view). */
  isSelected: boolean;
  /** Whether this card is disabled (e.g. insufficient holdings). */
  isDisabled?: boolean;
  /** Show the schematic mechanic demo at the top of the expanded card. */
  demo?: boolean;
  /** Called when the user clicks the card to select it. */
  onSelect?: () => void;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fillExample(template: string, ticker: string, price: number): string {
  const dropPrice = Math.round(price * 0.85);
  const recoveryPrice = Math.round(price * 0.92);
  return template
    .replace(/\{ticker\}/g, ticker)
    .replace(/\$\{price\}/g, `$${price}`)
    .replace(/\$\{dropPrice\}/g, `$${dropPrice}`)
    .replace(/\$\{recoveryPrice\}/g, `$${recoveryPrice}`);
}

function bulletLines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

/** The condensed card's outer element.
 *
 * `readOnly` renders a plain `<div>` rather than a disabled `<button>`, and
 * that distinction matters. The home "Overlay overview" is informational — the
 * picker chooses an overlay FOR a portfolio you have already uploaded, so
 * offering the choice with no holdings would dead-end. But rendering it as a
 * disabled button would dim it to `opacity-60` and show a not-allowed cursor,
 * which reads as "broken" rather than "this is a description". A read-only card
 * is fully legible, simply not clickable, and carries no button semantics for a
 * screen reader to announce.
 */
function Shell({
  readOnly,
  onSelect,
  isDisabled,
  testId,
  children,
}: {
  readOnly: boolean;
  onSelect?: () => void;
  isDisabled?: boolean;
  testId: string;
  children: React.ReactNode;
}) {
  const base =
    "w-full rounded-xl border p-4 text-left transition-all duration-150 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
  if (readOnly) {
    return (
      <div data-testid={testId} className={cn(base, "border-border")}>
        {children}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onSelect}
      disabled={isDisabled}
      data-testid={testId}
      className={cn(
        base,
        "cursor-pointer",
        isDisabled
          ? "cursor-not-allowed border-muted/30 bg-muted/10 opacity-60"
          : "border-border hover:border-primary/40 hover:bg-muted/30",
      )}
      aria-pressed={false}
      aria-disabled={isDisabled}
    >
      {children}
    </button>
  );
}

// ── Component ────────────────────────────────────────────────────────────────

export function StrategyCard({
  meta,
  ticker,
  examplePrice,
  holdingsCount,
  isSelected,
  isDisabled,
  demo = false,
  readOnly = false,
  onSelect,
}: StrategyCardProps & { readOnly?: boolean }) {
  const qualifies = holdingsCount >= meta.minHoldings;

  if (!isSelected) {
    // ── Condensed ────────────────────────────────────────────────────────
    return (
      <Shell
        readOnly={readOnly}
        onSelect={onSelect}
        isDisabled={isDisabled}
        testId={`strategy-card-${meta.kind}`}
      >
        {/* Header */}
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-base font-semibold">{meta.label}</span>
          <span
            className={cn(
              "shrink-0 rounded px-2 py-0.5 text-[11px] font-medium",
              meta.tier === "basic"
                ? "bg-primary/10 text-primary"
                : "bg-amber-100 text-amber-700",
            )}
          >
            {meta.tier === "basic" ? "BASIC" : "ADVANCED"}
          </span>
        </div>

        {/* Idea */}
        <p className="mb-2 text-sm leading-relaxed text-muted-foreground">
          {meta.idea}
        </p>

        {/* Tagline */}
        <p className="text-sm font-medium">{meta.tagline}</p>

        {/* The tagline carries a hard figure — "worst loss −28% vs −55%". In
            the picker the user can expand the card and read where it comes
            from; a read-only overview has no expand, so the basis travels with
            the claim or the claim doesn't ship. The rule is not "hide the
            number" (it is a real backtest, sourced in `overlay-metadata.ts`)
            — it is "never show a number without saying what produced it". */}
        {readOnly && meta.historicalEstimate && (
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {meta.historicalEstimate}
          </p>
        )}

        {/* Insufficient holdings badge */}
        {!qualifies && (
          <p className="mt-2 inline-block rounded bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-600">
            Needs {meta.minHoldings}+ holdings
          </p>
        )}
      </Shell>
    );
  }

  // ── Expanded (selected) ─────────────────────────────────────────────────
  const exampleText = fillExample(meta.exampleTemplate, ticker, examplePrice);
  const executionLines = bulletLines(meta.execution);

  return (
    <section
      data-testid={`strategy-card-${meta.kind}-expanded`}
      className={cn(
        "col-span-full overflow-hidden rounded-xl border border-primary bg-primary/5 ring-2 ring-primary shadow-sm",
        isDisabled && "opacity-60",
      )}
    >
      <div className="p-5">
        {/* Header */}
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-base font-semibold">{meta.label}</span>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "rounded px-2 py-0.5 text-[11px] font-medium",
                meta.tier === "basic"
                  ? "bg-primary/10 text-primary"
                  : "bg-amber-100 text-amber-700",
              )}
            >
              {meta.tier === "basic" ? "BASIC" : "ADVANCED"}
            </span>
            <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground">
              Selected
            </span>
          </div>
        </div>

        {/* Idea + Tagline */}
        <p className="mb-1 text-sm leading-relaxed text-muted-foreground">
          {meta.idea}
        </p>
        <p className="mb-4 text-sm font-medium">{meta.tagline}</p>

        {/* Schematic mechanic demo */}
        {demo && (
          <div className="mb-4 rounded-lg border border-border bg-background p-3">
            <OverlayDemo kind={meta.kind} />
          </div>
        )}

        {/* Two-column split */}
        <div className="grid gap-4 md:grid-cols-2">
          {/* Left: How it works */}
          <div className="max-h-[440px] overflow-y-auto rounded-lg border border-border p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              How it works
            </h3>
            <ul className="mb-3 space-y-1">
              {executionLines.map((line, i) => (
                <li
                  key={i}
                  className="flex items-start gap-1.5 text-sm leading-relaxed text-muted-foreground"
                >
                  <span className="mt-0.5 shrink-0 text-[11px] text-primary">
                    •
                  </span>
                  {line}
                </li>
              ))}
            </ul>

            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Example
            </h3>
            <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
              {exampleText}
            </p>

            {/* Track record */}
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Track record
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {meta.trackRecord.map((m) => (
                <div key={m.label} className="rounded-lg bg-muted/30 p-2">
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {m.label}
                  </dt>
                  <dd className="mt-0.5 font-mono text-sm font-semibold tabular-nums">
                    {m.value}
                  </dd>
                </div>
              ))}
            </div>

            {/* Fit + regime */}
            <div className="mt-3 space-y-0.5">
              {qualifies ? (
                <p className="text-xs font-medium text-emerald-600">
                  ✓ {meta.fitLabel}
                </p>
              ) : (
                <p className="text-[11px] font-medium text-red-600">
                  Needs {meta.minHoldings}+ holdings
                </p>
              )}
              <p className="text-xs leading-relaxed text-muted-foreground">
                <span className="text-emerald-600">{meta.bestRegime}</span>
                {" · "}
                <span className="text-amber-600">{meta.worstRegime}</span>
              </p>
            </div>
          </div>

          {/* Right: Why it works */}
          <div className="max-h-[440px] overflow-y-auto rounded-lg border border-border p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Why it works
            </h3>
            <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
              {meta.whyItWorks}
            </p>

            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              In detail
            </h3>
            <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
              {meta.mechanicDetail}
            </p>

            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Things to know
            </h3>
            <p className="mb-3 text-sm leading-relaxed text-muted-foreground">
              {meta.watchFor}
            </p>

            <p className="text-[11px] italic text-muted-foreground/70">
              {meta.research}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
