"use client";

/**
 * Place an order at the user's own broker, from an exit signal.
 *
 * THE FLOW IS THREE STATES AND THE MIDDLE ONE IS THE POINT:
 *
 *   idle  ──"Place this order"──▶  preview  ──"Send it"──▶  sent
 *
 * `preview` is a real round-trip to the broker that prices the order —
 * actual commission, actual resulting cash — and returns a trade id.
 * Sending can only ever execute that id. So this is not a confirm dialog
 * that a determined user clicks through; it is the only path that exists,
 * and what they confirm is the real thing rather than our estimate of it.
 *
 * NO ONE-CLICK. There is deliberately no button that goes from idle to
 * sent. The preview costs a round-trip and a tap, and that is the feature.
 *
 * WHERE THE ACCOUNT COMES FROM. For a SELL, the account is the one that
 * actually holds the shares — looked up from the broker's own position
 * list. Not a dropdown: a user cannot sell from an account that does not
 * hold it, and it removes a choice they would have to get right.
 *
 * A BUY has nothing to look up — you do not own the thing yet — so it uses
 * the connected account, and asks only when there is more than one. This
 * component required `held` until 2026-08-25, which meant it could not buy
 * at all: `held` is null for anything you do not already own.
 *
 * SELLS ARE SIZED IN SHARES, BUYS IN DOLLARS. You sell what you hold, so a
 * share count is exact. A buy answers "how much of my money", and SnapTrade
 * takes a notional amount natively — converting it to shares ourselves
 * would round against a stale price and print a number the fill won't match.
 *
 * NOTHING IS AUTOMATIC. Every call here begins with a click. There is no
 * effect that places an order, no retry that re-sends one, and no path
 * from a notification straight to `sent`.
 */

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import {
  getSnapTradeStatus,
  listBrokerAccounts,
  listBrokerPositions,
  placeOrder,
  previewOrder,
} from "@/lib/api";
import type {
  BrokerAccount,
  BrokerPosition,
  OrderPreview,
  OrderResult,
} from "@/lib/contracts";

type State =
  | { kind: "idle" }
  | { kind: "previewing" }
  | { kind: "preview"; preview: OrderPreview }
  | { kind: "sending"; preview: OrderPreview }
  | { kind: "sent"; result: OrderResult }
  | { kind: "error"; message: string };

function money(v?: number | null) {
  return v === null || v === undefined ? "—" : `$${v.toFixed(2)}`;
}

export function PlaceOrder({
  symbol,
  units,
  notional,
  action = "SELL",
}: {
  symbol: string;
  /** Shares. Required for a SELL. */
  units?: number;
  /** Dollars. Required for a BUY. */
  notional?: number;
  action?: "BUY" | "SELL";
}) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [enabled, setEnabled] = useState(false);
  const [held, setHeld] = useState<BrokerPosition | null>(null);
  const [account, setAccount] = useState<BrokerAccount | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });

  useEffect(() => {
    // Wait for NextAuth to resolve, or a signed-in user fires this
    // anonymously during the loading window and gets nothing back.
    if (sessionStatus === "loading" || !backendToken) return;
    let live = true;
    getSnapTradeStatus(backendToken)
      .then((s) => {
        if (!live || !s.trading_enabled || !s.registered) return;
        setEnabled(true);
        return listBrokerPositions(backendToken);
      })
      .then((rows) => {
        if (!live || !rows) return;
        setHeld(
          rows.find(
            (r) => r.symbol.toUpperCase() === symbol.toUpperCase(),
          ) ?? null,
        );
        // A BUY needs an account and cannot get one from a position it does
        // not have yet. Only fetched for buys — a sell already knows.
        if (action === "BUY") return listBrokerAccounts(backendToken);
      })
      .then((accts) => {
        if (live && accts && accts.length > 0) setAccount(accts[0]);
      })
      .catch(() => {
        /* offer nothing rather than a control that will fail */
      });
    return () => {
      live = false;
    };
  }, [sessionStatus, backendToken, symbol, action]);

  // A sell prices against the account that holds the shares; a buy against
  // the connected account.
  const accountId = action === "SELL" ? held?.account_id : account?.id;

  const doPreview = useCallback(async () => {
    if (!backendToken || !accountId) return;
    setState({ kind: "previewing" });
    try {
      const preview = await previewOrder(
        {
          account_id: accountId,
          symbol,
          action,
          // Exactly one — the backend refuses both.
          ...(action === "BUY" ? { notional } : { units }),
          order_type: "Market",
          time_in_force: "Day",
        },
        backendToken,
      );
      setState({ kind: "preview", preview });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "Couldn't price this order.",
      });
    }
  }, [backendToken, accountId, symbol, action, units, notional]);

  const doPlace = useCallback(
    async (preview: OrderPreview) => {
      if (!backendToken) return;
      setState({ kind: "sending", preview });
      try {
        const result = await placeOrder(preview.trade_id, backendToken);
        setState({ kind: "sent", result });
      } catch (e) {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Couldn't place the order.",
        });
      }
    },
    [backendToken],
  );

  // Nothing to offer: trading off, no connection, or — for a sell — they
  // don't actually hold it.
  if (!enabled) return null;
  if (action === "SELL" && !held) return null;
  if (action === "BUY" && !account) return null;

  // Never offer to sell more than the broker says they have. A buy has no
  // equivalent ceiling here: the broker rejects it at preview if the cash
  // isn't there, and its answer is better than our guess.
  if (action === "SELL") {
    if (!units || Math.min(units, held!.units) <= 0) return null;
  } else if (!notional || notional <= 0) {
    return null;
  }

  return (
    <div
      data-testid={`place-order-${symbol}`}
      className="mt-3 rounded-md border border-border bg-background p-3"
    >
      {state.kind === "sent" ? (
        <p className="text-[13px] text-foreground">
          Order sent to your broker
          {state.result.status ? ` — ${state.result.status}` : ""}. It will
          appear in your account as your broker fills it.
        </p>
      ) : state.kind === "preview" || state.kind === "sending" ? (
        <>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Confirm this order
          </p>
          <p className="mt-1 font-mono text-sm font-semibold">
            {state.preview.action}{" "}
            {state.preview.units
              ? `${state.preview.units} ${state.preview.symbol}`
              : `${money(notional)} of ${state.preview.symbol}`}
          </p>
          <dl className="mt-2 space-y-0.5 text-[12px]">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Estimated commission</dt>
              <dd className="font-mono">
                {money(state.preview.estimated_commission)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Cash after</dt>
              <dd className="font-mono">{money(state.preview.remaining_cash)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            These are your broker&apos;s own numbers for this order. Sending it
            places a real trade in your account.
          </p>
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              disabled={state.kind === "sending"}
              onClick={() => doPlace(state.preview)}
              data-testid={`send-order-${symbol}`}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 transition hover:bg-slate-50 disabled:opacity-40"
            >
              {state.kind === "sending" ? "Sending…" : "Send it"}
            </button>
            <button
              type="button"
              disabled={state.kind === "sending"}
              onClick={() => setState({ kind: "idle" })}
              className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline disabled:opacity-40"
            >
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={state.kind === "previewing"}
              onClick={doPreview}
              data-testid={`preview-order-${symbol}`}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 transition hover:bg-slate-50 disabled:opacity-40"
            >
              {state.kind === "previewing"
                ? "Pricing…"
                : `Place this order at your broker`}
            </button>
            <span className="text-[12px] text-muted-foreground">
              {action === "SELL"
                ? `${Math.min(units ?? 0, held?.units ?? 0)} of ${held?.units ?? 0} held`
                : `${money(notional)} at ${account?.institution_name ?? "your broker"}`}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            You&apos;ll see the real cost before anything is sent.
          </p>
        </>
      )}
      {state.kind === "error" && (
        <p className="mt-2 text-[12px] text-destructive">{state.message}</p>
      )}
    </div>
  );
}
