"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Tier } from "@/lib/contracts";
import type { Route } from "next";

interface PricingTierCardProps {
  tier: Tier | "scout";
  name: string;
  tagline: string;
  monthlyPrice: number | null;   // cents; null = free
  annualPrice: number | null;    // cents effective per month; null = free
  cycle: "monthly" | "annual";
  features: string[];
  ctaLabel: string;
  ctaHref?: string;
  onCta?: () => void;
  highlighted?: boolean;
  badge?: string;
  ctaDisabled?: boolean;
}

export function PricingTierCard({
  tier,
  name,
  tagline,
  monthlyPrice,
  annualPrice,
  cycle,
  features,
  ctaLabel,
  ctaHref,
  onCta,
  highlighted = false,
  badge,
  ctaDisabled = false,
}: PricingTierCardProps) {
  const price = cycle === "annual" ? annualPrice : monthlyPrice;
  const displayPrice =
    price === null ? "Free" : `$${Math.round(price / 100)}`;
  const displaySuffix = price === null ? "" : "/mo";
  const annualNote =
    cycle === "annual" && annualPrice !== null && monthlyPrice !== null
      ? `Billed $${Math.round((annualPrice / 100) * 12)}/yr`
      : null;

  return (
    <div
      className={cn(
        "relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm transition-shadow hover:shadow-md",
        highlighted
          ? "border-primary ring-2 ring-primary"
          : "border-border",
      )}
    >
      {badge && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-xs font-semibold text-primary-foreground">
          {badge}
        </div>
      )}

      <div className="mb-4">
        <h2 className="font-heading text-lg font-bold">{name}</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{tagline}</p>
      </div>

      <div className="mb-6">
        <span className="font-heading text-4xl font-bold">{displayPrice}</span>
        <span className="text-muted-foreground">{displaySuffix}</span>
        {annualNote && (
          <p className="mt-1 text-xs text-muted-foreground">{annualNote}</p>
        )}
      </div>

      {ctaHref ? (
        <Button
          asChild
          className={cn("w-full", highlighted ? "" : "variant-outline")}
          variant={highlighted ? "default" : "outline"}
          disabled={ctaDisabled}
        >
          <Link href={ctaHref as Route}>{ctaLabel}</Link>
        </Button>
      ) : (
        <Button
          className="w-full"
          variant={highlighted ? "default" : "outline"}
          onClick={onCta}
          disabled={ctaDisabled}
        >
          {ctaLabel}
        </Button>
      )}

      <ul className="mt-6 space-y-2.5">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
