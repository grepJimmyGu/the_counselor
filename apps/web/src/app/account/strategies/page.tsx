/**
 * /account/strategies — "My Strategies" repo.
 *
 * Lists the user's saved strategies (the SavedStrategy table — these are
 * the active-execution + portfolio-mode strategies that have a live
 * dashboard). Each row links to `/account/strategies/{id}` where the
 * dashboard renders. Reached from the home "Your saved strategies" tile
 * and from the composer's post-save screen.
 *
 * Trap #19: reads `backendToken` off `useSession()`, fetches after the
 * session resolves.
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import { ArrowRight, Loader2 } from "lucide-react";

import { listSavedStrategies } from "@/lib/api";
import type { UserSavedStrategy } from "@/lib/contracts";

function isActiveExecution(s: UserSavedStrategy): boolean {
  const json = (s.strategy_json ?? {}) as { bar_resolution?: string };
  return !!json.bar_resolution && json.bar_resolution !== "daily";
}

export default function MyStrategiesPage() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [rows, setRows] = useState<UserSavedStrategy[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "loading") return;
    if (!backendToken) {
      setRows([]);
      return;
    }
    listSavedStrategies(backendToken)
      .then((r) => {
        setRows(r);
        setError(null);
      })
      .catch((e) => setError((e as Error).message || "Failed to load."));
  }, [status, backendToken]);

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-10">
      <header className="mb-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          My strategies
        </p>
        <h1 className="mt-1 font-heading text-2xl font-bold">
          Your saved strategies
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Open any strategy to see its live dashboard — positions, exit
          ladder, and trade log.
        </p>
      </header>

      {status !== "loading" && !backendToken ? (
        <p className="text-sm text-muted-foreground">
          Sign in to see your saved strategies.
        </p>
      ) : error ? (
        <p
          data-testid="my-strategies-error"
          className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        >
          Couldn&rsquo;t load your strategies. {error}
        </p>
      ) : rows === null ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : rows.length === 0 ? (
        <div
          data-testid="my-strategies-empty"
          className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground"
        >
          You haven&rsquo;t saved a live strategy yet. Build one with{" "}
          <Link
            href={"/flow/custom_build_mode" as Route}
            className="text-primary underline underline-offset-2"
          >
            Build from scratch
          </Link>
          .
        </div>
      ) : (
        <ul className="space-y-2" data-testid="my-strategies-list">
          {rows.map((s) => (
            <li key={s.id}>
              <Link
                href={`/account/strategies/${s.id}` as Route}
                data-testid={`my-strategy-row-${s.id}`}
                className="group flex items-center justify-between gap-3 rounded-lg border border-border/60 bg-white px-4 py-3 transition-colors hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-foreground">
                    {s.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Saved {new Date(s.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {isActiveExecution(s) && (
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                      Live
                    </span>
                  )}
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
