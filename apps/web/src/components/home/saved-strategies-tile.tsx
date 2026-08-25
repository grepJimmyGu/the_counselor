"use client";

/**
 * <SavedStrategiesTile> — PRD-11 above-picker tile on the Home page.
 *
 * Two branches:
 *
 *   - **Signed-in user** — fetches the three most-recent saved strategies
 *     (the backend list endpoint orders by `created_at DESC`) and renders
 *     each as a <SignalCard> (PRD-25). Signal state comes from ONE batched
 *     `/api/signals/card/batch` call rather than a per-row fetch — the card
 *     endpoint is always mounted, returning `pending` cards until the signal
 *     cron populates state, so there's no route-404 dance any more.
 *
 *   - **Anonymous user** — renders a compact "Sign in to access your
 *     strategies" prompt that triggers NextAuth's `signIn()`.
 *
 * Perceived load <300ms: skeleton rows render immediately when the session
 * status is `authenticated` and the fetch is in flight; the single batch call
 * then fills every card at once.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession, signIn } from "next-auth/react";
import { BookmarkCheck, LogIn } from "lucide-react";

import { listSavedStrategies, getSignalCardsBatch } from "@/lib/api";
import type { SignalCard as SignalCardType, UserSavedStrategy } from "@/lib/contracts";
import { SignalCard } from "@/components/signals/signal-card";
import { Skeleton } from "@/components/ui/skeleton";

const MAX_ROWS = 3;

interface RowState {
  strategy: UserSavedStrategy;
  card: SignalCardType | null;
  loading: boolean;
}

function SkeletonRow() {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <Skeleton className="h-4 w-44" />
      <Skeleton className="mt-1.5 h-3 w-24" />
      <Skeleton className="mt-2 h-5 w-20 rounded-full" />
    </div>
  );
}

function FallbackRow({ strategy }: { strategy: UserSavedStrategy }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <Link
        href={`/account/strategies/${strategy.id}` as Route}
        className="block truncate text-sm font-semibold text-foreground hover:text-primary"
      >
        {strategy.title}
      </Link>
      <p className="text-xs text-muted-foreground">
        Saved {new Date(strategy.created_at).toLocaleDateString()}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">Signal unavailable right now.</p>
    </div>
  );
}

export function SavedStrategiesTile() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string | null } | null)
    ?.backendToken ?? null;

  // `null` = list fetch in flight; `[]` = fetch complete with no rows.
  const [rows, setRows] = useState<RowState[] | null>(null);

  useEffect(() => {
    if (status !== "authenticated" || !backendToken) return;
    let cancelled = false;

    listSavedStrategies(backendToken)
      .then((all) => {
        if (cancelled) return;
        const top = all.slice(0, MAX_ROWS);
        setRows(top.map((s) => ({ strategy: s, card: null, loading: true })));
        if (top.length === 0) return;

        // ONE batched call warms every row's card (spec: batch = one cached
        // call, no per-row fan-out).
        getSignalCardsBatch(
          top.map((s) => s.id),
          backendToken,
        )
          .then((cards) => {
            if (cancelled) return;
            const byId = new Map(cards.map((c) => [c.saved_strategy_id, c]));
            setRows((prev) =>
              prev
                ? prev.map((r) => ({
                    ...r,
                    card: byId.get(r.strategy.id) ?? null,
                    loading: false,
                  }))
                : prev,
            );
          })
          .catch(() => {
            if (cancelled) return;
            setRows((prev) => (prev ? prev.map((r) => ({ ...r, loading: false })) : prev));
          });
      })
      .catch(() => {
        if (cancelled) return;
        setRows([]);
      });

    return () => {
      cancelled = true;
    };
  }, [status, backendToken]);

  const loading = status === "authenticated" && rows === null;

  if (status === "loading") {
    return (
      <section
        aria-label="Your saved strategies"
        data-testid="saved-strategies-tile"
        className="rounded-2xl border border-border bg-white p-5 shadow-sm"
      >
        <div className="mb-4 flex items-center gap-2">
          <Skeleton className="h-4 w-4 rounded" />
          <Skeleton className="h-4 w-44" />
        </div>
        <div className="space-y-2">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      </section>
    );
  }

  if (status !== "authenticated") {
    return (
      <section
        aria-label="Sign in to access your saved strategies"
        data-testid="saved-strategies-signin-prompt"
        className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-white px-5 py-4 shadow-sm"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/5">
            <BookmarkCheck className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">
              Sign in to access your strategies
            </h2>
            <p className="text-xs text-muted-foreground">
              Saved strategies show their current signal status here so you can act when the
              market shifts.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => signIn()}
          data-testid="saved-strategies-signin-btn"
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-primary bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <LogIn className="h-3.5 w-3.5" />
          Sign in
        </button>
      </section>
    );
  }

  return (
    <section
      aria-label="Your saved strategies"
      data-testid="saved-strategies-tile"
      className="rounded-2xl border border-border bg-white p-5 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between gap-2">
        {/* The heading itself is an entry into the My Strategies repo —
            available in every state (loading / empty / populated), unlike
            "View all →" which only renders when there are saved rows. */}
        <Link
          href={"/account/strategies" as Route}
          data-testid="saved-strategies-tile-heading"
          className="group flex items-center gap-2 rounded-md transition-colors hover:text-primary"
        >
          <BookmarkCheck className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground group-hover:text-primary">
            Your saved strategies
          </h2>
        </Link>
        {rows && rows.length > 0 && (
          <div className="flex items-center gap-3">
            {/* PRD-28 Step 4. Someone with saved strategies is exactly who
                wants "what am I holding" — and this tile is the highest-
                traffic place they already look. */}
            <Link
              href={"/account/positions" as Route}
              data-testid="saved-strategies-tile-positions"
              className="text-xs font-medium text-primary transition-colors hover:underline"
            >
              Positions
            </Link>
            <Link
              href={"/account/strategies" as Route}
              className="text-xs font-medium text-primary transition-colors hover:underline"
            >
              View all →
            </Link>
          </div>
        )}
      </div>

      {loading || rows === null ? (
        <div className="space-y-2">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-5 text-center text-sm text-muted-foreground">
          You haven&rsquo;t saved a strategy yet. Pick an entry point below to build your first one.
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={row.strategy.id}
              data-testid="saved-strategy-row"
              data-strategy-id={row.strategy.id}
            >
              {row.loading ? (
                <SkeletonRow />
              ) : row.card ? (
                <SignalCard
                  card={row.card}
                  href={`/account/strategies/${row.strategy.id}` as Route}
                  subtitle={`Saved ${new Date(row.strategy.created_at).toLocaleDateString()}`}
                />
              ) : (
                <FallbackRow strategy={row.strategy} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
