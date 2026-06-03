"use client";

/**
 * <StrategyCard> — mode-agnostic LEGO brick (Sprint 2).
 *
 * Renders a single portfolio overlay strategy card with progressive
 * disclosure: compact view (always visible) + expandable "Why it works"
 * section. Designed to be reused across portfolio mode, one-asset mode,
 * and future thesis/custom-build modes.
 *
 * The card is pure presentational — all data comes from OverlayMeta.
 * Dynamic content (ticker in examples, fit badge) is computed by the
 * parent and passed as props.
 */

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { OverlayMeta } from "@/lib/overlay-metadata";

// ── Props ────────────────────────────────────────────────────────────────────

export interface StrategyCardProps {
  meta: OverlayMeta;
  /** Ticker for the dynamic example (from user's portfolio or selected asset). */
  ticker: string;
  /** Example price for the ticker (used in example narrative). */
  examplePrice: number;
  /** Number of holdings in the user's portfolio. Used for fit badge. */
  holdingsCount: number;
  /** Whether this card is currently selected. */
  isSelected: boolean;
  /** Whether this card is disabled (e.g. insufficient holdings). */
  isDisabled: boolean;
  /** Called when the user clicks the card to select it. */
  onSelect: () => void;
  /** Called when the user toggles the expanded "Why it works" section. */
  onExpand?: () => void;
  /** Whether the expanded section is currently open. */
  expanded?: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fillExample(
  template: string,
  ticker: string,
  price: number,
): string {
  const dropPrice = Math.round(price * 0.85);
  const recoveryPrice = Math.round(price * 0.92);
  return template
    .replace(/\{ticker\}/g, ticker)
    .replace(/\$\{price\}/g, `$${price}`)
    .replace(/\$\{dropPrice\}/g, `$${dropPrice}`)
    .replace(/\$\{recoveryPrice\}/g, `$${recoveryPrice}`);
}

// ── Component ────────────────────────────────────────────────────────────────

export function StrategyCard({
  meta,
  ticker,
  examplePrice,
  holdingsCount,
  isSelected,
  isDisabled,
  onSelect,
  expanded = false,
}: StrategyCardProps) {
  const exampleText = fillExample(meta.exampleTemplate, ticker, examplePrice);
  const qualifies = holdingsCount >= meta.minHoldings;

  return (
    <section
      data-testid={`strategy-card-${meta.kind}`}
      className={cn(
        "overflow-hidden rounded-xl border transition-all duration-150",
        "focus-within:ring-2 focus-within:ring-primary",
        isDisabled
          ? "cursor-not-allowed border-muted/30 bg-muted/10 opacity-60"
          : isSelected
            ? "cursor-pointer border-primary bg-primary/5 ring-2 ring-primary shadow-sm"
            : "cursor-pointer border-border hover:border-primary/40 hover:bg-muted/30",
      )}
      onClick={isDisabled ? undefined : onSelect}
      role="button"
      tabIndex={isDisabled ? -1 : 0}
      aria-pressed={isSelected}
      aria-disabled={isDisabled}
    >
      <div className="space-y-3 p-5">
        {/* ── Header ──────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">{meta.label}</span>
          <span
            className={cn(
              "rounded px-2 py-0.5 text-[10px] font-medium",
              meta.tier === "core"
                ? "bg-primary/10 text-primary"
                : "bg-amber-100 text-amber-700",
            )}
          >
            {meta.tier === "core" ? "CORE" : "ADVANCED"}
          </span>
        </div>

        {/* ── The idea ────────────────────────────────────────────────── */}
        <p className="text-xs leading-relaxed text-muted-foreground">
          {meta.idea}
        </p>

        {/* ── How it executes ─────────────────────────────────────────── */}
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            How it executes
          </h3>
          <p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">
            {meta.execution}
          </p>
        </div>

        {/* ── Example ─────────────────────────────────────────────────── */}
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Example
          </h3>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {exampleText}
          </p>
        </div>

        {/* ── Track record ────────────────────────────────────────────── */}
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Track record
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {meta.trackRecord.map((m) => (
              <div
                key={m.label}
                className="rounded-lg bg-muted/30 p-2.5"
              >
                <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {m.label}
                </dt>
                <dd className="mt-0.5 font-mono text-xs font-semibold tabular-nums">
                  {m.value}
                </dd>
              </div>
            ))}
          </div>
        </div>

        {/* ── Fit + regime ────────────────────────────────────────────── */}
        <div className="space-y-1">
          {qualifies ? (
            <p className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600">
              ✓ {meta.fitLabel}
            </p>
          ) : (
            <p className="inline-flex items-center gap-1 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
              Needs {meta.minHoldings}+ holdings
            </p>
          )}
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            <span className="text-emerald-600">{meta.bestRegime}</span>
            {" · "}
            <span className="text-amber-600">{meta.worstRegime}</span>
          </p>
        </div>
      </div>

      {/* ── Expandable: Why it works ──────────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            // toggle handled by parent via onExpand
          }}
          className={cn(
            "flex w-full items-center justify-between border-t border-border px-5 py-3",
            "text-[11px] font-semibold uppercase tracking-wider text-muted-foreground",
            "transition-colors hover:text-foreground",
          )}
          aria-expanded={expanded}
        >
          {expanded ? "▾ Why it works" : "▸ Why it works"}
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform duration-200",
              expanded && "rotate-180",
            )}
          />
        </button>

        <div
          className={cn(
            "overflow-hidden transition-all duration-200",
            expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0",
          )}
        >
          <div className="space-y-4 px-5 pb-5">
            {/* Why it works */}
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Why it works
              </h3>
              <p className="text-sm leading-relaxed">{meta.whyItWorks}</p>
            </div>

            {/* The mechanic in detail */}
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                The mechanic in detail
              </h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {meta.mechanicDetail}
              </p>
            </div>

            {/* Research */}
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                What the research says
              </h3>
              <p className="text-sm leading-relaxed italic text-muted-foreground">
                {meta.research}
              </p>
            </div>

            {/* Watch for */}
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                What to watch for
              </h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {meta.watchFor}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
