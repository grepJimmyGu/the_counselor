"use client";

/**
 * /account/positions — PRD-28 Step 4. "What am I holding, and what happens
 * next."
 *
 * The last missing destination. Every other surface in the execution chain
 * answers a narrower question: the per-strategy dashboard needs you to
 * already know which strategy to open, and the home banner only appears when
 * something has fired. Between those two there was nowhere to simply look at
 * your positions.
 *
 * THREE SECTIONS, IN THIS ORDER, and the order is the design:
 *
 *   1. Exits you owe a decision on — you were told, you have not answered.
 *   2. Positions Livermore is tracking, with their live stop and next target.
 *   3. Brokerage holdings that are NOT tracked.
 *
 * The third section is the honest one. A brokerage holding has no strategy
 * and no exit ladder, so nothing is watching it — and a page that mixed it in
 * with the tracked positions would imply otherwise. Listing them separately,
 * with a way to start tracking, is the difference between "here is your
 * portfolio" and "here is what we are actually doing for you."
 *
 * UNDER `/account`, not top-level: a permanent trading surface shown to
 * signed-out visitors is a different product.
 *
 * Trap #19: reads `backendToken` off `useSession()` and waits for the session
 * to resolve before fetching.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import { ArrowRight, Loader2 } from "lucide-react";

import { listBrokerPositions, listOpenPositions } from "@/lib/api";
import type { BrokerPosition, TrackedPosition } from "@/lib/contracts";
import { UnresolvedExits } from "@/components/notifications/unresolved-exits";
import { ConnectBrokerage } from "@/components/execution/connect-brokerage";

function pct(v: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = (v * 100).toFixed(1);
  return opts.sign && v > 0 ? `+${s}%` : `${s}%`;
}

function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `$${v.toFixed(2)}`;
}

/** How the price we are showing was obtained. A daily strategy is evaluated
 *  on the close, so an intraday quote is fresher than the thing the ladder
 *  will actually be measured against — saying which avoids implying the
 *  monitor is watching tick by tick. */
function priceNote(p: TrackedPosition): string {
  if (p.price_source === "none") return "no recent price";
  if (p.price_source === "daily_close") return "last close";
  return p.bar_resolution === "daily"
    ? "latest quote · checked at the close"
    : "latest quote";
}

export default function PositionsPage() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [tracked, setTracked] = useState<TrackedPosition[] | null>(null);
  const [broker, setBroker] = useState<BrokerPosition[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!backendToken) return;
    listOpenPositions(backendToken)
      .then((r) => {
        setTracked(r);
        setError(null);
      })
      .catch((e) => setError((e as Error).message || "Failed to load."));
    // Broker holdings are a bonus section — a failure here (no connection,
    // upstream hiccup) must not take the tracked positions down with it.
    listBrokerPositions(backendToken)
      .then(setBroker)
      .catch(() => setBroker([]));
  }, [backendToken]);

  useEffect(() => {
    if (status === "loading") return;
    if (!backendToken) {
      setTracked([]);
      return;
    }
    load();
  }, [status, backendToken, load]);

  const trackedSymbols = new Set((tracked ?? []).map((p) => p.symbol));
  const untracked = broker.filter((b) => !trackedSymbols.has(b.symbol));

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-10">
      <header className="mb-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Positions
        </p>
        <h1 className="mt-1 font-heading text-2xl font-bold">
          What you&rsquo;re holding
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Positions you track against a strategy, and what happens next for
          each. Livermore never places or cancels an order on its own.
        </p>
      </header>

      {status !== "loading" && !backendToken ? (
        <p className="text-sm text-muted-foreground">
          Sign in to see your positions.
        </p>
      ) : (
        <div className="space-y-8">
          {/* 1 — decisions owed. Renders nothing when there are none. */}
          <UnresolvedExits />

          {/* 2 — tracked */}
          <section>
            <h2 className="mb-2 text-sm font-semibold text-foreground">
              Tracked positions
            </h2>

            {error ? (
              <p
                data-testid="positions-error"
                className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
              >
                Couldn&rsquo;t load your positions. {error}
              </p>
            ) : tracked === null ? (
              <div className="flex justify-center py-10">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : tracked.length === 0 ? (
              <div
                data-testid="positions-empty"
                className="rounded-lg border border-dashed border-border bg-card p-4"
              >
                <p className="text-sm text-foreground">
                  Nothing tracked yet.
                </p>
                <p className="mt-1 text-[13px] text-muted-foreground">
                  When you save a strategy you can tell us you hold the stock,
                  and we&rsquo;ll watch its exits for you.
                </p>
                <Link
                  href={"/account/strategies" as Route}
                  data-testid="positions-empty-cta"
                  className="mt-2.5 inline-flex items-center gap-1 text-[13px] font-medium text-primary underline-offset-2 hover:underline"
                >
                  Open a strategy <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            ) : (
              <ul className="space-y-2" data-testid="tracked-positions">
                {tracked.map((p) => (
                  <li
                    key={p.position_id}
                    data-testid={`tracked-${p.symbol}`}
                    className="rounded-lg border border-border/60 bg-white p-4"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-sm font-semibold text-foreground">
                          {p.shares_remaining} {p.symbol}
                        </span>
                        <Link
                          href={`/account/strategies/${p.strategy_id}` as Route}
                          className="ml-2 text-[12px] text-muted-foreground underline-offset-2 hover:underline"
                        >
                          {p.strategy_title}
                        </Link>
                      </div>
                      <div className="text-right">
                        <div
                          className={
                            "text-sm font-semibold " +
                            ((p.pct_change_from_entry ?? 0) < 0
                              ? "text-rose-600"
                              : "text-emerald-700")
                          }
                        >
                          {pct(p.pct_change_from_entry, { sign: true })}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {money(p.latest_price)} · {priceNote(p)}
                        </div>
                      </div>
                    </div>

                    <div className="mt-1 text-[12px] text-muted-foreground">
                      Cost basis {money(p.entry_price)}
                    </div>

                    {p.unresolved_count > 0 && (
                      <p
                        data-testid={`tracked-${p.symbol}-unresolved`}
                        className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[12px] font-medium text-amber-900"
                      >
                        {p.unresolved_count === 1
                          ? "A tier fired and is waiting on you."
                          : `${p.unresolved_count} tiers fired and are waiting on you.`}
                      </p>
                    )}

                    {(p.stop || p.next_target) && (
                      <dl className="mt-2.5 grid grid-cols-2 gap-2 border-t border-border/60 pt-2.5">
                        <div data-testid={`tracked-${p.symbol}-stop`}>
                          <dt className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            Stop
                          </dt>
                          <dd className="text-[13px] text-foreground">
                            {p.stop ? (
                              <>
                                {money(p.stop.price)}
                                <span className="ml-1.5 text-[11px] text-muted-foreground">
                                  {pct(p.stop.distance_pct)} away
                                </span>
                              </>
                            ) : (
                              <span className="text-muted-foreground">
                                none set
                              </span>
                            )}
                          </dd>
                        </div>
                        <div data-testid={`tracked-${p.symbol}-target`}>
                          <dt className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                            Next target
                          </dt>
                          <dd className="text-[13px] text-foreground">
                            {p.next_target ? (
                              <>
                                {money(p.next_target.price)}
                                <span className="ml-1.5 text-[11px] text-muted-foreground">
                                  {pct(p.next_target.distance_pct, { sign: true })} away
                                </span>
                              </>
                            ) : (
                              <span className="text-muted-foreground">
                                all hit
                              </span>
                            )}
                          </dd>
                        </div>
                      </dl>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* 3 — at the broker, not tracked */}
          <section>
            <h2 className="mb-2 text-sm font-semibold text-foreground">
              At your brokerage
            </h2>
            {untracked.length === 0 ? (
              <ConnectBrokerage returnPath="/account/positions" />
            ) : (
              <>
                <p className="mb-2 text-[13px] text-muted-foreground">
                  These are real holdings your broker reports.{" "}
                  <strong className="font-medium text-foreground">
                    Nothing is watching them
                  </strong>{" "}
                  — they have no strategy and no exit rules.
                </p>
                <ul className="space-y-1.5" data-testid="untracked-holdings">
                  {untracked.map((b) => (
                    <li
                      key={`${b.account_id}-${b.symbol}`}
                      data-testid={`untracked-${b.symbol}`}
                      className="flex items-baseline justify-between gap-3 rounded-lg border border-border/60 bg-card px-4 py-2.5"
                    >
                      <span className="text-sm text-foreground">
                        {b.units} {b.symbol}
                      </span>
                      <span className="text-[12px] text-muted-foreground">
                        {b.average_purchase_price
                          ? `cost ${money(b.average_purchase_price)}`
                          : "cost unknown"}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
