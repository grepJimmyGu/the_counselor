"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import type { AnonymousEntitlements, Entitlements } from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

interface UseEntitlementsResult {
  entitlements: Entitlements | null;
  anonymousEntitlements: AnonymousEntitlements | null;
  isAnonymous: boolean;
  loading: boolean;
}

/**
 * Fetch the current viewer's entitlements.
 *
 * Returns one of two shapes:
 *  - Authenticated viewers: `entitlements: Entitlements` (the per-tier caps).
 *  - Anonymous viewers: `anonymousEntitlements: AnonymousEntitlements`
 *    (runs_remaining + signup CTA variant).
 *
 * `isAnonymous` is the canonical switch for components that need to render
 * differently for the two surfaces — don't rely on `entitlements === null`.
 */
export function useEntitlements(): UseEntitlementsResult {
  const { data: session, status } = useSession();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [anonymousEntitlements, setAnonymousEntitlements] = useState<AnonymousEntitlements | null>(null);
  const [loading, setLoading] = useState(false);

  const backendToken = (session as unknown as { backendToken?: string })?.backendToken;
  const isAuthenticated = status === "authenticated" && !!backendToken;

  useEffect(() => {
    if (status === "loading") return;

    let cancelled = false;
    setLoading(true);

    const url = isAuthenticated
      ? `${API_BASE}/api/me/entitlements`
      : `${API_BASE}/api/anonymous/entitlements`;
    const init: RequestInit = isAuthenticated
      ? { headers: { Authorization: `Bearer ${backendToken}` } }
      : { credentials: "include" }; // anonymous endpoint sets livermore_anon_id cookie

    fetch(url, init)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return;
        if (isAuthenticated) {
          setEntitlements(data as Entitlements);
          setAnonymousEntitlements(null);
        } else {
          setAnonymousEntitlements(data as AnonymousEntitlements);
          setEntitlements(null);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [status, isAuthenticated, backendToken]);

  return {
    entitlements,
    anonymousEntitlements,
    isAnonymous: !isAuthenticated,
    loading,
  };
}
