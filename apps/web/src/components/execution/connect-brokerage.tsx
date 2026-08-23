"use client";

/**
 * Connect a brokerage account.
 *
 * THIS IS THE MISSING LINK. `POST /api/snaptrade/connect` shipped in #334
 * and had zero callers, so `status.registered` was false for every user,
 * so `<PlaceOrder>` (#336) never rendered. Two merged features that had
 * never once appeared on screen, waiting on this component.
 *
 * WHAT THE USER IS ACTUALLY AGREEING TO, and why the copy is careful:
 * they sign in AT THEIR OWN BROKER, on SnapTrade's portal. Livermore never
 * sees brokerage credentials — that is the entire reason for going through
 * an aggregator instead of asking for a password. The card says so, because
 * "connect your brokerage" sounds like handing over a login to anyone who
 * has not thought about it, and that is the objection that stops people.
 *
 * A PEER, NOT A GATE. In the portfolio flow this sits beside "add a ticker"
 * with its own dismissal. A brokerage login is a high-trust action and a
 * real share of users will decline it on first contact; the manual paths
 * stay exactly as they were, and declining costs nothing.
 *
 * `returnPath` is a SITE-RELATIVE PATH. The server builds the origin — a
 * full URL here would be an open redirect at the most sensitive moment in
 * the product. See `return_url_for` in `snaptrade_service.py`.
 */

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import { connectBrokerage, getSnapTradeStatus } from "@/lib/api";
import type { SnapTradeStatus } from "@/lib/contracts";

type Props = {
  /** Where SnapTrade returns the user. Site-relative path only. */
  returnPath?: string;
  /** Flow surfaces offer a dismissal; a settings page does not. */
  dismissible?: boolean;
  className?: string;
};

export function ConnectBrokerage({
  returnPath,
  dismissible = false,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [state, setState] = useState<SnapTradeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Wait for NextAuth to resolve, or a signed-in user fires this
    // anonymously during the loading window and gets nothing back.
    if (sessionStatus === "loading" || !backendToken) return;
    let live = true;
    getSnapTradeStatus(backendToken)
      .then((s) => {
        if (live) setState(s);
      })
      .catch(() => {
        /* offer nothing rather than a control that will fail */
      });
  }, [sessionStatus, backendToken]);

  const connect = useCallback(async () => {
    if (!backendToken) return;
    setBusy(true);
    setError(null);
    try {
      const { redirect_uri } = await connectBrokerage(backendToken, returnPath);
      // Full navigation, not a new tab: the user is going to their broker to
      // sign in, and coming back is the point. A popup that gets blocked, or
      // a tab they close, both strand them mid-connection.
      window.location.assign(redirect_uri);
    } catch (e) {
      setBusy(false);
      setError(
        e instanceof Error ? e.message : "Couldn't start the connection.",
      );
    }
  }, [backendToken, returnPath]);

  if (dismissed) return null;
  // Unconfigured means the operator has not enabled this. Show nothing
  // rather than a button that 503s on click.
  if (!state?.configured) return null;

  if (state.registered && state.connected_accounts > 0) {
    return (
      <div
        data-testid="brokerage-connected"
        className={className ?? "rounded-lg border border-border bg-card p-3"}
      >
        <p className="text-[13px] text-foreground">
          {state.connected_accounts === 1
            ? "1 brokerage account connected"
            : `${state.connected_accounts} brokerage accounts connected`}
          {state.last_synced_at ? " · holdings up to date" : ""}
        </p>
        <button
          type="button"
          onClick={connect}
          disabled={busy}
          data-testid="connect-another-brokerage"
          className="mt-1.5 text-[12px] font-medium text-primary underline-offset-2 hover:underline disabled:opacity-40"
        >
          {busy ? "Opening…" : "Connect another"}
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="connect-brokerage"
      className={
        className ?? "rounded-lg border-2 border-primary/40 bg-card p-3"
      }
    >
      <p className="text-sm font-medium">Connect your brokerage</p>
      <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
        Your real positions and cost basis, with nothing to type. You sign in
        at your broker — Livermore never sees those credentials, and can read
        your holdings, not move your money.
      </p>
      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={connect}
          disabled={busy}
          data-testid="connect-brokerage-start"
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-900 transition hover:bg-slate-50 disabled:opacity-40"
        >
          {busy ? "Opening…" : "Connect a broker"}
        </button>
        {dismissible && (
          <button
            type="button"
            onClick={() => setDismissed(true)}
            data-testid="connect-brokerage-dismiss"
            className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
          >
            I&apos;ll add them myself
          </button>
        )}
      </div>
      {error && (
        <p className="mt-2 text-[12px] text-destructive">{error}</p>
      )}
    </div>
  );
}
