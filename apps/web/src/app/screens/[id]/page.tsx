/**
 * /screens/[id] — one tracked screen's dashboard (PRD-23c).
 *
 * Keyed on the SavedStrategy UUID (the saved-screen endpoint is owner-only
 * on this id). Renders three things:
 *   1. the reading (the composed rules the screen scans for),
 *   2. the CURRENT basket — the names passing the reading right now,
 *   3. the entrant/exit history — every membership stint, newest first.
 *
 * A non-owner / non-screen id returns 404 from the API → "not found" state.
 *
 * Trap #19: reads `backendToken` off `useSession()`.
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { ArrowLeft, Loader2 } from "lucide-react";

import { getSavedScreen } from "@/lib/api";
import type { SavedScreenDetail, StrategyRule } from "@/lib/contracts";
import { universeLabel } from "@/lib/screen-universe";

const OPERATOR_COPY: Record<string, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
  crosses_up: "crosses up",
  crosses_down: "crosses down",
  fires: "fires",
  is_true: "is true",
  in_range: "in range",
  equals: "=",
  divergence_bullish: "bullish divergence",
  divergence_bearish: "bearish divergence",
};

function formatThreshold(t: StrategyRule["threshold"]): string {
  if (t === undefined || t === null) return "";
  if (typeof t === "object") return `${t.min}–${t.max}`;
  return String(t);
}

/** A compact human reading of one rule — "rsi < 30", "macd_cross fires". */
function ruleReading(rule: StrategyRule): string {
  const indicator = rule.indicator ?? rule.source ?? "signal";
  const op = rule.operator ? OPERATOR_COPY[rule.operator] ?? rule.operator : "";
  const threshold = formatThreshold(rule.threshold);
  return [indicator, op, threshold].filter(Boolean).join(" ");
}

export default function SavedScreenDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [screen, setScreen] = useState<SavedScreenDetail | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (status === "loading" || !backendToken) return;
    getSavedScreen(id, { backendToken })
      .then((s) => {
        setScreen(s);
        setNotFound(false);
      })
      .catch(() => setNotFound(true));
  }, [status, backendToken, id]);

  const loading = (status === "loading" || (!screen && !notFound));

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-10">
      <Link
        href={"/screens" as Route}
        className="mb-4 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> My screens
      </Link>

      {status !== "loading" && !backendToken ? (
        <p className="text-sm text-muted-foreground">
          Sign in to view this screen.
        </p>
      ) : notFound ? (
        <p
          data-testid="screen-not-found"
          className="text-sm text-muted-foreground"
        >
          Screen not found, or you don&rsquo;t have access to it.
        </p>
      ) : loading || !screen ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <header className="mb-6">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {universeLabel(screen.universe_id)}
            </p>
            <h1 className="mt-1 font-heading text-2xl font-bold">
              {screen.title}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {screen.basket_size}{" "}
              {screen.basket_size === 1 ? "name" : "names"} pass this reading
              right now.
            </p>
          </header>

          {/* The reading — the rules the screen scans for. */}
          {screen.rules.length > 0 && (
            <section className="mb-8" data-testid="screen-reading">
              <h2 className="mb-2 text-sm font-semibold text-foreground">
                The reading
              </h2>
              <ul className="flex flex-wrap gap-2">
                {screen.rules.map((rule, i) => (
                  <li
                    key={i}
                    className="rounded-md border border-border/60 bg-muted/30 px-2.5 py-1 font-mono text-xs text-foreground"
                  >
                    {ruleReading(rule)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Current basket. */}
          <section className="mb-8" data-testid="screen-basket">
            <h2 className="mb-2 text-sm font-semibold text-foreground">
              Current basket
            </h2>
            {screen.basket.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                No names pass the reading right now. You&rsquo;ll be notified
                when one enters.
              </p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {screen.basket.map((sym) => (
                  <li
                    key={sym}
                    className="rounded-md bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-700"
                  >
                    {sym}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Entrant/exit history. */}
          <section data-testid="screen-history">
            <h2 className="mb-2 text-sm font-semibold text-foreground">
              Entrant / exit history
            </h2>
            {screen.history.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No history yet — the basket hasn&rsquo;t changed since you
                started tracking.
              </p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border/60">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Entered</th>
                      <th className="px-3 py-2 text-left">Exited</th>
                      <th className="px-3 py-2 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {screen.history.map((h, i) => (
                      <tr
                        key={`${h.symbol}-${h.entered_date}-${i}`}
                        className="border-t border-border/40"
                      >
                        <td className="px-3 py-2 font-medium text-foreground">
                          {h.symbol}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {new Date(h.entered_date).toLocaleDateString()}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {h.exited_date
                            ? new Date(h.exited_date).toLocaleDateString()
                            : "—"}
                        </td>
                        <td className="px-3 py-2">
                          {h.is_current ? (
                            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                              In basket
                            </span>
                          ) : (
                            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              Exited
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
