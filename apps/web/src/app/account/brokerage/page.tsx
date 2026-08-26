"use client";

/**
 * /account/brokerage — your account, as your broker sees it.
 *
 * Connect once and everything appears: what you hold and what it cost, every
 * buy and sell, how the account has actually done, its value over time, and
 * the orders on file.
 *
 * NO STRATEGY LENS, DELIBERATELY. Nothing here is matched to a Livermore
 * strategy. Most of a person's trades predate any strategy they built here,
 * and a strategy lens would hide exactly those — which are the majority, and
 * the interesting ones. This page is the raw record; interpreting it is a
 * separate job.
 *
 * PERFORMANCE IS THE BROKER'S NUMBER. We never see the deposits and
 * withdrawals that make a return figure mean anything, so we pass theirs
 * through rather than computing one from an incomplete picture and putting
 * our name on it.
 *
 * EVERY SECTION FAILS ALONE. Five independent reads against a third party;
 * one broker having a bad morning must cost you that section, not the page.
 *
 * Trap #19: reads `backendToken` off `useSession()` and waits for the session
 * to resolve before fetching.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { Loader2 } from "lucide-react";

import {
  getBrokerBalanceHistory,
  getBrokerPerformance,
  getSnapTradeStatus,
  listBrokerActivities,
  listBrokerOrders,
  listBrokerPositions,
} from "@/lib/api";
import type { BrokerActivity, BrokerPosition } from "@/lib/contracts";
import { ConnectBrokerage } from "@/components/execution/connect-brokerage";

type Row = Record<string, unknown>;
type Window = "1M" | "6M" | "1Y";

const WINDOW_DAYS: Record<Window, number> = { "1M": 30, "6M": 182, "1Y": 365 };

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function money(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function pct(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  // Brokers report either a fraction or a percent. A |value| under 1.5 is
  // almost certainly a fraction; above that, already a percent. Guessing is
  // unavoidable here, so guess conservatively and never show 1840%.
  const asPct = Math.abs(n) <= 1.5 ? n * 100 : n;
  return `${asPct > 0 ? "+" : ""}${asPct.toFixed(1)}%`;
}

/** The broker's field names differ; take the first that exists. */
function pick(row: Row, ...keys: string[]): unknown {
  for (const k of keys) if (row[k] !== undefined && row[k] !== null) return row[k];
  return undefined;
}

export default function BrokeragePage() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [connected, setConnected] = useState<boolean | null>(null);
  const [positions, setPositions] = useState<BrokerPosition[]>([]);
  const [activities, setActivities] = useState<BrokerActivity[] | null>(null);
  const [performance, setPerformance] = useState<Row[]>([]);
  const [balances, setBalances] = useState<Row[]>([]);
  const [orders, setOrders] = useState<Row[]>([]);
  const [window, setWindow] = useState<Window>("1Y");

  // Each read is independent — a failure costs that section, not the page.
  const load = useCallback(() => {
    if (!backendToken) return;
    getSnapTradeStatus(backendToken)
      .then((s) => setConnected(Boolean(s.registered && s.connected_accounts > 0)))
      .catch(() => setConnected(false));
    listBrokerPositions(backendToken).then(setPositions).catch(() => setPositions([]));
    getBrokerPerformance(backendToken).then(setPerformance).catch(() => setPerformance([]));
    getBrokerBalanceHistory(backendToken).then(setBalances).catch(() => setBalances([]));
    listBrokerOrders(backendToken, 30).then(setOrders).catch(() => setOrders([]));
  }, [backendToken]);

  useEffect(() => {
    if (status === "loading") return;
    if (!backendToken) {
      setConnected(false);
      return;
    }
    load();
  }, [status, backendToken, load]);

  // History refetches when the window changes — the broker filters, not us.
  useEffect(() => {
    if (!backendToken || !connected) return;
    let live = true;
    setActivities(null);
    listBrokerActivities(backendToken, {
      startDate: isoDaysAgo(WINDOW_DAYS[window]), limit: 500,
    })
      .then((rows) => {
        if (live) setActivities(rows);
      })
      .catch(() => {
        if (live) setActivities([]);
      });
    return () => {
      live = false;
    };
  }, [backendToken, connected, window]);

  const marketValue = useMemo(
    () => positions.reduce(
      (sum, p) => sum + (p.units ?? 0) * (p.last_price ?? p.average_purchase_price ?? 0),
      0,
    ),
    [positions],
  );

  const trades = useMemo(
    () => (activities ?? []).filter(
      (a) => (a.type ?? "").toUpperCase() === "BUY" || (a.type ?? "").toUpperCase() === "SELL",
    ),
    [activities],
  );

  if (status !== "loading" && !backendToken) {
    return (
      <main className="mx-auto min-h-screen max-w-4xl px-4 py-10">
        <p className="text-sm text-muted-foreground">
          Sign in to see your brokerage.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-10">
      <header className="mb-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Brokerage
        </p>
        <h1 className="mt-1 font-heading text-2xl font-bold">Your account</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What your broker reports — holdings, trades, and performance. Read
          only; Livermore never places an order you haven&rsquo;t approved.
        </p>
      </header>

      {connected === null ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : !connected ? (
        <ConnectBrokerage returnPath="/account/brokerage" />
      ) : (
        <div className="space-y-8">
          {/* ── holdings ─────────────────────────────────────────── */}
          <section>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h2 className="text-sm font-semibold">Holdings</h2>
              <span
                data-testid="brokerage-market-value"
                className="font-mono text-[13px] tabular-nums text-foreground"
              >
                {money(marketValue)}
              </span>
            </div>
            {positions.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">
                Your broker reports no open positions.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[34rem] border-collapse text-sm">
                  <thead>
                    <tr className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-3 py-2 text-left font-semibold">Symbol</th>
                      <th className="px-3 py-2 text-right font-semibold">Shares</th>
                      <th className="px-3 py-2 text-right font-semibold">Cost</th>
                      <th className="px-3 py-2 text-right font-semibold">Last</th>
                      <th className="px-3 py-2 text-right font-semibold">Open P/L</th>
                    </tr>
                  </thead>
                  <tbody data-testid="brokerage-holdings">
                    {positions.map((p) => (
                      <tr key={`${p.account_id}-${p.symbol}`} className="border-t border-border">
                        <td className="px-3 py-2 font-medium">{p.symbol}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">{p.units}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">
                          {money(p.average_purchase_price)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">
                          {money(p.last_price)}
                        </td>
                        <td
                          className={
                            "px-3 py-2 text-right font-mono tabular-nums " +
                            ((p.open_pnl ?? 0) < 0 ? "text-rose-600" : "text-emerald-700")
                          }
                        >
                          {money(p.open_pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* ── performance ──────────────────────────────────────── */}
          <section>
            <h2 className="mb-2 text-sm font-semibold">Performance</h2>
            {performance.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">
                Your broker doesn&rsquo;t report return rates for this account.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2" data-testid="brokerage-performance">
                {performance.map((r, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-border bg-card px-4 py-2.5"
                  >
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      {String(pick(r, "timeframe", "period", "label") ?? "—")}
                    </div>
                    <div className="mt-0.5 font-mono text-base font-semibold tabular-nums">
                      {pct(pick(r, "rate_of_return", "return_rate", "rate", "value"))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              Your broker&rsquo;s own figures. We don&rsquo;t see your deposits
              and withdrawals, so we don&rsquo;t compute this ourselves.
            </p>
          </section>

          {/* ── balance over time ────────────────────────────────── */}
          {balances.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-semibold">Account value</h2>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[20rem] border-collapse text-sm">
                  <tbody data-testid="brokerage-balances">
                    {balances.slice(-12).reverse().map((b, i) => (
                      <tr key={i} className="border-t border-border first:border-t-0">
                        <td className="px-3 py-1.5 font-mono text-[12px] text-muted-foreground">
                          {String(pick(b, "date", "as_of", "timestamp") ?? "—")}
                        </td>
                        <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                          {money(pick(b, "value", "total_value", "balance"))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ── trade history ────────────────────────────────────── */}
          <section>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="text-sm font-semibold">Buys and sells</h2>
              <div className="flex gap-1" role="group" aria-label="History window">
                {(["1M", "6M", "1Y"] as Window[]).map((w) => (
                  <button
                    key={w}
                    type="button"
                    onClick={() => setWindow(w)}
                    data-testid={`brokerage-window-${w}`}
                    aria-pressed={window === w}
                    className={
                      "rounded-md border px-2.5 py-1 text-[12px] font-medium transition " +
                      (window === w
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-accent")
                    }
                  >
                    {w}
                  </button>
                ))}
              </div>
            </div>

            {activities === null ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : trades.length === 0 ? (
              <p data-testid="brokerage-no-trades" className="text-[13px] text-muted-foreground">
                No buys or sells in this window.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[34rem] border-collapse text-sm">
                  <thead>
                    <tr className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-3 py-2 text-left font-semibold">Date</th>
                      <th className="px-3 py-2 text-left font-semibold">Side</th>
                      <th className="px-3 py-2 text-left font-semibold">Symbol</th>
                      <th className="px-3 py-2 text-right font-semibold">Shares</th>
                      <th className="px-3 py-2 text-right font-semibold">Price</th>
                      <th className="px-3 py-2 text-right font-semibold">Amount</th>
                    </tr>
                  </thead>
                  <tbody data-testid="brokerage-trades">
                    {trades.map((a, i) => {
                      const side = (a.type ?? "").toUpperCase();
                      return (
                        <tr key={a.activity_id ?? i} className="border-t border-border">
                          {/* trade_date, not settlement_date — when it happened. */}
                          <td className="px-3 py-2 font-mono text-[12px] text-muted-foreground">
                            {a.trade_date ?? "—"}
                          </td>
                          <td
                            className={
                              "px-3 py-2 font-semibold " +
                              (side === "SELL" ? "text-rose-600" : "text-emerald-700")
                            }
                          >
                            {side}
                          </td>
                          <td className="px-3 py-2 font-medium">{a.symbol ?? "—"}</td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums">
                            {a.units ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums">
                            {money(a.price)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums">
                            {money(a.amount)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* ── recent orders ────────────────────────────────────── */}
          {orders.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-semibold">Recent orders</h2>
              <p className="mb-2 text-[12px] text-muted-foreground">
                Last 30 days, including orders you placed elsewhere.
              </p>
              <ul className="space-y-1.5" data-testid="brokerage-orders">
                {orders.slice(0, 20).map((o, i) => (
                  <li
                    key={i}
                    className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-border bg-card px-4 py-2 text-[13px]"
                  >
                    <span className="font-medium">
                      {String(pick(o, "action", "side") ?? "")}{" "}
                      {String(pick(o, "symbol", "universal_symbol") ?? "—")}
                    </span>
                    <span className="font-mono text-[12px] text-muted-foreground">
                      {String(pick(o, "status", "state") ?? "—")}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
