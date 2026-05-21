"use client";

import { BadgeCheck, Star } from "lucide-react";

type Badge = "verified" | "creator" | null | undefined;

interface Props {
  badge: Badge;
  /** Visual size of the icon (rem-based via Tailwind h-N w-N). */
  size?: "xs" | "sm" | "md";
}

/**
 * Quant tier → blue verified check.
 * Creator Program member (Stage 5) → gold star.
 * Otherwise renders nothing.
 */
export function VerifiedBadge({ badge, size = "sm" }: Props) {
  if (!badge) return null;
  const sizeClass =
    size === "xs" ? "h-3 w-3" : size === "md" ? "h-5 w-5" : "h-4 w-4";

  if (badge === "creator") {
    return (
      <Star
        className={`${sizeClass} fill-amber-400 text-amber-500`}
        aria-label="Creator"
      />
    );
  }
  // "verified"
  return (
    <BadgeCheck
      className={`${sizeClass} text-sky-500`}
      aria-label="Verified"
    />
  );
}
