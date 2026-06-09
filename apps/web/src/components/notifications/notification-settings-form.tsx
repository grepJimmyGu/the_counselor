/**
 * PRD-19 Step 6 — notification settings form brick.
 *
 * Single source of truth for the user's email + notification preferences.
 * Backed by `GET/PATCH /api/me/email-preferences` (extended in PRD-19
 * Step 4a with `signal_alerts_enabled`, `daily_digest_enabled`,
 * `silent_days_enabled` on top of the legacy 3 marketing flags).
 *
 * UX:
 *   - Optimistic toggle: click → flip locally → PATCH in background → on
 *     failure revert with an inline error message.
 *   - Toggles are grouped: "Strategy signals" (PRD-19) and "Other
 *     Livermore emails" (legacy Stage 6a). The legacy block is
 *     collapsed-by-default for visual clarity; an "Advanced" toggle
 *     expands it.
 *   - Global "Unsubscribe from everything" link at the bottom — opens
 *     the same one-click CAN-SPAM page the email footers link to.
 *
 * Trap #19 — reads `backendToken` off `useSession()` via the standard
 * cast; effect guards on `sessionStatus`. If the user is anonymous, the
 * form renders a sign-in prompt instead.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";

import {
  getEmailPreferences,
  updateEmailPreferences,
} from "@/lib/api";
import type {
  EmailPreferences,
  EmailPreferencesUpdate,
} from "@/lib/contracts";
import { cn } from "@/lib/utils";

interface NotificationSettingsFormProps {
  className?: string;
}

export function NotificationSettingsForm({
  className,
}: NotificationSettingsFormProps) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [prefs, setPrefs] = useState<EmailPreferences | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Load initial prefs. Wait for NextAuth to resolve (trap #19) so we
  // don't fire an anonymous request for a signed-in user.
  useEffect(() => {
    if (sessionStatus === "loading") return;
    if (!backendToken) {
      setPrefs(null);
      return;
    }
    getEmailPreferences(backendToken)
      .then(setPrefs)
      .catch((err: unknown) => {
        setLoadError(
          err instanceof Error ? err.message : "Couldn't load preferences.",
        );
      });
  }, [backendToken, sessionStatus]);

  const togglePref = useCallback(
    async (key: keyof EmailPreferencesUpdate, nextValue: boolean) => {
      if (!prefs || !backendToken) return;
      // Snapshot previous for rollback.
      const previous = prefs;
      const optimistic: EmailPreferences = { ...prefs, [key]: nextValue };
      setPrefs(optimistic);
      setSaveError(null);
      try {
        const updated = await updateEmailPreferences(
          { [key]: nextValue } as EmailPreferencesUpdate,
          backendToken,
        );
        // Use the server's truth — it might clear `unsubscribed_at` on
        // a re-enable, which the optimistic state doesn't model.
        setPrefs(updated);
      } catch (err: unknown) {
        setPrefs(previous);
        setSaveError(
          err instanceof Error ? err.message : "Couldn't save. Try again.",
        );
      }
    },
    [backendToken, prefs],
  );

  if (sessionStatus === "loading") {
    return (
      <div className={cn("rounded-lg border border-slate-200 p-6", className)}>
        <p className="text-sm text-slate-500">Loading preferences…</p>
      </div>
    );
  }

  if (!backendToken) {
    return (
      <div
        className={cn(
          "rounded-lg border border-slate-200 bg-slate-50 p-6 text-center",
          className,
        )}
      >
        <p className="mb-3 text-sm text-slate-700">
          Sign in to manage your notification preferences.
        </p>
        <Link
          href={"/auth/signin" as Route}
          className="inline-flex items-center justify-center rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
        >
          Sign in
        </Link>
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        className={cn(
          "rounded-lg border border-rose-200 bg-rose-50 p-6",
          className,
        )}
      >
        <p className="text-sm text-rose-700">{loadError}</p>
      </div>
    );
  }

  if (!prefs) {
    return (
      <div className={cn("rounded-lg border border-slate-200 p-6", className)}>
        <p className="text-sm text-slate-500">Loading preferences…</p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} data-testid="notification-settings-form">
      {/* PRD-19 Strategy signals block — the load-bearing toggles. */}
      <fieldset className="rounded-lg border border-slate-200 bg-white p-5">
        <legend className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Strategy signals
        </legend>
        <div className="mt-2 flex flex-col gap-4">
          <ToggleRow
            id="signal_alerts_enabled"
            label="Signal-change emails"
            description="When a saved strategy flips long ↔ cash, or rotates a basket, we email you the new signal."
            checked={prefs.signal_alerts_enabled}
            onChange={(v) => togglePref("signal_alerts_enabled", v)}
          />
          <ToggleRow
            id="daily_digest_enabled"
            label="Daily morning brief"
            description="One summary email each morning with what changed overnight across your saved strategies."
            checked={prefs.daily_digest_enabled}
            onChange={(v) => togglePref("daily_digest_enabled", v)}
          />
          <ToggleRow
            id="silent_days_enabled"
            label='"Only when there’s news" mode'
            description="Skip the morning brief on days nothing flipped. Off by default — you get the brief every day."
            checked={prefs.silent_days_enabled}
            onChange={(v) => togglePref("silent_days_enabled", v)}
          />
        </div>
      </fieldset>

      {/* Legacy Stage 6a — collapsed by default. */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-[12px] font-medium text-slate-500 hover:text-slate-700"
        >
          {showAdvanced ? "Hide" : "Show"} other Livermore email categories
        </button>
        {showAdvanced ? (
          <fieldset className="mt-3 rounded-lg border border-slate-200 bg-white p-5">
            <legend className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Other Livermore emails
            </legend>
            <div className="mt-2 flex flex-col gap-4">
              <ToggleRow
                id="weekly_digest"
                label="Weekly digest"
                description="A weekly roundup of the community + product updates."
                checked={prefs.weekly_digest}
                onChange={(v) => togglePref("weekly_digest", v)}
              />
              <ToggleRow
                id="upsell_nudges"
                label="Upgrade nudges"
                description="Occasional emails when a feature you'd benefit from is gated by your tier."
                checked={prefs.upsell_nudges}
                onChange={(v) => togglePref("upsell_nudges", v)}
              />
              <ToggleRow
                id="creator_program"
                label="Creator program updates"
                description="Updates relevant only if you've applied to the Creator program. Safe to leave on."
                checked={prefs.creator_program}
                onChange={(v) => togglePref("creator_program", v)}
              />
            </div>
          </fieldset>
        ) : null}
      </div>

      {prefs.unsubscribed_at ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-[12px] text-slate-600">
            You globally unsubscribed on {formatDate(prefs.unsubscribed_at)}.
            Flipping any toggle above back on will clear that.
          </p>
        </div>
      ) : null}

      {saveError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3">
          <p className="text-[12px] text-rose-700">{saveError}</p>
        </div>
      ) : null}
    </div>
  );
}

interface ToggleRowProps {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}

function ToggleRow({ id, label, description, checked, onChange }: ToggleRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <label htmlFor={id} className="flex-1 cursor-pointer select-none">
        <span className="block text-sm font-medium text-slate-900">{label}</span>
        <span className="mt-0.5 block text-[12px] leading-snug text-slate-500">
          {description}
        </span>
      </label>
      <button
        type="button"
        role="switch"
        id={id}
        aria-checked={checked}
        data-testid={`toggle-${id}`}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border transition",
          checked
            ? "border-emerald-500 bg-emerald-500"
            : "border-slate-300 bg-slate-200",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition",
            checked ? "translate-x-6" : "translate-x-1",
          )}
        />
      </button>
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
