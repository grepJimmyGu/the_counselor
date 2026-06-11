"use client";

/**
 * <SavedStrategiesTile> — PRD-11 above-picker tile on the Home page.
 *
 * Two branches:
 *
 *   - **Signed-in user** — fetches the three most-recent saved strategies
 *     (the backend list endpoint orders by `created_at DESC`) and renders
 *     each row with its current signal status when the signal-alerts
 *     feature is enabled. The signal fetch is per-row and tolerant of the
 *     route 404'ing when `SIGNAL_ALERTS_ENABLED=false` on Railway — those
 *     rows simply skip the "In signal" chip instead of breaking the tile.
 *
 *   - **Anonymous user** — renders a compact "Sign in to access your
 *     strategies" prompt that triggers NextAuth's `signIn()`.
 *
 * Perceived load <300ms: skeleton rows render immediately when the session
 * status is `authenticated` and the fetch is in flight. The signal chips
 * fill in as each per-row fetch resolves (independent promises so a slow
 * signal call on row 1 doesn't block rows 2 and 3).
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession, signIn } from "next-auth/react";
import { ArrowRight, BookmarkCheck, LogIn } from "lucide-react";
import {
  listSavedStrategies,
  getSavedStrategySignal,
} from "@/lib/api";
import type { UserSavedStrategy } from "@/lib/contracts";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const MAX_ROWS = 3;

interface RowState {
  strategy: UserSavedStrategy;
  signalDisplay: string | null;
  asOfDate: string | null;
  signalLoading: boolean;
}

function SignalChip({ display, asOfDate }: { display: string | null; asOfDate: string | null }) {
  if (!display) {
    return (
      <span className="text-xs text-muted-foreground" aria-label="Signal not yet computed">
        Signal pending
      </span>
    );
  }
  const isLong = /\b(long|in[- ]?signal|hold|buy)\b/i.test(display);
  const isCash = /\b(cash|out[- ]?of[- ]?signal|sell|flat)\b/i.test(display);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        isLong && "border-emerald-200 bg-emerald-50 text-emerald-700",
        isCash && "border-amber-200 bg-amber-50 text-amber-700",
        !isLong && !isCash && "border-border bg-muted/60 text-muted-foreground",
      )}
      title={asOfDate ? `As of ${asOfDate}` : undefined}
    >
      {display}
    </span>
  );
}

function SkeletonRow() {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 px-4 py-3">
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-4 w-44" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-5 w-16 rounded-full" />
    </div>
  );
}

export function SavedStrategiesTile() {
  const { data: session, status } = useSession();
  const backendToken = (session as unknown as { backendToken?: string | null } | null)
    ?.backendToken ?? null;

  // `null` = list fetch in flight; `[]` = fetch complete with no rows.
  // Deriving `loading` from this avoids a redundant setState in the effect
  // body, which React 19's set-state-in-effect lint flags.
  const [rows, setRows] = useState<RowState[] | null>(null);

  useEffect(() => {
    if (status !== "authenticated" || !backendToken) return;
    let cancelled = false;

    listSavedStrategies(backendToken)
      .then((all) => {
        if (cancelled) return;
        const top = all.slice(0, MAX_ROWS);
        setRows(
          top.map((s) => ({
            strategy: s,
            signalDisplay: null,
            asOfDate: null,
            signalLoading: true,
          })),
        );

        // Fire per-row signal fetches in parallel. Each resolves
        // independently so a slow row doesn't block the others.
        top.forEach((s) => {
          getSavedStrategySignal(s.id, backendToken)
            .then((state) => {
              if (cancelled) return;
              setRows((prev) =>
                prev
                  ? prev.map((r) =>
                      r.strategy.id === s.id
                        ? {
                            ...r,
                            signalDisplay: state?.current_signal_display ?? null,
                            asOfDate: state?.as_of_date ?? null,
                            signalLoading: false,
                          }
                        : r,
                    )
                  : prev,
              );
            })
            .catch(() => {
              if (cancelled) return;
              setRows((prev) =>
                prev
                  ? prev.map((r) =>
                      r.strategy.id === s.id ? { ...r, signalLoading: false } : r,
                    )
                  : prev,
              );
            });
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
          <Link
            href={"/account/strategies" as Route}
            className="text-xs font-medium text-primary transition-colors hover:underline"
          >
            View all →
          </Link>
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
            <li key={row.strategy.id}>
              <Link
                href={`/account/strategies/${row.strategy.id}` as Route}
                className="group flex items-center justify-between gap-3 rounded-lg border border-border/60 bg-muted/20 px-4 py-3 transition-colors hover:border-primary/40 hover:bg-primary/5"
                data-testid="saved-strategy-row"
                data-strategy-id={row.strategy.id}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-foreground">
                    {row.strategy.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Saved {new Date(row.strategy.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {row.signalLoading ? (
                    <Skeleton className="h-5 w-16 rounded-full" />
                  ) : (
                    <SignalChip display={row.signalDisplay} asOfDate={row.asOfDate} />
                  )}
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
