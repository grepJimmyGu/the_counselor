/**
 * /screens — "My Screens" repo (PRD-23c).
 *
 * Lists the user's tracked standing screens (SavedStrategy rows with
 * kind=="screen"). Distinct from /account/strategies, which lists the
 * single-asset / active-execution strategies — a screen's "position" is a
 * basket of names that gains and loses members as the market moves, so it
 * has its own surface here. Each row links to `/screens/{id}` where the
 * current basket + entrant/exit history render.
 *
 * Reached from the composer's post-save "Save + track" confirmation.
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

import { listSavedScreens } from "@/lib/api";
import type { SavedScreenSummary } from "@/lib/contracts";
import { universeLabel } from "@/lib/screen-universe";

export default function MyScreensPage() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [rows, setRows] = useState<SavedScreenSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "loading") return;
    if (!backendToken) {
      setRows([]);
      return;
    }
    listSavedScreens({ backendToken })
      .then((r) => {
        setRows(r.screens);
        setError(null);
      })
      .catch((e) => setError((e as Error).message || "Failed to load."));
  }, [status, backendToken]);

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-10">
      <header className="mb-6">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          My screens
        </p>
        <h1 className="mt-1 font-heading text-2xl font-bold">
          Your tracked screens
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Open any screen to see its current basket and the entrant/exit
          history — who&rsquo;s passing your reading right now, and who came and
          went.
        </p>
      </header>

      {status !== "loading" && !backendToken ? (
        <p className="text-sm text-muted-foreground">
          Sign in to see your tracked screens.
        </p>
      ) : error ? (
        <p
          data-testid="my-screens-error"
          className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        >
          Couldn&rsquo;t load your screens. {error}
        </p>
      ) : rows === null ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : rows.length === 0 ? (
        <div
          data-testid="my-screens-empty"
          className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground"
        >
          You aren&rsquo;t tracking a screen yet. Compose a reading with{" "}
          <Link
            href={"/flow/custom_build_mode" as Route}
            className="text-primary underline underline-offset-2"
          >
            Screen the market
          </Link>
          , then &ldquo;Save + track&rdquo; it.
        </div>
      ) : (
        <ul className="space-y-2" data-testid="my-screens-list">
          {rows.map((s) => (
            <li key={s.saved_strategy_id}>
              <Link
                href={`/screens/${s.saved_strategy_id}` as Route}
                data-testid={`my-screen-row-${s.saved_strategy_id}`}
                className="group flex items-center justify-between gap-3 rounded-lg border border-border/60 bg-white px-4 py-3 transition-colors hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-foreground">
                    {s.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {universeLabel(s.universe_id)}
                    {s.created_at
                      ? ` · tracked since ${new Date(
                          s.created_at,
                        ).toLocaleDateString()}`
                      : ""}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-700">
                    {s.basket_size} in basket
                  </span>
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
