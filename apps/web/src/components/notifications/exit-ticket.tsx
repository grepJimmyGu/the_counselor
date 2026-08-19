"use client";

/**
 * The exit order ticket — the artifact a user carries to their broker.
 *
 * WHY THE PRIMARY FIELD HAS NO PRICE IN IT. The user's job at the broker is
 * to enter side, quantity, symbol. Price is not needed for a market order
 * and is user-chosen for a limit order — so the one number that is
 * structurally stale is also the one they do not need, and excluding it
 * from the headline solves half the honesty problem by information
 * architecture rather than by disclaimer. Every price here is demoted to a
 * muted evidence row.
 *
 * `Trigger price`, never `Current`. A field name that cannot decay needs no
 * warning attached to it.
 *
 * THE QUANTITY RULE (design pass §3.2): print a quantity only when it is
 * derivable ONE way.
 *
 *   - `sell_all`                          → exact, `shares_remaining`
 *   - first scale-out on an untouched pos → exact
 *   - any later scale-out                 → NO primary number
 *
 * The last case is not a temporary crutch. Since #325 the scale-out
 * convention is unambiguous, but `shares_remaining` only decrements when
 * the user confirms a fill — so on a position with an unconfirmed earlier
 * exit we genuinely do not know what they hold. Printing a confident number
 * there would describe a position that may not exist. A system that says "I
 * don't know" when it doesn't know is believed when it does.
 *
 * Precision inherits what the user declared, always rounded DOWN, so a
 * ticket can never instruct someone to sell more than the tier describes
 * and `13.3333` never reaches a broker.
 */

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";

import type { UnresolvedExit } from "@/lib/contracts";

function money(v?: number | null) {
  return v === null || v === undefined ? "—" : `$${v.toFixed(2)}`;
}

function pct(v?: number | null) {
  if (v === null || v === undefined) return null;
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

/** Round DOWN, at the precision the user declared. */
function shareText(raw: number, declared: number): string {
  const whole = Number.isInteger(declared);
  const v = whole ? Math.floor(raw) : Math.floor(raw * 10_000) / 10_000;
  return String(v);
}

type Qty =
  | { kind: "exact"; shares: string }
  | { kind: "ambiguous"; ifExecuted: string; ifNot: string };

export function quantityFor(item: UnresolvedExit): Qty {
  if (item.action === "sell_all") {
    return {
      kind: "exact",
      shares: shareText(item.shares_remaining, item.shares_initial),
    };
  }
  const suggested = item.shares ?? 0;
  // Untouched position: nothing has been sold, so the tier's fraction of the
  // original IS what they hold a fraction of. No ambiguity.
  if (item.shares_remaining === item.shares_initial) {
    return { kind: "exact", shares: shareText(suggested, item.shares_initial) };
  }
  return {
    kind: "ambiguous",
    ifExecuted: shareText(suggested, item.shares_initial),
    ifNot: shareText(item.shares_remaining, item.shares_initial),
  };
}

/** The three lines the copy button emits. The caveat travels attached to
 *  the number — the only durable way to stop it being read later as a
 *  quote once it has been pasted somewhere else. */
export function ticketText(item: UnresolvedExit): string {
  const q = quantityFor(item);
  const line1 =
    q.kind === "exact"
      ? `SELL ${q.shares} ${item.symbol}`
      : `SELL ${item.symbol} — quantity depends on what you still hold`;
  const tier = item.tier_label ?? "Exit tier";
  const move = pct(item.pct_change);
  const line2 = `${tier}${move ? ` (${move} from entry)` : ""} — ${item.strategy_title}`;
  const when = item.bar_date ?? item.signaled_at ?? "";
  const line3 =
    item.bar_resolution === "daily"
      ? `Measured on the ${when} close · trigger ${money(item.price)} — not a fill price; you act at the next open`
      : `Signaled ${when} · trigger ${money(item.price)} (delayed data, not a fill price)`;
  return `${line1}\n${line2}\n${line3}`;
}

export function ExitTicket({ item }: { item: UnresolvedExit }) {
  const [copied, setCopied] = useState(false);
  const q = quantityFor(item);
  const isDaily = item.bar_resolution === "daily";
  const move = pct(item.pct_change);

  async function copy() {
    try {
      await navigator.clipboard.writeText(ticketText(item));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked — the ticket is still on screen to read */
    }
  }

  return (
    <div
      data-testid={`exit-ticket-${item.symbol}`}
      className="rounded-lg border border-border bg-card p-3"
    >
      {/* Byline — the established date-stamp pattern, never buried. */}
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {item.bar_date ?? item.signaled_at ?? "—"}
        {" · "}
        {item.strategy_title}
      </p>
      <h3 className="mt-1 text-sm font-semibold">
        {item.symbol} — {item.tier_label ?? "Exit tier"} reached
      </h3>

      {/* The ticket block: the one thing worth screenshotting. */}
      <div className="mt-3 rounded-md border border-border bg-background p-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          What the rule says
        </p>
        {q.kind === "exact" ? (
          <p className="mt-1.5 font-mono text-lg font-semibold tracking-tight">
            SELL {q.shares} {item.symbol}
          </p>
        ) : (
          <>
            <p className="mt-1.5 font-mono text-base text-muted-foreground">
              SELL — {item.symbol}
            </p>
            <p className="mt-1 text-[13px] text-foreground">
              We haven&apos;t confirmed what you sold at the earlier tier, so
              we won&apos;t state a share count.
            </p>
            <div className="mt-1.5 space-y-0.5 text-[12px] text-muted-foreground">
              <div>If that tier was executed: {q.ifExecuted} shares</div>
              <div>If it was not: up to {q.ifNot} shares held</div>
            </div>
          </>
        )}
        <div className="mt-2 flex items-center justify-between gap-2">
          <p className="text-[12px] text-muted-foreground">
            {item.tier_label ?? "Exit tier"}
            {" · "}
            {item.action === "sell_all" ? "sell all" : "partial exit"}
          </p>
          <button
            type="button"
            onClick={copy}
            data-testid={`copy-ticket-${item.symbol}`}
            className="rounded-md border border-border bg-background px-2.5 py-1 text-[12px] font-medium transition hover:bg-muted"
          >
            {copied ? "Copied" : "Copy ticket"}
          </button>
        </div>
      </div>

      {/* Evidence — every price lives here, muted, never in the headline. */}
      <dl className="mt-3 space-y-1 text-[12px]">
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Trigger price</dt>
          <dd className="font-mono">
            {money(item.price)}
            {move ? ` (${move})` : ""}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Your entry</dt>
          <dd className="font-mono">{money(item.entry_price)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">You hold</dt>
          <dd className="font-mono">
            {shareText(item.shares_remaining, item.shares_initial)} shares
          </dd>
        </div>
      </dl>

      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        {isDaily
          ? "Measured on a completed session's bar. This is the price that met the rule, not one you can still get — you would act at the next open."
          : "Prices are delayed up to ~20 minutes. This is the bar that met the rule, not a quote."}
      </p>

      <Link
        href={`/strategies/${encodeURIComponent(item.strategy_id)}?action=executed` as Route}
        className="mt-2 inline-block text-[12px] font-medium text-primary hover:underline"
      >
        Open the position in Livermore →
      </Link>

      <p className="mt-2 border-t border-border pt-2 text-[11px] leading-relaxed text-muted-foreground">
        Livermore does not place trades on your behalf. The strategy signalled
        this; you decide whether to act on it.
      </p>
    </div>
  );
}
