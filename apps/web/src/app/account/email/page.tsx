"use client";

export const dynamic = "force-dynamic";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  getEmailPreferences,
  updateEmailPreferences,
  type EmailPreferencesResponse,
} from "@/lib/api";
import { track } from "@/lib/analytics";

export default function EmailPreferencesPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;

  const [prefs, setPrefs] = useState<EmailPreferencesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // Redirect if not signed in
  useEffect(() => {
    if (status === "unauthenticated") router.push("/login" as Route);
  }, [status, router]);

  useEffect(() => {
    if (!backendToken) return;
    setLoading(true);
    getEmailPreferences(backendToken)
      .then(setPrefs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [backendToken]);

  async function save(patch: Partial<Pick<EmailPreferencesResponse, "weekly_digest" | "upsell_nudges" | "creator_program">>) {
    if (!backendToken || !prefs) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const next = await updateEmailPreferences(patch, backendToken);
      setPrefs(next);
      setSaveMsg("Saved.");
      track("email_preferences_updated", patch as Record<string, unknown>);
    } catch (err) {
      setSaveMsg((err as Error).message || "Save failed.");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(null), 2000);
    }
  }

  if (status === "loading" || loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </main>
    );
  }
  if (!prefs) return null;

  return (
    <main className="mx-auto max-w-2xl px-4 py-10 md:py-14">
      <nav className="mb-6 text-xs text-muted-foreground">
        <Link href={"/account" as Route} className="hover:text-foreground">
          ← Account
        </Link>
      </nav>

      <h1 className="font-heading text-2xl font-bold">Email preferences</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Pick what you want to hear from us about. We always send important
        account email (verifications, payment receipts) regardless.
      </p>

      <section className="mt-8 space-y-3">
        <Toggle
          label="Weekly digest"
          description="A Monday-morning recap of your activity, top community publishes, and what's new."
          checked={prefs.weekly_digest}
          disabled={saving}
          onChange={(v) => save({ weekly_digest: v })}
        />
        <Toggle
          label="Upgrade nudges"
          description="We'll email if you hit free-tier walls multiple times — never more than once a month."
          checked={prefs.upsell_nudges}
          disabled={saving}
          onChange={(v) => save({ upsell_nudges: v })}
        />
        <Toggle
          label="Creator Program"
          description="Updates about the referral program, payouts, and creator tools."
          checked={prefs.creator_program}
          disabled={saving}
          onChange={(v) => save({ creator_program: v })}
        />
      </section>

      {prefs.unsubscribed_at && (
        <div className="mt-6 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-900 dark:text-amber-200">
          You've globally unsubscribed. Toggling any of the above back ON
          will re-subscribe you to that category.
        </div>
      )}

      {saveMsg && (
        <p className="mt-4 flex items-center gap-1.5 text-xs text-emerald-600">
          <Check className="h-3.5 w-3.5" />
          {saveMsg}
        </p>
      )}

      <div className="mt-10 rounded-xl border border-border bg-card p-5">
        <p className="text-sm font-semibold">Transactional email</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Account verification, password resets, payment receipts, and trial
          alerts are always delivered. These can't be turned off — they're
          legally required for your account to function.
        </p>
      </div>
    </main>
  );
}

function Toggle({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-4 rounded-xl border border-border bg-card p-5 transition-colors hover:bg-accent/30">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 cursor-pointer accent-primary"
      />
      <span className="flex-1">
        <span className="block text-sm font-medium text-foreground">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}
