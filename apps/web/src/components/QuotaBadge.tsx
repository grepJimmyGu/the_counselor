"use client";

import Link from "next/link";
import { useEntitlements } from "@/lib/useEntitlements";

const SCOUT_WEEKLY_CAP = 5;

/**
 * Top-bar quota indicator (Stage 1a).
 *
 *   Scout (authenticated):   "3 / 5 runs · resets Monday"   → links to /pricing
 *   Strategist / Quant:       hidden (custom runs are unlimited)
 *   Anonymous, runs left:    "1 free run left — sign up to save" → links to /signup
 *   Anonymous, exhausted:    "Sign up to keep exploring"          → links to /signup
 */
export function QuotaBadge() {
  const { entitlements, anonymousEntitlements, isAnonymous, loading } = useEntitlements();

  if (loading) return null;

  if (isAnonymous) {
    const remaining = anonymousEntitlements?.runs_remaining ?? 0;
    const label =
      remaining > 0
        ? `${remaining} free run left — sign up to save`
        : "Sign up to keep exploring";
    return (
      <Link
        href="/signup"
        className="hidden md:inline-flex items-center rounded-full border border-border bg-muted/40 px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted/70"
      >
        {label}
      </Link>
    );
  }

  if (!entitlements) return null;
  if (entitlements.custom_backtest_runs_remaining === null) return null; // unlimited tier

  const remaining = entitlements.custom_backtest_runs_remaining;
  const used = SCOUT_WEEKLY_CAP - remaining;
  return (
    <Link
      href="/pricing"
      className="hidden md:inline-flex items-center rounded-full border border-border bg-muted/40 px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted/70"
      title="Custom-strategy weekly quota. Templates remain unlimited."
    >
      {used} / {SCOUT_WEEKLY_CAP} runs · resets Monday
    </Link>
  );
}
