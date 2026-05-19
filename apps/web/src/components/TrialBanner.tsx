"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { createCheckoutSession } from "@/lib/api";
import type { UserMe } from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function daysUntil(isoDate: string): number {
  const diff = new Date(isoDate).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

export function TrialBanner() {
  const { data: session } = useSession();
  const [me, setMe] = useState<UserMe | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(false);

  const backendToken = (session as any)?.backendToken as string | undefined;

  useEffect(() => {
    if (!backendToken) return;
    fetch(`${API_BASE}/api/me`, { headers: { Authorization: `Bearer ${backendToken}` } })
      .then(r => (r.ok ? r.json() : null))
      .then((d: UserMe | null) => { if (d) setMe(d); })
      .catch(() => {});
  }, [backendToken]);

  if (!me || me.plan.status !== "trialing" || !me.plan.trial_end || dismissed) return null;

  const days = daysUntil(me.plan.trial_end);

  async function handleAddCard() {
    if (!backendToken) return;
    setLoading(true);
    try {
      const returnUrl = window.location.href;
      const { url } = await createCheckoutSession(
        { tier: me!.plan.tier as "strategist" | "quant", billing_cycle: "monthly", return_url: returnUrl },
        backendToken,
      );
      window.location.href = url;
    } catch {
      setLoading(false);
    }
  }

  const urgency = days <= 3 ? "border-rose-400 bg-rose-50 text-rose-900" : "border-amber-400 bg-amber-50 text-amber-900";

  return (
    <div className={`flex items-center justify-between gap-4 border-b px-4 py-2 text-sm ${urgency}`}>
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          <strong>Trial ends in {days} day{days !== 1 ? "s" : ""}</strong>
          {" · Add a card to keep your "}
          <span className="capitalize">{me.plan.tier}</span> features.
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={handleAddCard}
          disabled={loading}
          className="cursor-pointer rounded-md border border-current px-3 py-1 text-xs font-semibold hover:opacity-80 disabled:opacity-50"
        >
          {loading ? "Redirecting…" : "Add a card"}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss trial banner"
          className="cursor-pointer rounded-md p-1 hover:opacity-70"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
