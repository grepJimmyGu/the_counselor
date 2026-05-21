"use client";

/**
 * PostHog analytics — safe no-op wrapper (Stage 6a).
 *
 * Usage:
 *   import { track, identifyUser, resetUser } from "@/lib/analytics";
 *   track("signup_completed", { provider: "google", locale: "en" });
 *
 * The wrapper:
 *   - Lazy-loads `posthog-js` only when NEXT_PUBLIC_POSTHOG_KEY is set
 *   - Silently no-ops if the key is missing OR the package isn't installed
 *   - Catches all PostHog errors so analytics never breaks a render
 *
 * To enable:
 *   1. `npm install posthog-js` (add to package.json same commit)
 *   2. Set Vercel env vars NEXT_PUBLIC_POSTHOG_KEY + NEXT_PUBLIC_POSTHOG_HOST
 *   3. Redeploy. Events start firing on the next page load.
 */

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.posthog.com";

type PostHog = {
  init: (key: string, opts: Record<string, unknown>) => void;
  capture: (event: string, props?: Record<string, unknown>) => void;
  identify: (userId: string, traits?: Record<string, unknown>) => void;
  reset: () => void;
  __loaded?: boolean;
};

let _client: PostHog | null = null;
let _loadAttempted = false;

async function _getClient(): Promise<PostHog | null> {
  if (_client) return _client;
  if (_loadAttempted) return null;
  _loadAttempted = true;
  if (!KEY || typeof window === "undefined") return null;
  try {
    // Lazy dynamic import — webpack code-splits, only fetched when KEY is set.
    const mod = await import("posthog-js");
    const ph = (mod.default ?? mod) as unknown as PostHog;
    if (!ph.__loaded) {
      ph.init(KEY, {
        api_host: HOST,
        person_profiles: "identified_only",
        capture_pageview: false, // we send page_view manually
        capture_pageleave: true,
        autocapture: false,
        // session_recording: enable in a follow-up after PII review
      });
    }
    _client = ph;
    return ph;
  } catch (err) {
    // init failed — keep no-op'ing.
    // eslint-disable-next-line no-console
    console.debug("analytics: posthog-js init failed, no-op mode", err);
    return null;
  }
}

/**
 * Fire an event. Silent no-op when PostHog is disabled.
 *
 * Property naming convention: snake_case, flat (no nested objects),
 * currency in cents, dates ISO 8601.
 */
export function track(event: string, props?: Record<string, unknown>): void {
  if (!KEY) return;
  // Fire-and-forget; don't await in caller code.
  void _getClient().then((ph) => {
    if (!ph) return;
    try {
      ph.capture(event, props);
    } catch {
      // never break the UI
    }
  });
}

export function identifyUser(userId: string, traits?: Record<string, unknown>): void {
  if (!KEY) return;
  void _getClient().then((ph) => {
    if (!ph) return;
    try {
      ph.identify(userId, traits);
    } catch {
      /* noop */
    }
  });
}

export function resetUser(): void {
  if (!KEY) return;
  void _getClient().then((ph) => {
    if (!ph) return;
    try {
      ph.reset();
    } catch {
      /* noop */
    }
  });
}

/**
 * Standard event names — match backend/services/posthog_service.py taxonomy.
 * Defined as a union type so callers can autocomplete + TypeScript catches typos.
 */
export type AnalyticsEvent =
  | "page_view"
  | "signup_started"
  | "signup_completed"
  | "trial_started"
  | "template_run"
  | "backtest_started"
  | "backtest_completed"
  | "paywall_hit"
  | "paywall_cta_clicked"
  | "checkout_started"
  | "checkout_completed"
  | "strategy_published"
  | "strategy_viewed"
  | "share_clicked"
  | "referral_landed"
  | "unsubscribed"
  | "email_preferences_updated";
