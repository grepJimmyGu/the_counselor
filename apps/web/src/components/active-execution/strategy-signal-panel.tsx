"use client";

/**
 * What this strategy says to hold right now — and, when it says to be in
 * something you don't own, the ticket to buy it.
 *
 * THIS IS THE ENTRY SIDE. The exit side has worked for weeks: a tier fires,
 * you get an email, the ticket shows a sell. The other half — "your strategy
 * wants in" — had no surface at all, so the only way to act on an entry was
 * to notice it yourself.
 *
 * WHY THE SIGNAL CARD AND NOT THE SIGNAL STATE. `/api/saved-strategies/{id}/signal`
 * is 404 in production on purpose: `main.py` gates the whole signals router
 * on `signal_alerts_enabled`, held until the disclaimer copy clears legal
 * review. `/api/signals/card` (PRD-25) is deliberately always mounted for
 * exactly this reason — "a read-only re-presentation of existing signal
 * state… must exist regardless of signal_alerts_enabled." So this reads the
 * card. Reaching around the gate to the state endpoint would be routing
 * around a legal hold, which is not ours to do.
 *
 * SIZED IN DOLLARS. A sell is sized in shares because you sell what you
 * hold. A buy answers "how much of my money," and SnapTrade takes a notional
 * amount natively — converting to shares here would round against a stale
 * price and print a number the fill won't match.
 *
 * NOTHING AUTOMATIC. The card is a read. The dollar field does nothing until
 * you type in it, and `<PlaceOrder>` still costs a preview and two taps.
 *
 * AND IT HAS TO BE USEFUL WITH PLACEMENT OFF, which is the state production
 * is in right now. `SNAPTRADE_TRADING_ENABLED` defaults false, so
 * `<PlaceOrder>` renders nothing — and the first version of this panel showed
 * a dollar field anyway. You typed $2,000 and nothing happened: an input that
 * promised an action the product could not perform. `<ExitTicket>` had this
 * right from the start (Copy always works), and the entry side has to match:
 * when we cannot place the order, hand over a ticket you can carry to any
 * broker instead of a control that does nothing.
 */

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { getSignalCard, getSnapTradeStatus } from "@/lib/api";
import type { SignalCard } from "@/lib/contracts";
import { PlaceOrder } from "@/components/execution/place-order";

/** Three lines: the order, where it came from, and what it is not.
 *  Mirrors `ticketText` on the exit side — the same artefact, opposite side. */
export function entryTicketText(
  card: SignalCard, symbol: string, dollars: number | null,
): string {
  const size = dollars && dollars > 0 ? `${"$"}${dollars.toLocaleString()} of ` : "";
  return [
    `BUY ${size}${symbol}`,
    `${card.strategy_title ?? "Your strategy"} signalled an entry${
      card.as_of ? ` on the ${card.as_of} close` : ""
    }.`,
    "Signal price is a completed session's close, not a live quote.",
  ].join("\n");
}

/** A card whose state names one ticker the strategy wants to be long. */
export function entrySymbol(card: SignalCard | null): string | null {
  if (!card || card.state !== "in_signal") return null;
  return card.symbol ? card.symbol.toUpperCase() : null;
}

export function StrategySignalPanel({ strategyId }: { strategyId: string }) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [card, setCard] = useState<SignalCard | null>(null);
  const [amount, setAmount] = useState("");
  // Whether we can actually transmit an order. False in production today.
  const [canPlace, setCanPlace] = useState(false);
  const [copied, setCopied] = useState(false);

  const symbol = entrySymbol(card);
  const dollars = Number(amount);
  const validAmount = Number.isFinite(dollars) && dollars > 0;

  useEffect(() => {
    if (sessionStatus === "loading" || !backendToken) return;
    let live = true;
    getSignalCard(strategyId, backendToken)
      .then((c) => {
        if (live) setCard(c);
      })
      .catch(() => {
        /* show nothing rather than a wrong reading */
      });
    getSnapTradeStatus(backendToken)
      .then((st) => {
        if (live) setCanPlace(Boolean(st.trading_enabled && st.registered));
      })
      .catch(() => {
        /* treat unknown as "cannot place" — offer the ticket, not a button */
      });
    return () => {
      live = false;
    };
  }, [sessionStatus, backendToken, strategyId]);

  const copyTicket = useCallback(async () => {
    if (!card || !symbol) return;
    await navigator.clipboard.writeText(
      entryTicketText(card, symbol, validAmount ? dollars : null),
    );
    setCopied(true);
  }, [card, symbol, dollars, validAmount]);

  if (!card) return null;

  // Not yet computed. Say so — an empty panel reads as "no signal", which is
  // a different claim from "we haven't looked yet".
  if (card.state === "pending") {
    return (
      <div
        data-testid="signal-panel-pending"
        className="rounded-lg border border-dashed border-border bg-card p-3"
      >
        <p className="text-[13px] text-muted-foreground">
          We haven&rsquo;t computed this strategy&rsquo;s signal yet. It runs
          after the close.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="signal-panel"
      className="rounded-lg border border-border bg-card p-3.5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Your strategy says
          </p>
          <p
            data-testid="signal-panel-display"
            className="mt-0.5 font-mono text-sm font-semibold text-foreground"
          >
            {card.display}
          </p>
        </div>
        {card.as_of && (
          <span className="font-mono text-[11px] text-muted-foreground">
            as of {card.as_of}
          </span>
        )}
      </div>

      {card.reason && (
        <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
          {card.reason}
        </p>
      )}

      {symbol && (
        <div className="mt-3 border-t border-border pt-3">
          {canPlace ? (
            <>
              <label className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] text-foreground">
                  Buy {symbol} with
                </span>
                <span className="inline-flex items-center rounded-md border border-input bg-background px-2 py-1">
                  <span className="text-[13px] text-muted-foreground">$</span>
                  <input
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    inputMode="decimal"
                    placeholder="2,000"
                    data-testid="signal-panel-amount"
                    className="w-24 bg-transparent px-1 font-mono text-[13px] outline-none"
                  />
                </span>
              </label>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Your broker converts this to shares at the fill — we
                don&rsquo;t round it for you.
              </p>
              {validAmount && (
                <PlaceOrder symbol={symbol} notional={dollars} action="BUY" />
              )}
            </>
          ) : (
            /* Cannot transmit an order — hand over one you can carry to any
               broker rather than an input that does nothing. */
            <>
              <p
                data-testid="signal-panel-ticket"
                className="font-mono text-sm font-semibold text-foreground"
              >
                BUY {symbol}
              </p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
                Take this to your broker — you choose the size. Signal price is
                a completed session&rsquo;s close, not a live quote.
              </p>
              <button
                type="button"
                onClick={copyTicket}
                data-testid="signal-panel-copy"
                className="mt-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 transition hover:bg-slate-50"
              >
                {copied ? "Copied" : "Copy ticket"}
              </button>
            </>
          )}
        </div>
      )}

      <p className="mt-3 border-t border-border pt-2 text-[11px] leading-relaxed text-muted-foreground">
        Livermore never places an order you haven&rsquo;t approved. This is
        what the strategy computed, not advice.
      </p>
    </div>
  );
}
