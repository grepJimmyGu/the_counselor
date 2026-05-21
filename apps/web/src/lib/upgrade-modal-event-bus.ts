"use client";

/**
 * Global event bus for triggering the UpgradeModal from anywhere.
 *
 * When the API client (fetchApi) detects a 402 with `error="upgrade_required"`,
 * it calls `dispatchUpgrade(entitlementDetail)`. The UpgradeModal (mounted once
 * at the root layout) subscribes and renders the matching copy variant.
 *
 * Using a tiny event-emitter pattern instead of React Context so that
 * non-React code (the api.ts module) can publish events.
 */
import type { EntitlementErrorDetail } from "@/lib/contracts";

type Listener = (detail: EntitlementErrorDetail) => void;

const _listeners = new Set<Listener>();

export function dispatchUpgrade(detail: EntitlementErrorDetail): void {
  for (const fn of _listeners) {
    try {
      fn(detail);
    } catch {
      // Listeners must not break dispatch
    }
  }
}

export function subscribeUpgrade(fn: Listener): () => void {
  _listeners.add(fn);
  return () => {
    _listeners.delete(fn);
  };
}
