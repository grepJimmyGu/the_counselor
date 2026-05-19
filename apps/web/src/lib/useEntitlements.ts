"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import type { Entitlements } from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

interface UseEntitlementsResult {
  entitlements: Entitlements | null;
  loading: boolean;
}

/**
 * Fetch the current user's entitlements once per page load.
 * Returns null when the user is unauthenticated or the fetch hasn't completed yet.
 */
export function useEntitlements(): UseEntitlementsResult {
  const { data: session, status } = useSession();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [loading, setLoading] = useState(false);

  const backendToken = (session as any)?.backendToken as string | undefined;

  useEffect(() => {
    if (status !== "authenticated" || !backendToken) return;
    setLoading(true);
    fetch(`${API_BASE}/api/me/entitlements`, {
      headers: { Authorization: `Bearer ${backendToken}` },
    })
      .then(r => (r.ok ? r.json() : null))
      .then((data: Entitlements | null) => { if (data) setEntitlements(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [status, backendToken]);

  return { entitlements, loading };
}
