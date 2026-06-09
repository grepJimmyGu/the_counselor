/**
 * PRD-19 Step 5 — Mark-as-Executed brick.
 *
 * Closes the retention metric loop on the user side: clicking this
 * button POSTs to `/api/saved-strategies/{strategy_id}/mark-executed`,
 * which writes a `MarkAsExecutedEvent` row and fires PostHog
 * `notification_executed`. Sprint A's dashboard joins that against
 * `notification_dispatched` on `signal_event_id` to compute
 * `latency_seconds` (HANDOFF §7).
 *
 * Behavior:
 *   - **Optimistic**: click → button immediately shows "Marked — ✓"
 *     state, POST in background.
 *   - **Idempotent**: repeat-click on the same signal-event returns
 *     `idempotent: true`. The button renders the same confirmed state
 *     whether the row was created or already existed; no toast spam.
 *   - **Failure**: revert to the unmarked state + show an inline error
 *     (no toast — toasts are easy to miss). User can retry.
 *   - **Auth**: requires `backendToken` from `useSession()` per trap #19.
 *     If the user isn't signed in, the button renders disabled with a
 *     "Sign in to track" hint.
 *
 * The backend already enforces ownership (404 for non-owners — same
 * message as missing, no existence leak), so we don't pre-check ownership
 * on the frontend. We just submit and handle the 404 case.
 */
"use client";

import { useCallback, useState } from "react";
import { useSession } from "next-auth/react";

import { markStrategyExecuted } from "@/lib/api";
import { cn } from "@/lib/utils";

interface MarkAsExecutedButtonProps {
  /** Saved-strategy ID the user is attesting they acted on. */
  strategyId: string;
  /** Optional className override for the outer button. */
  className?: string;
  /** Optional callback fired after the POST resolves (success or
   *  idempotent). Useful for the parent surface to flip a chip,
   *  refresh a counter, etc. */
  onMarked?: (info: {
    idempotent: boolean;
    executed_at: string;
    latency_seconds: number;
  }) => void;
}

type ButtonState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "marked"; at: string; idempotent: boolean }
  | { kind: "error"; message: string };

export function MarkAsExecutedButton({
  strategyId,
  className,
  onMarked,
}: MarkAsExecutedButtonProps) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [state, setState] = useState<ButtonState>({ kind: "idle" });

  const handleClick = useCallback(async () => {
    if (!backendToken) return;
    if (state.kind === "submitting" || state.kind === "marked") return;

    setState({ kind: "submitting" });
    try {
      const resp = await markStrategyExecuted(
        strategyId,
        { user_note: null },
        backendToken,
      );
      setState({
        kind: "marked",
        at: resp.executed_at,
        idempotent: resp.idempotent,
      });
      onMarked?.({
        idempotent: resp.idempotent,
        executed_at: resp.executed_at,
        latency_seconds: resp.latency_seconds,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Couldn't record. Try again.";
      setState({ kind: "error", message });
    }
  }, [backendToken, onMarked, state.kind, strategyId]);

  // Anonymous / NextAuth still loading — render a hint, not a broken button.
  if (sessionStatus === "loading") {
    return (
      <button
        type="button"
        disabled
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-400",
          className,
        )}
      >
        <span>I executed this</span>
      </button>
    );
  }
  if (!backendToken) {
    return (
      <button
        type="button"
        disabled
        title="Sign in to track when you act on a signal"
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-400",
          className,
        )}
      >
        <span>Sign in to track</span>
      </button>
    );
  }

  if (state.kind === "marked") {
    const formatted = formatExecutedAt(state.at);
    return (
      <button
        type="button"
        disabled
        data-testid="mark-as-executed-marked"
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700",
          className,
        )}
      >
        <CheckIcon />
        <span>
          {state.idempotent ? "Already marked" : "Marked"}
          {formatted ? <span className="text-emerald-600/70"> · {formatted}</span> : null}
        </span>
      </button>
    );
  }

  if (state.kind === "error") {
    return (
      <div className={cn("inline-flex flex-col items-start gap-1", className)}>
        <button
          type="button"
          onClick={handleClick}
          className="inline-flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-100"
        >
          <span>Try again — I executed this</span>
        </button>
        <p className="text-[11px] text-rose-600">{state.message}</p>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={state.kind === "submitting"}
      data-testid="mark-as-executed-idle"
      className={cn(
        "inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60",
        className,
      )}
    >
      <span>
        {state.kind === "submitting" ? "Recording…" : "I executed this"}
      </span>
    </button>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

/**
 * "Today at 4:05 PM" / "Yesterday at 9:30 AM" / "Jun 5, 4:05 PM".
 * Falls back to the raw ISO string if parsing fails.
 */
function formatExecutedAt(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();
  const time = d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  if (sameDay) return `today at ${time}`;
  if (isYesterday) return `yesterday at ${time}`;
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} at ${time}`;
}
