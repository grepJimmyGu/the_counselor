"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import { Bell, BellRing, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { subscribeSignalAlert, unsubscribeSignalAlert } from "@/lib/api";

/**
 * Post-results signal-alert opt-in CTA — PR-E, 2026-05-24.
 *
 * Renders BELOW the backtest results metrics card. Wires to the
 * PR #83 endpoints (`POST/DELETE /api/saved-strategies/{id}/signal/subscribe`),
 * which require `SIGNAL_ALERTS_ENABLED=true` on Railway.
 *
 * Three render states:
 *   1. Anonymous user → "Sign in to track" (no API call; routes to /login)
 *   2. Signed-in, not subscribed → "Get email alerts" button (POST)
 *   3. Subscribed → "Email alerts on" + "Turn off" (DELETE)
 *
 * Per the rebuild plan, this PR only wires the opt-in handshake.
 * The daily recompute cron, email body template, and full SignalPanel
 * UI are PR #83's Phase B/C/D — still backlogged. So opting in today
 * stores the subscription but no emails fire until the cron lands.
 *
 * If the backend returns 404 (flag not enabled), the CTA shows a
 * grey "Email alerts not yet available" state and disables the
 * button — so the page never breaks during the feature-flag flip
 * window.
 */

export interface SignalAlertCTAProps {
  /** Saved-strategy ID returned by the backtest endpoint. CTA only
   *  renders when this is present (you can't subscribe to an
   *  unsaved strategy). */
  strategyId: string | null;
  className?: string;
}

type Status = "idle" | "subscribing" | "subscribed" | "unsubscribing" | "unavailable";

export function SignalAlertCTA({ strategyId, className }: SignalAlertCTAProps): React.ReactElement | null {
  const { data: session, status: sessionStatus } = useSession();
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  if (!strategyId) return null;

  const isAnonymous = sessionStatus !== "authenticated";
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken ?? null;

  async function handleSubscribe(): Promise<void> {
    if (!strategyId || !backendToken) return;
    setStatus("subscribing");
    setError(null);
    try {
      await subscribeSignalAlert(strategyId, backendToken);
      setStatus("subscribed");
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setStatus("unavailable");
      } else {
        setError(msg || "Failed to subscribe");
        setStatus("idle");
      }
    }
  }

  async function handleUnsubscribe(): Promise<void> {
    if (!strategyId || !backendToken) return;
    setStatus("unsubscribing");
    setError(null);
    try {
      await unsubscribeSignalAlert(strategyId, backendToken);
      setStatus("idle");
    } catch (e) {
      setError((e as Error).message || "Failed to unsubscribe");
      setStatus("subscribed");
    }
  }

  // ── Anonymous → sign-in prompt ────────────────────────────────────────────
  if (isAnonymous) {
    return (
      <div
        className={cn(
          "rounded-xl border border-border bg-card px-4 py-3",
          className,
        )}
      >
        <div className="flex items-center gap-2.5">
          <Bell className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <div className="flex-1 text-sm">
            <span className="font-medium">Track this strategy via email</span>
            <span className="ml-1 text-muted-foreground">— sign in to get notified when the signal changes.</span>
          </div>
          <Link href={"/login" as Route}>
            <Button size="sm" variant="outline">Sign in</Button>
          </Link>
        </div>
      </div>
    );
  }

  // ── Unavailable (SIGNAL_ALERTS_ENABLED not flipped yet) ──────────────────
  if (status === "unavailable") {
    return (
      <div
        className={cn(
          "rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground",
          className,
        )}
      >
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4" aria-hidden="true" />
          <span>Email alerts not yet available — coming soon.</span>
        </div>
      </div>
    );
  }

  // ── Subscribed (or in-flight unsubscribing) ──────────────────────────────
  if (status === "subscribed" || status === "unsubscribing") {
    return (
      <div
        className={cn(
          "rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3",
          className,
        )}
      >
        <div className="flex items-center gap-2.5">
          <BellRing className="h-4 w-4 text-emerald-700" aria-hidden="true" />
          <div className="flex-1 text-sm">
            <span className="font-medium text-emerald-900">Email alerts on</span>
            <span className="ml-1 text-emerald-900/70">
              — we&apos;ll notify you when this strategy&apos;s signal changes.
            </span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleUnsubscribe}
            disabled={status === "unsubscribing"}
            className="text-emerald-900 hover:bg-emerald-100"
          >
            {status === "unsubscribing" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Turn off"}
          </Button>
        </div>
      </div>
    );
  }

  // ── Idle → opt-in CTA ────────────────────────────────────────────────────
  return (
    <div className={cn("rounded-xl border border-border bg-card px-4 py-3", className)}>
      <div className="flex items-center gap-2.5">
        <Bell className="h-4 w-4 text-primary" aria-hidden="true" />
        <div className="flex-1 text-sm">
          <span className="font-medium">Get email alerts</span>
          <span className="ml-1 text-muted-foreground">
            when this strategy&apos;s signal changes (entry / exit).
          </span>
        </div>
        <Button
          size="sm"
          onClick={handleSubscribe}
          disabled={status === "subscribing"}
        >
          {status === "subscribing" ? (
            <>
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Subscribing
            </>
          ) : (
            "Subscribe"
          )}
        </Button>
      </div>
      {error && (
        <p className="mt-1.5 text-xs text-red-600">{error}</p>
      )}
    </div>
  );
}
