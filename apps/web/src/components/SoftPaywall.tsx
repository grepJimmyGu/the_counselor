"use client";

import Link from "next/link";
import type { Route } from "next";
import { Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { EntitlementErrorDetail } from "@/lib/contracts";

interface SoftPaywallProps {
  /** Either supply a full EntitlementErrorDetail or the partial fields below. */
  detail?: EntitlementErrorDetail;
  title?: string;
  body?: string;
  ctaLabel?: string;
  ctaHref?: string;
}

/**
 * Inline upgrade card for embedded gates — used when a page-level fetch
 * returns 402 and we want to keep the user on the page instead of opening
 * the global UpgradeModal.
 *
 * Pass the parsed EntitlementErrorDetail when you have it (from a caught
 * UpgradeRequiredError); fall back to manual props otherwise.
 */
export function SoftPaywall({
  detail,
  title,
  body,
  ctaLabel,
  ctaHref,
}: SoftPaywallProps) {
  const resolvedTitle = title ?? (detail?.detail ?? "Upgrade to unlock this feature");
  const resolvedBody = body ?? _bodyFor(detail);
  const resolvedCta = ctaLabel ?? (detail?.cta_text ?? "Upgrade");
  const resolvedHref = (ctaHref ?? detail?.upgrade_url ?? "/pricing") as Route;

  return (
    <div className="rounded-xl border border-border bg-muted/30 p-6 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Lock className="h-5 w-5" />
      </div>
      <h3 className="mt-3 text-base font-semibold text-foreground">{resolvedTitle}</h3>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{resolvedBody}</p>
      <div className="mt-4">
        <Button asChild size="sm">
          <Link href={resolvedHref}>{resolvedCta}</Link>
        </Button>
      </div>
    </div>
  );
}

function _bodyFor(detail?: EntitlementErrorDetail): string {
  if (!detail) return "";
  if (detail.is_anonymous) {
    return "Sign up in one click — Scout (free) includes weekly custom runs and unlimited templates.";
  }
  if (detail.required_tier === "quant") {
    return "Quant unlocks the full feature set including A-shares, all-5 robustness tests, and supply-chain deep-dive.";
  }
  return "Strategist unlocks unlimited custom runs, 10-year history, larger universes, and all-US Market Pulse.";
}
