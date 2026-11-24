import type { ReactNode } from "react";

/**
 * Makes the company page a static shell: generated the first time a ticker is
 * visited, then served from cache.
 *
 * Without this the route is `ƒ (Dynamic)` — a function re-renders it on every
 * request — even though `page.tsx` is a client component whose server output
 * is identical for every visitor (the skeleton; all data loads in the
 * browser). That per-request render was part of what Vercel paused the
 * project for on 2026-11-11: see docs/KNOWN_ISSUES.md.
 *
 * Returning an empty list means "prerender nothing at build time, generate
 * each path on first visit". `dynamicParams` stays at its default (true), so
 * every ticker still resolves — do not set it to false.
 *
 * This lives in a layout because `generateStaticParams` cannot be exported
 * from a "use client" file, and `page.tsx` is one.
 */
export function generateStaticParams(): { ticker: string }[] {
  return [];
}

export default function TickerLayout({ children }: { children: ReactNode }) {
  return children;
}
