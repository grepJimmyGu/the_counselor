/**
 * PRD-19 Step 5 — in-app notification banner.
 *
 * Renders pending banner entries written by `signal_cron`'s
 * `dispatch_in_app_banner` call. Polls `GET /api/me/notifications/pending`
 * once on mount + every 60s thereafter. Each row has a dismiss button
 * that POSTs to `/api/me/notifications/{id}/ack` and removes the row
 * optimistically.
 *
 * Surface placement:
 *   - Home (top of feed, above PRD-11's entry-mode picker for signed-in users)
 *   - Future: any logged-in surface where signal flips matter
 *
 * Anonymous users get null — the brick reads `useSession()` and renders
 * nothing when there's no `backendToken`. This matches the email side:
 * notifications are an opt-in feature gated on having an account.
 *
 * Per trap #19 (apps/api/CLAUDE.md):
 *   - Read `backendToken` off `useSession()` via cast (NextAuth doesn't
 *     expose it in the default Session type).
 *   - Effect waits for `sessionStatus !== "loading"` before firing, so
 *     signed-in users don't briefly fire an anonymous request.
 *
 * The banner is **non-critical** — if the fetch fails, we render
 * nothing. We never block the page on it.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";

import {
  ackNotificationBanner,
  getPendingNotifications,
} from "@/lib/api";
import type { PendingNotificationBanner } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { MarkAsExecutedButton } from "./mark-as-executed-button";

const POLL_INTERVAL_MS = 60_000;

interface NotificationBannerProps {
  className?: string;
  /** Cap on how many rows to show. Defaults to 3 — past that we add a
   *  "+N more" affordance for now (Step 6 settings page links to the
   *  full inbox). Backend already limits to 10. */
  maxShown?: number;
}

export function NotificationBanner({
  className,
  maxShown = 3,
}: NotificationBannerProps) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [items, setItems] = useState<PendingNotificationBanner[]>([]);
  const [dismissing, setDismissing] = useState<Set<number>>(new Set());
  const tokenRef = useRef<string | undefined>(undefined);

  // Keep tokenRef in sync without re-creating the poll callback identity.
  tokenRef.current = backendToken;

  const fetchPending = useCallback(async () => {
    const token = tokenRef.current;
    if (!token) return;
    try {
      const rows = await getPendingNotifications(token);
      setItems(rows);
    } catch {
      // Non-critical surface; on error just keep whatever we had.
    }
  }, []);

  // Initial fetch + polling. The effect waits for NextAuth to resolve
  // out of `loading` so signed-in users don't briefly fire an anon
  // request (trap #19).
  useEffect(() => {
    if (sessionStatus === "loading") return;
    if (!backendToken) {
      setItems([]);
      return;
    }
    fetchPending();
    const interval = setInterval(fetchPending, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [backendToken, fetchPending, sessionStatus]);

  const handleDismiss = useCallback(
    async (entryId: number) => {
      const token = tokenRef.current;
      if (!token) return;
      // Optimistic: remove the row immediately + track in-flight so a
      // failed ack can rollback if needed.
      setDismissing((prev) => new Set(prev).add(entryId));
      setItems((prev) => prev.filter((it) => it.id !== entryId));
      try {
        await ackNotificationBanner(entryId, token);
      } catch {
        // Rollback: re-fetch to reconcile with backend truth.
        fetchPending();
      } finally {
        setDismissing((prev) => {
          const next = new Set(prev);
          next.delete(entryId);
          return next;
        });
      }
    },
    [fetchPending],
  );

  // Don't render anything for anonymous or while NextAuth is still loading.
  if (sessionStatus === "loading" || !backendToken) return null;
  if (items.length === 0) return null;

  const shown = items.slice(0, maxShown);
  const overflow = items.length - shown.length;

  return (
    <section
      aria-label="Signal notifications"
      data-testid="notification-banner"
      className={cn("flex flex-col gap-2", className)}
    >
      {shown.map((item) => (
        <BannerRow
          key={item.id}
          item={item}
          dismissing={dismissing.has(item.id)}
          onDismiss={() => handleDismiss(item.id)}
        />
      ))}
      {overflow > 0 ? (
        <p className="px-2 text-[11px] text-slate-500">
          +{overflow} more in your{" "}
          <Link
            href={"/account/notifications" as Route}
            className="font-medium text-slate-700 underline-offset-2 hover:underline"
          >
            notification inbox
          </Link>
        </p>
      ) : null}
    </section>
  );
}

interface BannerRowProps {
  item: PendingNotificationBanner;
  dismissing: boolean;
  onDismiss: () => void;
}

function BannerRow({ item, dismissing, onDismiss }: BannerRowProps) {
  // `strategy_slug` carries the SavedStrategy.id (Step 3b's signal_cron
  // sets `strategy_slug=strat.id` when it constructs the SignalChangeEvent
  // for `dispatch_in_app_banner`). The link target goes to the public
  // strategy detail page; the inline button targets the saved-strategies
  // mark-executed endpoint.
  const strategyId = item.strategy_slug;
  const href = strategyId
    ? `/strategies/${encodeURIComponent(strategyId)}`
    : null;

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          {href ? (
            <Link
              href={href as Route}
              className="block focus:outline-none focus-visible:underline"
            >
              <p className="truncate text-sm font-semibold text-slate-900 hover:underline">
                {item.title}
              </p>
            </Link>
          ) : (
            <p className="truncate text-sm font-semibold text-slate-900">
              {item.title}
            </p>
          )}
          <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
            {item.body}
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          disabled={dismissing}
          aria-label="Dismiss"
          title="Dismiss"
          className="-mr-1 -mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-amber-100 hover:text-slate-900 disabled:opacity-40"
          data-testid={`notification-dismiss-${item.id}`}
        >
          <DismissIcon />
        </button>
      </div>
      {strategyId ? (
        <div className="mt-2.5 flex items-center gap-2">
          <MarkAsExecutedButton strategyId={strategyId} />
          <Link
            href={`/strategies/${encodeURIComponent(strategyId)}` as Route}
            className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
          >
            View strategy →
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function DismissIcon() {
  return (
    <svg
      aria-hidden
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
