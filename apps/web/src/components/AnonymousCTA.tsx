"use client";

import Link from "next/link";
import type { Route } from "next";
import { Button } from "@/components/ui/button";
import { useEntitlements } from "@/lib/useEntitlements";

type Variant = "before-run" | "after-run" | "second-run-blocked";

interface AnonymousCTAProps {
  variant: Variant;
  /** Optional creator handle (preserves attribution through ?via=handle). */
  viaHandle?: string;
}

/**
 * Anonymous viewer call-to-action (Stage 1a).
 *
 * Renders one of three copy variants depending on where the viewer is in the
 * one-shot funnel. Only visible to anonymous users — authenticated users see
 * nothing.
 *
 *   before-run            "Run this strategy free — no signup needed"
 *   after-run             "Save this strategy and run more — 1-click Google signup"
 *   second-run-blocked    "Continue with Google" (modal-style block)
 */
export function AnonymousCTA({ variant, viaHandle }: AnonymousCTAProps) {
  const { isAnonymous, loading } = useEntitlements();

  if (loading || !isAnonymous) return null;

  const signupHref = `/signup?intent=continue${viaHandle ? `&via=${encodeURIComponent(viaHandle)}` : ""}`;

  if (variant === "before-run") {
    return (
      <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm text-foreground">
        <p className="font-medium">Run this strategy free — no signup needed.</p>
        <p className="mt-1 text-xs text-muted-foreground">
          You get one free backtest. Sign up after to save it and keep exploring.
        </p>
      </div>
    );
  }

  if (variant === "after-run") {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
        <p className="text-sm font-medium text-foreground">
          Save this strategy and run more
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          One-click signup with Google attaches this backtest to your new account.
        </p>
        <div className="mt-3">
          <Button asChild size="sm">
            <Link href={signupHref as Route}>Continue with Google</Link>
          </Button>
        </div>
      </div>
    );
  }

  // second-run-blocked
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
      <p className="text-sm font-medium text-foreground">You&apos;ve used your free backtest</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Sign up to keep exploring — Scout includes 5 custom backtests every week,
        plus unlimited templates.
      </p>
      <div className="mt-3">
        <Button asChild size="sm">
          <Link href={signupHref as Route}>Continue with Google</Link>
        </Button>
      </div>
    </div>
  );
}
