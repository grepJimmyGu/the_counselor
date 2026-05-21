"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";

import { identifyUser, resetUser, track } from "@/lib/analytics";

/**
 * Stage 6a — Analytics lifecycle.
 *
 * Mounted once at the root layout. Subscribes to:
 *   - Session changes: identifies user on auth, resets on signout
 *   - Pathname changes: fires page_view (we set capture_pageview=false in
 *     analytics.ts so we control when this fires for cleaner data)
 *
 * Safe no-op when PostHog isn't configured — all calls go through the
 * track/identifyUser/resetUser wrappers which short-circuit on no key.
 */
export function AnalyticsProvider() {
  const { data: session } = useSession();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastIdentifiedRef = useRef<string | null>(null);

  // Identify on auth, reset on signout
  useEffect(() => {
    const userId = session?.user
      ? ((session.user as unknown as { id?: string }).id ?? null)
      : null;
    if (userId && userId !== lastIdentifiedRef.current) {
      identifyUser(userId, {
        email: session?.user?.email ?? undefined,
        name: session?.user?.name ?? undefined,
      });
      lastIdentifiedRef.current = userId;
    } else if (!userId && lastIdentifiedRef.current) {
      resetUser();
      lastIdentifiedRef.current = null;
    }
  }, [session]);

  // page_view on every route change. Includes ?via= for share-URL attribution.
  useEffect(() => {
    if (!pathname) return;
    const via = searchParams?.get("via") ?? undefined;
    track("page_view", {
      path: pathname,
      via_handle: via,
    });
  }, [pathname, searchParams]);

  return null;
}
