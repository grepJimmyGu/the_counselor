"use client";

/**
 * <SignalCard> — PRD-25 unified signal card (L1 → L3 progressive disclosure).
 *
 *   L1 — heading + glance state + display + plain-English reason (always shown)
 *   L2 — the strategy's fired-primitive logic (on expand)
 *   L3 — a link into the existing backtest (on expand)
 *
 * Self-contained: its own expand control lives here, so DON'T nest it inside
 * another interactive element. Renders any `SignalCard` payload — a saved
 * strategy today, and (PRD-26/27) a promote-draft preview or per-ticker card.
 *
 * Minimal scope: the state set is `in_signal / basket / flat / pending`. The
 * market-fill states (entry_zone / in_position / target / stop) are deferred —
 * see apps/api/app/schemas/signal_card.py.
 */
import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { ChevronDown } from "lucide-react";

import type { SignalCard as SignalCardType } from "@/lib/contracts";
import { cn } from "@/lib/utils";

import { SignalGlanceChip } from "./signal-glance-chip";

interface SignalCardProps {
  card: SignalCardType;
  /** Optional sub-line under the heading (e.g. "Saved 7/28/2026"). */
  subtitle?: string;
  /** When set, the heading becomes a navigation link. */
  href?: Route | null;
  /** L3 target; defaults to the strategy page when a backtest exists. */
  backtestHref?: Route | null;
  defaultOpen?: boolean;
  className?: string;
}

export function SignalCard({
  card,
  subtitle,
  href,
  backtestHref,
  defaultOpen = false,
  className,
}: SignalCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  const heading = card.strategy_title ?? card.symbol ?? "Signal";
  const btHref =
    backtestHref ??
    (card.backtest_id ? (`/account/strategies/${card.saved_strategy_id}` as Route) : null);
  const hasDetail =
    card.fired_primitives.length > 0 || Boolean(btHref) || Boolean(card.strategy_type);

  return (
    <div
      data-testid="signal-card"
      data-state={card.state}
      className={cn("rounded-lg border border-border bg-card p-3", className)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {card.as_of && (
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              As of {card.as_of}
            </p>
          )}
          {href ? (
            <Link
              href={href}
              data-testid="signal-card-heading"
              className="block truncate text-sm font-semibold text-foreground hover:text-primary"
            >
              {heading}
            </Link>
          ) : (
            <p className="truncate text-sm font-semibold text-foreground">{heading}</p>
          )}
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          <div className="mt-1 flex items-center gap-2">
            <SignalGlanceChip state={card.state} />
            <span className="truncate text-xs text-muted-foreground">{card.display}</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{card.reason}</p>
        </div>
        {hasDetail && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            data-testid="signal-card-toggle"
            aria-expanded={open}
            aria-label={open ? "Hide signal details" : "Show signal details"}
            className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
          </button>
        )}
      </div>

      {open && hasDetail && (
        <div
          data-testid="signal-card-detail"
          className="mt-3 space-y-3 border-t border-border/60 pt-3"
        >
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Logic
            </p>
            {card.fired_primitives.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {card.fired_primitives.map((primitive, i) => (
                  <span
                    key={`${primitive}-${i}`}
                    className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
                  >
                    {primitive}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                {card.strategy_type
                  ? `${card.strategy_type.replace(/_/g, " ")} logic`
                  : "No rule breakdown available."}
              </p>
            )}
          </div>
          {btHref && (
            <Link
              href={btHref}
              data-testid="signal-card-backtest"
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              View backtest →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
