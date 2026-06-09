/**
 * PRD-19 Step 6 — Notification settings page.
 *
 * Single surface for the user to manage their notification preferences:
 *   - PRD-19 signal alerts + daily digest + silent-days toggle
 *   - Legacy Stage 6a marketing flags (collapsed, advanced section)
 *   - Global unsub status hint
 *
 * The page itself is a Client Component because the form polls / writes
 * via NextAuth-authenticated requests. The settings form brick is the
 * load-bearing piece; this file is just the page shell + nav + footer.
 *
 * Note: the existing /account/email page (Stage 6a) continues to serve
 * the legacy 3-flag UX. PRD-19 doesn't deprecate it — both surfaces
 * target the same endpoint and stay in sync via the form's optimistic
 * refresh-from-server pattern. Step 6 doesn't migrate or redirect.
 */
"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import type { Route } from "next";

import { NotificationSettingsForm } from "@/components/notifications/notification-settings-form";
import { NotInvestmentAdviceFooter } from "@/components/notifications/not-investment-advice-footer";

export default function NotificationSettingsPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 md:py-14">
      <nav className="mb-6 text-xs text-muted-foreground">
        <Link
          href={"/account" as Route}
          className="hover:text-foreground"
        >
          ← Account
        </Link>
      </nav>

      <header className="mb-8">
        <h1 className="font-heading text-2xl font-bold">Notifications</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Manage signal alerts, the daily morning brief, and other email
          you get from Livermore. Important account email (verifications,
          payment receipts) is always delivered regardless of these
          settings.
        </p>
      </header>

      <NotificationSettingsForm />

      <div className="mt-10">
        <NotInvestmentAdviceFooter />
      </div>
    </main>
  );
}
